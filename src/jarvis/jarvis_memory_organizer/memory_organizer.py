#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记忆整理工具 - 用于合并具有相似标签的记忆

该工具会查找具有高度重叠标签的记忆，并使用大模型将它们合并成一个新的记忆。
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Any, Optional

import typer

from jarvis.jarvis_utils.config import (
    get_data_dir,
    get_normal_platform_name,
    get_normal_model_name,
)
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.utils import init_env


class MemoryOrganizer:
    """记忆整理器，用于合并具有相似标签的记忆"""

    def __init__(self, llm_group: Optional[str] = None):
        """初始化记忆整理器"""
        self.project_memory_dir = Path(".jarvis/memory")
        self.global_memory_dir = Path(get_data_dir()) / "memory"

        # 统一使用 normal 平台与模型
        platform_name_func = get_normal_platform_name
        model_name_func = get_normal_model_name

        # 确定平台和模型
        platform_name = platform_name_func(model_group_override=llm_group)
        model_name = model_name_func(model_group_override=llm_group)

        # 获取当前配置的平台实例
        registry = PlatformRegistry.get_global_platform_registry()
        self.platform = registry.create_platform(platform_name)
        if self.platform and model_name:
            self.platform.set_model_name(model_name)

    def _get_memory_files(self, memory_type: str) -> List[Path]:
        """获取指定类型的所有记忆文件"""
        if memory_type == "project_long_term":
            memory_dir = self.project_memory_dir
        elif memory_type == "global_long_term":
            memory_dir = self.global_memory_dir / memory_type
        else:
            raise ValueError(f"不支持的记忆类型: {memory_type}")

        if not memory_dir.exists():
            return []

        return list(memory_dir.glob("*.json"))

    def _load_memories(self, memory_type: str) -> List[Dict[str, Any]]:
        """加载指定类型的所有记忆"""
        memories = []
        memory_files = self._get_memory_files(memory_type)
        error_lines: list[str] = []

        for memory_file in memory_files:
            try:
                with open(memory_file, "r", encoding="utf-8") as f:
                    memory_data = json.load(f)
                    memory_data["file_path"] = str(memory_file)
                    memories.append(memory_data)
            except Exception as e:
                error_lines.append(f"读取记忆文件 {memory_file} 失败: {str(e)}")

        if error_lines:
            PrettyOutput.print("\n".join(error_lines), OutputType.WARNING)

        return memories

    def _find_overlapping_memories(
        self, memories: List[Dict[str, Any]], min_overlap: int
    ) -> Dict[int, List[Set[int]]]:
        """
        查找具有重叠标签的记忆组

        返回：{重叠数量: [记忆索引集合列表]}
        """
        # 构建标签到记忆索引的映射
        tag_to_memories = defaultdict(set)
        for i, memory in enumerate(memories):
            for tag in memory.get("tags", []):
                tag_to_memories[tag].add(i)

        # 查找具有共同标签的记忆对
        overlap_groups = defaultdict(list)
        processed_groups = set()

        # 对每对记忆计算标签重叠数
        for i in range(len(memories)):
            for j in range(i + 1, len(memories)):
                tags_i = set(memories[i].get("tags", []))
                tags_j = set(memories[j].get("tags", []))
                overlap_count = len(tags_i & tags_j)

                if overlap_count >= min_overlap:
                    # 查找包含这两个记忆的最大组
                    group = {i, j}

                    # 扩展组，包含所有与组内记忆有足够重叠的记忆
                    changed = True
                    while changed:
                        changed = False
                        for k in range(len(memories)):
                            if k not in group:
                                # 检查与组内所有记忆的最小重叠数
                                min_overlap_with_group = min(
                                    len(
                                        set(memories[k].get("tags", []))
                                        & set(memories[m].get("tags", []))
                                    )
                                    for m in group
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
{"="*50}
{memory_contents_str}
{"="*50}

原始标签集合：{', '.join(sorted(all_tags))}

请完成以下任务：
1. 分析这些记忆的共同主题和关键信息
2. 将它们合并成一个连贯、完整的记忆
3. 生成新的标签列表（保留重要标签，去除冗余，可以添加新的概括性标签）
4. 确保合并后的记忆保留了所有重要信息
5. **重要**：越近期的记忆权重越高，优先保留最新记忆中的信息

请将合并结果放在 <merged_memory> 标签内，使用YAML格式：

<merged_memory>
content: |
  合并后的记忆内容
  可以是多行文本
tags:
  - 标签1
  - 标签2
  - 标签3
</merged_memory>

注意：
- 内容要全面但简洁
- 标签要准确反映内容主题
- 保持专业和客观的语气
- 最近的记忆信息优先级更高
- 只输出 <merged_memory> 标签内的内容，不要有其他说明
"""

        try:
            # 调用大模型 - 收集完整响应
            response_parts = []
            for chunk in self.platform.chat(prompt):  # type: ignore
                response_parts.append(chunk)
            response = "".join(response_parts)

            # 解析响应
            import re
            import yaml

            # 提取 <merged_memory> 标签内的内容
            yaml_match = re.search(
                r"<merged_memory>(.*?)</merged_memory>",
                response,
                re.DOTALL | re.IGNORECASE,
            )

            if yaml_match:
                yaml_content = yaml_match.group(1).strip()
                try:
                    result = yaml.safe_load(yaml_content)
                    return {
                        "content": result.get("content", ""),
                        "tags": result.get("tags", []),
                        "type": memories[0].get("type", "unknown"),
                        "merged_from": [m.get("id", "") for m in memories],
                    }
                except yaml.YAMLError as e:
                    raise ValueError(f"无法解析YAML内容: {str(e)}")
            else:
                raise ValueError("无法从模型响应中提取 <merged_memory> 标签内容")

        except Exception as e:
            PrettyOutput.print(f"调用大模型合并记忆失败: {str(e)}", OutputType.WARNING)
            # 返回 None 表示合并失败，跳过这组记忆
            return None

    def organize_memories(
        self,
        memory_type: str,
        min_overlap: int = 2,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        整理指定类型的记忆

        参数：
            memory_type: 记忆类型
            min_overlap: 最小标签重叠数
            dry_run: 是否只进行模拟运行

        返回：
            整理结果统计
        """
        PrettyOutput.print(
            f"开始整理{memory_type}类型的记忆，最小重叠标签数: {min_overlap}",
            OutputType.INFO,
        )

        # 加载记忆
        memories = self._load_memories(memory_type)
        if not memories:
            PrettyOutput.print("没有找到需要整理的记忆", OutputType.INFO)
            return {"processed": 0, "merged": 0}

        PrettyOutput.print(f"加载了 {len(memories)} 个记忆", OutputType.INFO)

        # 统计信息
        stats = {
            "total_memories": len(memories),
            "processed_groups": 0,
            "merged_memories": 0,
            "created_memories": 0,
        }

        # 从高重叠度开始处理
        max_tags = max(len(m.get("tags", [])) for m in memories)

        # 创建一个标记已删除记忆的集合
        deleted_indices = set()

        for overlap_count in range(min(max_tags, 5), min_overlap - 1, -1):
            # 过滤掉已删除的记忆
            active_memories = [
                (i, mem) for i, mem in enumerate(memories) if i not in deleted_indices
            ]
            if not active_memories:
                break

            # 创建索引映射：原始索引 -> 活跃索引
            active_memory_list = [mem for _, mem in active_memories]

            overlap_groups = self._find_overlapping_memories(
                active_memory_list, overlap_count
            )

            if overlap_count in overlap_groups:
                groups = overlap_groups[overlap_count]
                PrettyOutput.print(
                    f"\n发现 {len(groups)} 个具有 {overlap_count} 个重叠标签的记忆组",
                    OutputType.INFO,
                )

                for group in groups:
                    # 将活跃索引转换回原始索引
                    original_indices = set()
                    for active_idx in group:
                        original_idx = active_memories[active_idx][0]
                        original_indices.add(original_idx)

                    group_memories = [memories[i] for i in original_indices]

                    # 显示将要合并的记忆（先拼接后统一打印，避免循环逐条输出）
                    lines = ["", f"准备合并 {len(group_memories)} 个记忆:"]
                    for mem in group_memories:
                        lines.append(
                            f"  - ID: {mem.get('id', '未知')}, "
                            f"标签: {', '.join(mem.get('tags', []))[:50]}..."
                        )
                    PrettyOutput.print("\n".join(lines), OutputType.INFO)

                    if not dry_run:
                        # 合并记忆
                        merged_memory = self._merge_memories_with_llm(group_memories)

                        # 如果合并失败，跳过这组
                        if merged_memory is None:
                            PrettyOutput.print(
                                "  跳过这组记忆的合并", OutputType.WARNING
                            )
                            continue

                        # 保存新记忆
                        self._save_merged_memory(
                            merged_memory,
                            memory_type,
                            [memories[i] for i in original_indices],
                        )

                        stats["processed_groups"] += 1
                        stats["merged_memories"] += len(original_indices)
                        stats["created_memories"] += 1

                        # 标记这些记忆已被删除
                        deleted_indices.update(original_indices)
                    else:
                        PrettyOutput.print("  [模拟运行] 跳过实际合并", OutputType.INFO)

        # 显示统计信息
        PrettyOutput.print("\n整理完成！", OutputType.SUCCESS)
        PrettyOutput.print(f"总记忆数: {stats['total_memories']}", OutputType.INFO)
        PrettyOutput.print(f"处理的组数: {stats['processed_groups']}", OutputType.INFO)
        PrettyOutput.print(f"合并的记忆数: {stats['merged_memories']}", OutputType.INFO)
        PrettyOutput.print(
            f"创建的新记忆数: {stats['created_memories']}", OutputType.INFO
        )

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
        memory["type"] = memory_type

        # 确定保存路径
        if memory_type == "project_long_term":
            memory_dir = self.project_memory_dir
        else:
            memory_dir = self.global_memory_dir / memory_type

        memory_dir.mkdir(parents=True, exist_ok=True)

        # 保存新记忆
        new_file = memory_dir / f"{memory['id']}.json"
        with open(new_file, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)

        PrettyOutput.print(
            f"创建新记忆: {memory['id']} (标签: {', '.join(memory['tags'][:3])}...)",
            OutputType.SUCCESS,
        )

        # 删除原始记忆文件（先汇总日志，最后统一打印）
        info_lines: list[str] = []
        warn_lines: list[str] = []
        for orig_memory in original_memories:
            if "file_path" in orig_memory:
                try:
                    file_path = Path(orig_memory["file_path"])
                    if file_path.exists():
                        file_path.unlink()
                        info_lines.append(f"删除原始记忆: {orig_memory.get('id', '未知')}")
                    else:
                        info_lines.append(
                            f"原始记忆文件已不存在，跳过删除: {orig_memory.get('id', '未知')}"
                        )
                except Exception as e:
                    warn_lines.append(
                        f"删除记忆文件失败 {orig_memory.get('file_path', '')}: {str(e)}"
                    )
        if info_lines:
            PrettyOutput.print("\n".join(info_lines), OutputType.INFO)
        if warn_lines:
            PrettyOutput.print("\n".join(warn_lines), OutputType.WARNING)

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
        progress_lines: list[str] = []

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
                memory["memory_type"] = memory_type
                memory.pop("file_path", None)

            all_memories.extend(memories)
            progress_lines.append(f"从 {memory_type} 导出了 {len(memories)} 个记忆")

        # 统一展示导出进度日志
        if progress_lines:
            PrettyOutput.print("\n".join(progress_lines), OutputType.INFO)

        # 保存到文件
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_memories, f, ensure_ascii=False, indent=2)

        PrettyOutput.print(
            f"成功导出 {len(all_memories)} 个记忆到 {output_file}", OutputType.SUCCESS
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

        PrettyOutput.print(f"准备导入 {len(memories)} 个记忆", OutputType.INFO)

        # 统计导入结果
        import_stats: Dict[str, int] = defaultdict(int)
        skipped_count = 0

        for memory in memories:
            memory_type = memory.get("memory_type", memory.get("type"))
            if not memory_type:
                skipped_count += 1
                continue

            # 确定保存路径
            if memory_type == "project_long_term":
                memory_dir = self.project_memory_dir
            elif memory_type == "global_long_term":
                memory_dir = self.global_memory_dir / memory_type
            else:
                PrettyOutput.print(
                    f"跳过不支持的记忆类型: {memory_type}", OutputType.WARNING
                )
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
                PrettyOutput.print(f"跳过已存在的记忆: {memory_id}", OutputType.INFO)
                skipped_count += 1
                continue

            # 保存记忆
            with open(memory_file, "w", encoding="utf-8") as f:
                # 清理记忆数据
                clean_memory = {
                    "id": memory["id"],
                    "type": memory_type,
                    "tags": memory.get("tags", []),
                    "content": memory.get("content", ""),
                    "created_at": memory.get("created_at", ""),
                }
                if "merged_from" in memory:
                    clean_memory["merged_from"] = memory["merged_from"]

                json.dump(clean_memory, f, ensure_ascii=False, indent=2)

            import_stats[memory_type] += 1

        # 显示导入结果
        PrettyOutput.print("\n导入完成！", OutputType.SUCCESS)
        if import_stats:
            lines = [f"{memory_type}: 导入了 {count} 个记忆" for memory_type, count in import_stats.items()]
            PrettyOutput.print("\n".join(lines), OutputType.INFO)

        if skipped_count > 0:
            PrettyOutput.print(f"跳过了 {skipped_count} 个记忆", OutputType.WARNING)

        return dict(import_stats)


app = typer.Typer(help="记忆整理工具 - 合并具有相似标签的记忆")


@app.command("organize")
def organize(
    memory_type: str = typer.Option(
        "project_long_term",
        "--type",
        help="要整理的记忆类型（project_long_term 或 global_long_term）",
    ),
    min_overlap: int = typer.Option(
        2,
        "--min-overlap",
        help="最小标签重叠数，必须大于等于2",
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

    # 整理项目长期记忆，最小重叠标签数为3
    jarvis-memory-organizer organize --type project_long_term --min-overlap 3

    # 整理全局长期记忆，模拟运行
    jarvis-memory-organizer organize --type global_long_term --dry-run

    # 使用默认设置（最小重叠数2）整理项目记忆
    jarvis-memory-organizer organize
    """
    # 验证参数
    if memory_type not in ["project_long_term", "global_long_term"]:
        PrettyOutput.print(
            f"错误：不支持的记忆类型 '{memory_type}'，请选择 'project_long_term' 或 'global_long_term'",
            OutputType.ERROR,
        )
        raise typer.Exit(1)

    if min_overlap < 2:
        PrettyOutput.print("错误：最小重叠数必须大于等于2", OutputType.ERROR)
        raise typer.Exit(1)

    # 创建整理器并执行
    try:
        organizer = MemoryOrganizer(llm_group=llm_group)
        stats = organizer.organize_memories(
            memory_type=memory_type, min_overlap=min_overlap, dry_run=dry_run
        )

        # 根据结果返回适当的退出码
        if stats.get("processed_groups", 0) > 0 or dry_run:
            raise typer.Exit(0)
        else:
            raise typer.Exit(0)  # 即使没有处理也是正常退出

    except typer.Exit:
        # typer.Exit 是正常的退出方式，直接传播
        raise
    except Exception as e:
        PrettyOutput.print(f"记忆整理失败: {str(e)}", OutputType.ERROR)
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
        valid_types = ["project_long_term", "global_long_term"]
        invalid_types = [mt for mt in memory_types if mt not in valid_types]
        if invalid_types:
            PrettyOutput.print(
                "错误：不支持的记忆类型: " + ", ".join(f"'{mt}'" for mt in invalid_types),
                OutputType.ERROR,
            )
            raise typer.Exit(1)

        count = organizer.export_memories(
            memory_types=memory_types,
            output_file=output,
            tags=tags,
        )

        if count > 0:
            raise typer.Exit(0)
        else:
            PrettyOutput.print("没有找到要导出的记忆", OutputType.WARNING)
            raise typer.Exit(0)

    except Exception as e:
        PrettyOutput.print(f"导出失败: {str(e)}", OutputType.ERROR)
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
            PrettyOutput.print("没有导入任何记忆", OutputType.WARNING)
            raise typer.Exit(0)

    except FileNotFoundError as e:
        PrettyOutput.print(str(e), OutputType.ERROR)
        raise typer.Exit(1)
    except Exception as e:
        PrettyOutput.print(f"导入失败: {str(e)}", OutputType.ERROR)
        raise typer.Exit(1)


def main():
    """Application entry point"""
    # 统一初始化环境
    init_env("欢迎使用记忆整理工具！")
    app()


if __name__ == "__main__":
    main()
