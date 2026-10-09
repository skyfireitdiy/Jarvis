"""
记忆整理工具 - 用于合并具有相似标签的记忆

该工具会查找具有高度重叠标签的记忆，并使用大模型将它们合并成一个新的记忆。
"""

import json
from collections import defaultdict
from pathlib import Path

from jarvis.jarvis_utils.output import PrettyOutput

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Set

import typer

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import (
    get_data_dir,
    set_llm_group,
    get_max_input_token_count,
)
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.utils import init_env


class MemoryOrganizer:
    """记忆整理器，用于合并具有相似标签的记忆"""

    def __init__(self):
        """初始化记忆整理器"""
        self.project_memory_dir = Path(".jarvis/memory")
        self.global_memory_dir = Path(get_data_dir()) / "memory"

        # 获取当前配置的平台实例
        registry = PlatformRegistry.get_global_platform_registry()
        self.platform = registry.get_normal_platform()

    def _resolve_memory_dir(self, memory_type: str) -> Path:
        """把记忆类型名解析为存储目录（兼容平铺名与双字段名）

        支持：
        - 平铺名：project_long_term / global_long_term / project_procedural ...
        - 双字段名：project/long_term / global/procedural ...
        - 仅作用域：project / global（默认 long_term）
        """
        if "/" in memory_type:
            scope, nature = memory_type.split("/", 1)
        elif "_" in memory_type:
            scope, nature = memory_type.split("_", 1)
        else:
            scope, nature = memory_type, "long_term"

        if scope == "project":
            if nature == "long_term":
                return self.project_memory_dir
            return self.project_memory_dir / nature
        elif scope == "global":
            if nature == "long_term":
                return self.global_memory_dir / "global_long_term"
            return self.global_memory_dir / nature
        raise ValueError(f"不支持的记忆类型: {memory_type}")

    def _get_memory_files(self, memory_type: str) -> List[Path]:
        """获取指定类型的所有记忆文件"""
        memory_dir = self._resolve_memory_dir(memory_type)

        if not memory_dir.exists():
            return []

        return list(memory_dir.glob("*.json"))

    def _load_memories(self, memory_type: str) -> List[Dict[str, Any]]:
        """加载指定类型的所有记忆"""
        memories = []
        memory_files = self._get_memory_files(memory_type)
        error_lines: List[str] = []

        for memory_file in memory_files:
            try:
                with open(memory_file, "r", encoding="utf-8") as f:
                    memory_data = json.load(f)
                    memory_data["file_path"] = str(memory_file)
                    memories.append(memory_data)
            except Exception as e:
                error_lines.append(f"读取记忆文件 {memory_file} 失败: {str(e)}")

        if error_lines:
            joined_errors = "\n".join(error_lines)
            PrettyOutput.auto_print(f"⚠️ {joined_errors}")

        return memories

    def _find_overlapping_memories(
        self, memories: List[Dict[str, Any]], min_overlap: int
    ) -> Dict[int, List[Set[int]]]:
        """
        查找具有重叠标签的记忆组

        返回：{重叠数量: [记忆索引集合列表]}

        性能优化：原实现为 O(n²) 两两比较 + O(n³) 组扩展，在记忆数量大时
        （如数千条）会非常慢。优化后：
        1. 用标签索引只生成"共享 >= min_overlap 个标签"的候选记忆对，
           避免全量 O(n²) 两两比较（候选对通常远小于全量对）；
        2. 组扩展时只从候选邻居中寻找可加入的记忆，避免遍历全部记忆。
        语义保持不变：组内任意两条记忆的重叠标签数均 >= min_overlap。
        """
        # 预计算每条记忆的标签集合
        tags_of = [set(memory.get("tags", [])) for memory in memories]

        # 构建标签到记忆索引的映射
        tag_to_memories = defaultdict(set)
        for i, tags in enumerate(tags_of):
            for tag in tags:
                tag_to_memories[tag].add(i)

        # 生成候选边：共享 >= min_overlap 个标签的记忆对（i < j）
        candidate_edges = set()
        visited_pairs = set()
        for memset in tag_to_memories.values():
            lst = sorted(memset)
            for a in range(len(lst)):
                for b in range(a + 1, len(lst)):
                    i, j = lst[a], lst[b]
                    key = (i, j) if i < j else (j, i)
                    if key in visited_pairs:
                        continue
                    visited_pairs.add(key)
                    if len(tags_of[i] & tags_of[j]) >= min_overlap:
                        candidate_edges.add(key)

        # 候选邻居表：与某记忆共享 >= min_overlap 个标签的其它记忆
        candidate_adj = defaultdict(set)
        for i, j in candidate_edges:
            candidate_adj[i].add(j)
            candidate_adj[j].add(i)

        # 查找具有共同标签的记忆组（团语义：组内两两重叠 >= min_overlap）
        overlap_groups = defaultdict(list)
        processed_groups = set()

        for i, j in sorted(candidate_edges):
            group = {i, j}

            # 扩展组，包含所有与组内记忆有足够重叠的记忆
            changed = True
            while changed:
                changed = False
                # 只从候选邻居中寻找可加入的记忆（候选邻居远少于全部记忆）
                candidates = set()
                for m in group:
                    candidates |= candidate_adj[m]
                for k in candidates:
                    if k not in group:
                        # 检查与组内所有记忆的最小重叠数
                        min_overlap_with_group = min(
                            len(tags_of[k] & tags_of[m]) for m in group
                        )
                        if min_overlap_with_group >= min_overlap:
                            group.add(k)
                            changed = True

            # 将组转换为有序元组以便去重
            group_tuple = tuple(sorted(group))
            if group_tuple not in processed_groups:
                processed_groups.add(group_tuple)
                overlap_groups[min_overlap].append(set(group_tuple))

        return overlap_groups

    def _merge_memories_with_llm(
        self, memories: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """使用大模型合并多个记忆"""
        # 准备合并提示
        memory_contents = []
        all_tags = set()

        # 按创建时间排序，最新的在前
        sorted_memories = sorted(
            memories, key=lambda m: m.get("created_at", ""), reverse=True
        )

        for memory in sorted_memories:
            memory_contents.append(
                f"记忆ID: {memory.get('id', '未知')}\n"
                f"创建时间: {memory.get('created_at', '未知')}\n"
                f"标签: {', '.join(memory.get('tags', []))}\n"
                f"内容:\n{memory.get('content', '')}"
            )
            all_tags.update(memory.get("tags", []))

        memory_contents_str = (("=" * 50) + "\n").join(memory_contents)

        prompt = f"""请将以下{len(memories)}个相关记忆合并成一个综合性的记忆。

原始记忆（按时间从新到旧排序）：
{"=" * 50}
{memory_contents_str}
{"=" * 50}

原始标签集合：{", ".join(sorted(all_tags))}

请完成以下任务：
1. 分析这些记忆的共同主题和关键信息
2. 将它们合并成一个连贯、完整的记忆
3. 生成新的标签列表（保留重要标签，去除冗余，可以添加新的概括性标签）
4. 确保合并后的记忆保留了所有重要信息
5. **重要**：越近期的记忆权重越高，优先保留最新记忆中的信息

请将合并结果放在 <merged_memory> 标签内，使用JSON格式：

<merged_memory>
{{
  "content": "合并后的记忆内容，可以是多行文本",
  "tags": ["标签1", "标签2", "标签3"]
}}
</merged_memory>

注意：
- 内容要全面但简洁
- 标签要准确反映内容主题
- 保持专业和客观的语气
- 最近的记忆信息优先级更高
- 只输出 <merged_memory> 标签内的内容，不要有其他说明
- JSON格式必须有效，字符串中的换行符使用 \\n 表示
"""

        try:
            if self.platform is None:
                raise ValueError("Platform is not initialized")

            # 调用大模型 - 收集完整响应
            response_parts = []
            for chunk_type, chunk_content in self.platform.chat(prompt):
                # 只收集 content 类型
                if chunk_type == "content":
                    response_parts.append(chunk_content)
            response = "".join(response_parts)

            # 解析响应
            import re

            from jarvis.jarvis_utils.jsonnet_compat import loads as json5_loads

            # 提取 <merged_memory> 标签内的内容
            json_match = re.search(
                r"<merged_memory>(.*?)</merged_memory>",
                response,
                re.DOTALL | re.IGNORECASE,
            )

            if json_match:
                json_content = json_match.group(1).strip()
                try:
                    result = json5_loads(json_content)
                    return {
                        "content": result.get("content", ""),
                        "tags": result.get("tags", []),
                        "type": memories[0].get("type", "unknown"),
                        "merged_from": [m.get("id", "") for m in memories],
                    }
                except (ValueError, Exception) as e:
                    raise ValueError(f"无法解析JSON内容: {str(e)}")
            else:
                raise ValueError("无法从模型响应中提取 <merged_memory> 标签内容")

        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 调用大模型合并记忆失败: {str(e)}")
            # 返回 None 表示合并失败，跳过这组记忆
            return None

    def _merge_memories_batch_with_llm(
        self, groups: List[List[Dict[str, Any]]]
    ) -> List[Optional[Dict[str, Any]]]:
        """使用大模型批量合并多个记忆组。

        将多个独立的小组打包进一次 LLM 调用，模型对每个组分别输出一个
        <merged_memory> 块，从而大幅减少小组合并时的调用次数（省去每次
        调用的固定开销）。返回与输入 groups 一一对应的合并结果列表，
        某组失败时对应位置为 None。
        """
        # 准备每个组的输入内容
        group_inputs = []
        for idx, memories in enumerate(groups, start=1):
            sorted_memories = sorted(
                memories, key=lambda m: m.get("created_at", ""), reverse=True
            )
            parts = []
            all_tags = set()
            for mem in sorted_memories:
                parts.append(
                    f"记忆ID: {mem.get('id', '未知')}\n"
                    f"创建时间: {mem.get('created_at', '未知')}\n"
                    f"标签: {', '.join(mem.get('tags', []))}\n"
                    f"内容:\n{mem.get('content', '')}"
                )
                all_tags.update(mem.get("tags", []))
            group_inputs.append(
                {
                    "idx": idx,
                    "contents": (("=" * 50) + "\n").join(parts),
                    "tags": ", ".join(sorted(all_tags)),
                    "count": len(memories),
                }
            )

        # 构造批量 prompt
        prompt_lines = [
            f"请将以下 {len(groups)} 组相关记忆分别合并，每组独立合并成一个综合性的记忆。",
            "",
        ]
        for gi in group_inputs:
            prompt_lines.append(f"【组 {gi['idx']}】（共 {gi['count']} 条记忆）")
            prompt_lines.append("原始记忆（按时间从新到旧排序）：")
            prompt_lines.append("=" * 50)
            prompt_lines.append(gi["contents"])
            prompt_lines.append("=" * 50)
            prompt_lines.append(f"原始标签集合：{gi['tags']}")
            prompt_lines.append("")
        prompt_lines.extend(
            [
                "请对每一组分别完成以下任务：",
                "1. 分析该组记忆的共同主题和关键信息",
                "2. 将它们合并成一个连贯、完整的记忆",
                "3. 生成新的标签列表（保留重要标签，去除冗余，可以添加新的概括性标签）",
                "4. 确保合并后的记忆保留了所有重要信息",
                "5. **重要**：越近期的记忆权重越高，优先保留最新记忆中的信息",
                "",
                "请将每组的结果放在对应的 <merged_memory> 标签内，使用JSON格式，并用组编号区分：",
                "",
                "<merged_memory>",
                "{",
                '  "group": 1,',
                '  "content": "组1合并后的记忆内容，可以是多行文本",',
                '  "tags": ["标签1", "标签2", "标签3"]',
                "}",
                "</merged_memory>",
                "",
                "<merged_memory>",
                "{",
                '  "group": 2,',
                '  "content": "组2合并后的记忆内容",',
                '  "tags": ["标签1", "标签2"]',
                "}",
                "</merged_memory>",
                "",
                "注意：",
                "- 每组内容要全面但简洁",
                "- 标签要准确反映内容主题",
                "- 保持专业和客观的语气",
                "- 最近的记忆信息优先级更高",
                "- 必须为每一组都输出一个 <merged_memory> 块，且 group 字段与组编号对应",
                "- 只输出 <merged_memory> 标签内的内容，不要有其他说明",
                "- JSON格式必须有效，字符串中的换行符使用 \\n 表示",
            ]
        )
        prompt = "\n".join(prompt_lines)

        results: List[Optional[Dict[str, Any]]] = [None] * len(groups)
        try:
            if self.platform is None:
                raise ValueError("Platform is not initialized")

            # 调用大模型 - 收集完整响应
            response_parts = []
            for chunk_type, chunk_content in self.platform.chat(prompt):
                if chunk_type == "content":
                    response_parts.append(chunk_content)
            response = "".join(response_parts)

            # 解析响应：提取所有 <merged_memory> 块
            import re

            from jarvis.jarvis_utils.jsonnet_compat import loads as json5_loads

            blocks = re.findall(
                r"<merged_memory>(.*?)</merged_memory>",
                response,
                re.DOTALL | re.IGNORECASE,
            )
            for block in blocks:
                try:
                    result = json5_loads(block.strip())
                    group_idx = result.get("group")
                    if group_idx is None:
                        continue
                    # 组编号是 1-based，转成 0-based 索引
                    pos = int(group_idx) - 1
                    if 0 <= pos < len(groups):
                        results[pos] = {
                            "content": result.get("content", ""),
                            "tags": result.get("tags", []),
                            "type": groups[pos][0].get("type", "unknown"),
                            "merged_from": [m.get("id", "") for m in groups[pos]],
                        }
                except (ValueError, Exception):
                    continue
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 调用大模型批量合并记忆失败: {str(e)}")

        return results

    def organize_memories(
        self,
        memory_type: str,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        整理指定类型的记忆

        参数：
            memory_type: 记忆类型
            dry_run: 是否只进行模拟运行

        返回：
            整理结果统计
        """
        PrettyOutput.auto_print(f"ℹ️ 开始整理{memory_type}类型的记忆，最小重叠标签数: 2")

        # 加载记忆
        memories = self._load_memories(memory_type)
        if not memories:
            PrettyOutput.auto_print("ℹ️ 没有找到需要整理的记忆")
            return {"processed": 0, "merged": 0}

        PrettyOutput.auto_print(f"ℹ️ 加载了 {len(memories)} 个记忆")

        # 统计信息
        stats = {
            "total_memories": len(memories),
            "processed_groups": 0,
            "merged_memories": 0,
            "created_memories": 0,
        }

        # 使用固定的最小重叠数2
        # 创建一个标记已删除记忆的集合
        deleted_indices = set()

        # 过滤掉已删除的记忆
        active_memories = [
            (i, mem) for i, mem in enumerate(memories) if i not in deleted_indices
        ]
        if active_memories:
            # 创建索引映射：原始索引 -> 活跃索引
            active_memory_list = [mem for _, mem in active_memories]

            overlap_groups = self._find_overlapping_memories(active_memory_list, 2)

            if 2 in overlap_groups:
                groups = overlap_groups[2]
                PrettyOutput.auto_print(
                    f"ℹ️ 发现 {len(groups)} 个具有 2 个重叠标签的记忆组"
                )

                # 批量合并参数：小组（<= 4 条）打包成批调用，大组单独调用
                # 每批小组数上限（防止单批输出过长）
                BATCH_MAX_GROUPS = 5
                BATCH_MAX_GROUP_SIZE = 4

                # 基于 token 预算动态分批：预留 20% 给输出，避免输入超模型上限
                try:
                    max_input_tokens = get_max_input_token_count()
                except Exception:
                    max_input_tokens = 0
                batch_token_budget = (
                    int(max_input_tokens * 0.8) if max_input_tokens > 0 else 0
                )

                # 预处理所有组：按原顺序贪心去重（跳过含已删除记忆的组），并转换索引
                pending_groups = []  # (original_indices, group_memories)
                pre_deleted = set()
                for group in groups:
                    original_indices = set()
                    for active_idx in group:
                        original_idx = active_memories[active_idx][0]
                        original_indices.add(original_idx)
                    # 贪心去重：若组内任一记忆已删除，跳过
                    if pre_deleted & original_indices:
                        continue
                    group_memories = [memories[i] for i in original_indices]
                    pending_groups.append((original_indices, group_memories))
                    pre_deleted.update(original_indices)

                # 拆分：小组合并进批，大组单独
                small_groups = [
                    pg for pg in pending_groups if len(pg[1]) <= BATCH_MAX_GROUP_SIZE
                ]
                large_groups = [
                    pg for pg in pending_groups if len(pg[1]) > BATCH_MAX_GROUP_SIZE
                ]

                # 批量合并小组：按 token 预算动态分批（同时受每批组数上限约束）
                batches = []
                current_batch = []
                current_tokens = 0
                for pg in small_groups:
                    # 估算该组的输入 token
                    group_text = "\n".join(
                        f"记忆ID: {m.get('id', '')}\n标签: {','.join(m.get('tags', []))}\n内容:{m.get('content', '')}"
                        for m in pg[1]
                    )
                    group_tokens = get_context_token_count(group_text)
                    # 达到组数上限或 token 预算时开新批
                    if current_batch and (
                        len(current_batch) >= BATCH_MAX_GROUPS
                        or (
                            batch_token_budget > 0
                            and current_tokens + group_tokens > batch_token_budget
                        )
                    ):
                        batches.append(current_batch)
                        current_batch = []
                        current_tokens = 0
                    current_batch.append(pg)
                    current_tokens += group_tokens
                if current_batch:
                    batches.append(current_batch)

                for batch in batches:
                    batch_memories = [pg[1] for pg in batch]

                    # 显示将要合并的记忆
                    for original_indices, group_memories in batch:
                        lines = ["", f"准备合并 {len(group_memories)} 个记忆:"]
                        for mem in group_memories:
                            lines.append(
                                f"  - ID: {mem.get('id', '未知')}, "
                                f"标签: {', '.join(mem.get('tags', []))[:50]}..."
                            )
                        PrettyOutput.auto_print(f"ℹ️ {'\n'.join(lines)}")

                    if not dry_run:
                        merged_results = self._merge_memories_batch_with_llm(
                            batch_memories
                        )
                        for (original_indices, group_memories), merged_memory in zip(
                            batch, merged_results
                        ):
                            if merged_memory is None:
                                PrettyOutput.auto_print("  ⚠️ 跳过这组记忆的合并")
                                continue
                            self._save_merged_memory(
                                merged_memory,
                                memory_type,
                                [memories[i] for i in original_indices],
                            )
                            stats["processed_groups"] += 1
                            stats["merged_memories"] += len(original_indices)
                            stats["created_memories"] += 1
                            deleted_indices.update(original_indices)
                    else:
                        PrettyOutput.auto_print("  ℹ️ [模拟运行] 跳过实际合并")

                # 大组单独合并
                for original_indices, group_memories in large_groups:
                    lines = ["", f"准备合并 {len(group_memories)} 个记忆:"]
                    for mem in group_memories:
                        lines.append(
                            f"  - ID: {mem.get('id', '未知')}, "
                            f"标签: {', '.join(mem.get('tags', []))[:50]}..."
                        )
                    PrettyOutput.auto_print(f"ℹ️ {'\n'.join(lines)}")

                    if not dry_run:
                        merged_memory = self._merge_memories_with_llm(group_memories)
                        if merged_memory is None:
                            PrettyOutput.auto_print("  ⚠️ 跳过这组记忆的合并")
                            continue
                        self._save_merged_memory(
                            merged_memory,
                            memory_type,
                            [memories[i] for i in original_indices],
                        )
                        stats["processed_groups"] += 1
                        stats["merged_memories"] += len(original_indices)
                        stats["created_memories"] += 1
                        deleted_indices.update(original_indices)
                    else:
                        PrettyOutput.auto_print("  ℹ️ [模拟运行] 跳过实际合并")

        # 显示统计信息
        PrettyOutput.auto_print("✅ 整理完成！")
        PrettyOutput.auto_print(f"ℹ️ 总记忆数: {stats['total_memories']}")
        PrettyOutput.auto_print(f"ℹ️ 处理的组数: {stats['processed_groups']}")
        PrettyOutput.auto_print(f"ℹ️ 合并的记忆数: {stats['merged_memories']}")
        PrettyOutput.auto_print(f"ℹ️ 创建的新记忆数: {stats['created_memories']}")

        return stats

    def _save_merged_memory(
        self,
        memory: Dict[str, Any],
        memory_type: str,
        original_memories: List[Dict[str, Any]],
    ):
        """保存合并后的记忆并删除原始记忆"""
        import uuid
        from datetime import datetime

        # 生成新的记忆ID
        memory["id"] = f"merged_{uuid.uuid4().hex[:8]}"
        memory["created_at"] = datetime.now().isoformat()
        memory["updated_at"] = datetime.now().isoformat()
        # 记录作用域与性质（兼容平铺名解析）
        if "/" in memory_type:
            scope, nature = memory_type.split("/", 1)
        elif "_" in memory_type:
            scope, nature = memory_type.split("_", 1)
        else:
            scope, nature = memory_type, "long_term"
        memory["memory_type"] = scope
        memory["nature"] = nature

        # 确定保存路径
        memory_dir = self._resolve_memory_dir(memory_type)

        memory_dir.mkdir(parents=True, exist_ok=True)

        # 保存新记忆
        new_file = memory_dir / f"{memory['id']}.json"
        with open(new_file, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)

        PrettyOutput.auto_print(
            f"✅ 创建新记忆: {memory['id']} (标签: {', '.join(memory['tags'][:3])}...)"
        )

        # 删除原始记忆文件（先汇总日志，最后统一打印）
        info_lines: List[str] = []
        warn_lines: List[str] = []
        for orig_memory in original_memories:
            if "file_path" in orig_memory:
                try:
                    file_path = Path(orig_memory["file_path"])
                    if file_path.exists():
                        file_path.unlink()
                        info_lines.append(
                            f"删除原始记忆: {orig_memory.get('id', '未知')}"
                        )
                    else:
                        info_lines.append(
                            f"原始记忆文件已不存在，跳过删除: {orig_memory.get('id', '未知')}"
                        )
                except Exception as e:
                    warn_lines.append(
                        f"删除记忆文件失败 {orig_memory.get('file_path', '')}: {str(e)}"
                    )
        if info_lines:
            joined_info = "\n".join(info_lines)
            PrettyOutput.auto_print(f"ℹ️ {joined_info}")
        if warn_lines:
            joined_warn = "\n".join(warn_lines)
            PrettyOutput.auto_print(f"⚠️ {joined_warn}")

    def export_memories(
        self,
        memory_types: List[str],
        output_file: Path,
        tags: Optional[List[str]] = None,
    ) -> int:
        """
        导出指定类型的记忆到文件

        参数：
            memory_types: 要导出的记忆类型列表
            output_file: 输出文件路径
            tags: 可选的标签过滤器

        返回：
            导出的记忆数量
        """
        all_memories = []
        progress_lines: List[str] = []

        for memory_type in memory_types:
            progress_lines.append(f"正在导出 {memory_type} 类型的记忆...")
            memories = self._load_memories(memory_type)

            # 如果指定了标签，进行过滤
            if tags:
                filtered_memories = []
                for memory in memories:
                    memory_tags = set(memory.get("tags", []))
                    if any(tag in memory_tags for tag in tags):
                        filtered_memories.append(memory)
                memories = filtered_memories

            # 添加记忆类型信息并移除文件路径
            for memory in memories:
                if "/" in memory_type:
                    scope, nature = memory_type.split("/", 1)
                elif "_" in memory_type:
                    scope, nature = memory_type.split("_", 1)
                else:
                    scope, nature = memory_type, "long_term"
                memory["memory_type"] = scope
                memory["nature"] = nature
                memory.pop("file_path", None)

            all_memories.extend(memories)
            progress_lines.append(f"从 {memory_type} 导出了 {len(memories)} 个记忆")

        # 统一展示导出进度日志
        if progress_lines:
            joined_progress = "\n".join(progress_lines)
            PrettyOutput.auto_print(f"ℹ️ {joined_progress}")

        # 保存到文件
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_memories, f, ensure_ascii=False, indent=2)

        PrettyOutput.auto_print(
            f"✅ 成功导出 {len(all_memories)} 个记忆到 {output_file}"
        )

        return len(all_memories)

    def import_memories(
        self,
        input_file: Path,
        overwrite: bool = False,
    ) -> Dict[str, int]:
        """
        从文件导入记忆

        参数：
            input_file: 输入文件路径
            overwrite: 是否覆盖已存在的记忆

        返回：
            导入统计 {memory_type: count}
        """
        # 读取记忆文件
        if not input_file.exists():
            raise FileNotFoundError(f"导入文件不存在: {input_file}")

        with open(input_file, "r", encoding="utf-8") as f:
            memories = json.load(f)

        if not isinstance(memories, list):
            raise ValueError("导入文件格式错误，应为记忆列表")

        PrettyOutput.auto_print(f"ℹ️ 准备导入 {len(memories)} 个记忆")

        # 统计导入结果
        import_stats: Dict[str, int] = defaultdict(int)
        skipped_count = 0

        for memory in memories:
            memory_type = memory.get("memory_type", memory.get("type"))
            if not memory_type:
                skipped_count += 1
                continue

            # 组装用于目录解析的类型名（优先作用域/性质组合）
            nature = memory.get("nature")
            resolve_type = f"{memory_type}/{nature}" if nature else memory_type

            # 确定保存路径
            try:
                memory_dir = self._resolve_memory_dir(resolve_type)
            except ValueError:
                PrettyOutput.auto_print(f"⚠️ 跳过不支持的记忆类型: {memory_type}")
                skipped_count += 1
                continue

            memory_dir.mkdir(parents=True, exist_ok=True)

            # 检查是否已存在
            memory_id = memory.get("id")
            if not memory_id:
                import uuid

                memory_id = f"imported_{uuid.uuid4().hex[:8]}"
                memory["id"] = memory_id

            memory_file = memory_dir / f"{memory_id}.json"

            if memory_file.exists() and not overwrite:
                PrettyOutput.auto_print(f"ℹ️ 跳过已存在的记忆: {memory_id}")
                skipped_count += 1
                continue

            # 保存记忆
            with open(memory_file, "w", encoding="utf-8") as f:
                # 清理记忆数据
                if "/" in resolve_type:
                    scope, nature = resolve_type.split("/", 1)
                elif "_" in resolve_type:
                    scope, nature = resolve_type.split("_", 1)
                else:
                    scope, nature = resolve_type, "long_term"
                clean_memory = {
                    "id": memory["id"],
                    "memory_type": scope,
                    "nature": nature,
                    "tags": memory.get("tags", []),
                    "content": memory.get("content", ""),
                    "created_at": memory.get("created_at", ""),
                }
                if "merged_from" in memory:
                    clean_memory["merged_from"] = memory["merged_from"]

                json.dump(clean_memory, f, ensure_ascii=False, indent=2)

            import_stats[memory_type] += 1

        # 显示导入结果
        PrettyOutput.auto_print("✅ 导入完成！")
        if import_stats:
            lines = [
                f"{memory_type}: 导入了 {count} 个记忆"
                for memory_type, count in import_stats.items()
            ]
            joined_lines = "\n".join(lines)
            PrettyOutput.auto_print(f"ℹ️ {joined_lines}")

        if skipped_count > 0:
            PrettyOutput.auto_print(f"⚠️ 跳过了 {skipped_count} 个记忆")

        return dict(import_stats)


app = typer.Typer(help="记忆整理工具 - 合并具有相似标签的记忆")


@app.command("organize")
def organize(
    memory_type: str = typer.Option(
        "project_long_term",
        "--type",
        help="要整理的记忆类型（project_long_term 或 global_long_term）",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="模拟运行，只显示将要进行的操作但不实际执行",
    ),
    llm_group: Optional[str] = typer.Option(
        None, "-g", "--llm-group", help="使用的模型组，覆盖配置文件中的设置"
    ),
):
    """
    整理和合并具有相似标签的记忆。

    示例：

    # 整理项目长期记忆
    jarvis-memory-organizer organize --type project_long_term

    # 整理全局长期记忆，模拟运行
    jarvis-memory-organizer organize --type global_long_term --dry-run

    # 使用默认设置整理项目记忆
    jarvis-memory-organizer organize
    """
    # 验证参数
    set_llm_group(llm_group)
    try:
        organizer = MemoryOrganizer()
        organizer._resolve_memory_dir(memory_type)
    except ValueError:
        PrettyOutput.auto_print(
            f"❌ 错误：不支持的记忆类型 '{memory_type}'，"
            "支持 project_long_term / global_long_term / project/long_term 等"
        )
        raise typer.Exit(1)

    # 创建整理器并执行
    try:
        organizer = MemoryOrganizer()
        stats = organizer.organize_memories(memory_type=memory_type, dry_run=dry_run)

        # 根据结果返回适当的退出码
        if stats.get("processed_groups", 0) > 0 or dry_run:
            raise typer.Exit(0)
        else:
            raise typer.Exit(0)  # 即使没有处理也是正常退出

    except typer.Exit:
        # typer.Exit 是正常的退出方式，直接传播
        raise
    except Exception as e:
        PrettyOutput.auto_print(f"❌ 记忆整理失败: {str(e)}")
        raise typer.Exit(1)


@app.command("export")
def export(
    output: Path = typer.Argument(
        ...,
        help="导出文件路径（JSON格式）",
    ),
    memory_types: List[str] = typer.Option(
        ["project_long_term", "global_long_term"],
        "--type",
        "-t",
        help="要导出的记忆类型（可多次指定）",
    ),
    tags: Optional[List[str]] = typer.Option(
        None,
        "--tag",
        help="按标签过滤（可多次指定）",
    ),
):
    """
    导出记忆到文件。

    示例：

    # 导出所有记忆到文件
    jarvis-memory-organizer export memories.json

    # 只导出项目长期记忆
    jarvis-memory-organizer export project_memories.json -t project_long_term

    # 导出带特定标签的记忆
    jarvis-memory-organizer export tagged_memories.json --tag Python --tag API
    """
    try:
        organizer = MemoryOrganizer()

        # 验证记忆类型（先收集无效类型，统一打印一次）
        invalid_types = []
        for mt in memory_types:
            try:
                organizer._resolve_memory_dir(mt)
            except ValueError:
                invalid_types.append(mt)
        if invalid_types:
            invalid_str = ", ".join(f"'{mt}'" for mt in invalid_types)
            PrettyOutput.auto_print(f"❌ 错误：不支持的记忆类型: {invalid_str}")
            raise typer.Exit(1)

        count = organizer.export_memories(
            memory_types=memory_types,
            output_file=output,
            tags=tags,
        )

        if count > 0:
            raise typer.Exit(0)
        else:
            PrettyOutput.auto_print("⚠️ 没有找到要导出的记忆")
            raise typer.Exit(0)

    except Exception as e:
        PrettyOutput.auto_print(f"❌ 导出失败: {str(e)}")
        raise typer.Exit(1)


@app.command("import")
def import_memories(
    input: Path = typer.Argument(
        ...,
        help="导入文件路径（JSON格式）",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        "-o",
        help="覆盖已存在的记忆",
    ),
):
    """
    从文件导入记忆。

    示例：

    # 导入记忆文件
    jarvis-memory-organizer import memories.json

    # 导入并覆盖已存在的记忆
    jarvis-memory-organizer import memories.json --overwrite
    """
    try:
        organizer = MemoryOrganizer()

        stats = organizer.import_memories(
            input_file=input,
            overwrite=overwrite,
        )

        total_imported = sum(stats.values())
        if total_imported > 0:
            raise typer.Exit(0)
        else:
            PrettyOutput.auto_print("⚠️ 没有导入任何记忆")
            raise typer.Exit(0)

    except FileNotFoundError as e:
        PrettyOutput.auto_print(f"❌ {str(e)}")
        raise typer.Exit(1)
    except Exception as e:
        PrettyOutput.auto_print(f"❌ 导入失败: {str(e)}")
        raise typer.Exit(1)


def main():
    """Application entry point"""
    # 统一初始化环境
    init_env()
    app()


if __name__ == "__main__":
    main()
