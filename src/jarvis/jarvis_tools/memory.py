# -*- coding: utf-8 -*-
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from jarvis.jarvis_utils.config import (
    calculate_token_limit,
    get_data_dir,
    get_max_input_token_count,
    get_memory_compress_threshold,
    is_enable_memory_compress,
    is_enable_memory_value_filter,
    save_exception,
)
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.globals import (
    add_short_term_memory,
    clear_short_term_memories,
    get_short_term_memories,
    short_term_memories,
)
from jarvis.jarvis_utils.output import PrettyOutput

# 延迟导入 SmartRetriever 以避免循环依赖
_smart_retriever = None


def _get_smart_retriever():
    """延迟获取 SmartRetriever 实例"""
    global _smart_retriever
    if _smart_retriever is None:
        from jarvis.jarvis_memory_organizer.smart_retrieval import SmartRetriever

        _smart_retriever = SmartRetriever()
    return _smart_retriever


class MemoryTool:
    """统一的记忆管理工具，支持保存、检索和清除记忆"""

    name = "memory"
    description = """统一的记忆管理工具，支持三种操作（每次只执行一种，参数随操作而异）：

1. **save**：把信息存入记忆库（支持批量）。记忆有两个正交维度：memory_type=作用域(project项目/global全局/short_term短期)，nature=性质(long_term长期/procedural程序性how-to/episodic情景归档)。例如 project+long_term=项目长期、global+procedural=全局程序性。可选 importance 标注重要性（high/medium/low，默认走启发式价值过滤），可选 source 标注来源。

2. **retrieve**：检索记忆库中的信息，支持按作用域(memory_type)、性质(nature)与标签过滤、可选语义检索

3. **clear**：按类型/标签/ID 清除指定记忆。注意：清除不可恢复

**要点**：
- 每次只能执行一种操作（save/retrieve/clear）
- 参数随操作类型不同
- save 时系统会自动做写时价值过滤与超长压缩：未显式标注 importance 且内容无价值（过短/纯客套）会被自动过滤；超长内容会做摘要压缩，原始完整内容保留在 original_content。这些是自动机制，无需 Agent 干预。"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["save", "retrieve", "clear"],
                "description": "要执行的操作：save 保存 / retrieve 检索 / clear 清除",
            },
            # save 操作的参数
            "memories": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "memory_type": {
                            "type": "string",
                            "enum": ["project", "global", "short_term"],
                            "description": "记忆作用域：project=项目、global=全局、short_term=短期",
                        },
                        "nature": {
                            "type": "string",
                            "enum": ["long_term", "procedural", "episodic"],
                            "description": "记忆性质：long_term=长期、procedural=程序性(how-to/踩坑经验)、episodic=情景(历史归档)",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "关联标签（用于检索过滤）",
                        },
                        "content": {
                            "type": "string",
                            "description": "要保存的记忆内容",
                        },
                        "importance": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": "重要性标注（可选，默认走启发式价值过滤）",
                        },
                        "source": {
                            "type": "string",
                            "description": "来源标注（可选，如任务名/会话ID）",
                        },
                    },
                    "required": ["memory_type", "tags", "content"],
                },
                "description": "待保存的记忆数组（仅 save 操作使用）",
            },
            # retrieve 操作的参数
            "memory_types": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["project", "global", "short_term", "all"],
                },
                "description": "按作用域过滤记忆（仅 retrieve 使用；all 表示全部作用域）",
            },
            "natures": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["long_term", "procedural", "episodic", "all"],
                },
                "description": "按性质过滤记忆（可选，仅 retrieve 使用；all 表示全部性质）",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "按标签过滤（可选，retrieve 与 clear 操作使用）",
            },
            "limit": {
                "type": "integer",
                "description": "返回结果条数上限（可选，仅 retrieve 操作使用）",
                "minimum": 1,
            },
            "smart_search": {
                "type": "boolean",
                "description": "是否启用语义检索（可选，仅 retrieve 操作使用）",
                "default": False,
            },
            "query": {
                "type": "string",
                "description": "语义检索的查询文本（smart_search=True 且操作为 retrieve 时使用）",
            },
            # clear 操作的参数
            "memory_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要清除的记忆 ID 列表（可选，仅 clear 使用）",
            },
            "confirm": {
                "type": "boolean",
                "description": "确认清除（仅 clear 操作使用；必须为 true 才会执行删除）",
                "default": False,
            },
        },
        "required": ["action"],
    }

    def __init__(self) -> None:
        """初始化记忆管理工具"""
        self.project_memory_dir = Path(".jarvis/memory")
        self.global_memory_dir = Path(get_data_dir()) / "memory"

    def _get_memory_dir(self, memory_type: str, nature: str = "long_term") -> Path:
        """根据作用域(memory_type)与性质(nature)获取存储目录

        作用域：project=项目、global=全局；性质：long_term=长期、procedural=程序性、episodic=情景。
        short_term 存内存不落盘，此处返回其占位目录（实际由调用方处理）。
        """
        if memory_type == "project":
            if nature == "long_term":
                return Path(self.project_memory_dir)
            elif nature == "procedural":
                return Path(self.project_memory_dir) / "procedural"
            elif nature == "episodic":
                return Path(self.project_memory_dir) / "episodic"
        elif memory_type == "global":
            if nature == "long_term":
                return Path(self.global_memory_dir) / "global_long_term"
            elif nature == "procedural":
                return Path(self.global_memory_dir) / "procedural"
            elif nature == "episodic":
                return Path(self.global_memory_dir) / "episodic"
        elif memory_type == "short_term":
            return Path(self.global_memory_dir) / "short_term"
        raise ValueError(f"未知的记忆类型: memory_type={memory_type}, nature={nature}")

    def _generate_memory_id(self) -> str:
        """生成唯一的记忆ID"""
        # 添加微秒级时间戳确保唯一性
        time.sleep(0.001)  # 确保不同记忆有不同的时间戳
        return datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    # ========== save 操作相关方法 ==========

    # 无信息量的客套/占位内容，启发式过滤时丢弃
    _LOW_VALUE_PHRASES = (
        "好的",
        "明白",
        "收到",
        "知道了",
        "了解",
        "嗯",
        "哦",
        "ok",
        "okay",
        "好的，明白",
        "好的明白",
        "好的收到",
        "没问题",
        "可以",
        "行",
        "好",
        "谢谢",
        "感谢",
        "不客气",
        "再见",
        "你好",
        "hello",
        "hi",
        "thanks",
        "done",
        "完成",
        "好的好的",
        "嗯嗯",
        "是的",
        "对",
        "对的",
    )

    def _should_store_memory(self, memory_data: Dict[str, Any]) -> bool:
        """写时记忆价值过滤：判断一条记忆是否值得存储。

        规则：
        1. 用户显式标注 importance（high/medium/low）→ 一律保留（尊重显式意图）。
        2. 未显式标注 → 启发式判断：
           - 去除空白后内容过短（< 8 字符）→ 丢弃
           - 纯客套/占位内容（命中 _LOW_VALUE_PHRASES）→ 丢弃
           - 其余内容保守保留（避免误删有价值信息）。
        3. 过滤仅对落盘/内存存储生效，不影响调用方已收集的标签等副作用。
        """
        # 用户显式标注 importance 时尊重其意图
        if "importance" in memory_data:
            return True

        content = (memory_data.get("content") or "").strip()
        if not content:
            return False

        # 过短内容无信息量
        if len(content) < 8:
            return False

        # 纯客套/占位内容
        lowered = content.lower()
        if lowered in self._LOW_VALUE_PHRASES:
            return False
        for phrase in self._LOW_VALUE_PHRASES:
            if phrase and lowered == phrase:
                return False

        return True

    # 高信号关键词：含这些词的句子在规则式压缩时优先保留
    _HIGH_SIGNAL_KEYWORDS = (
        "决策",
        "结论",
        "决定",
        "选择",
        "偏好",
        "原因",
        "因为",
        "所以",
        "因此",
        "用户",
        "修复",
        "问题",
        "方案",
        "配置",
        "版本",
        "地址",
        "路径",
        "命令",
        "bug",
        "bug",
        "error",
        "错误",
        "注意",
        "重要",
        "必须",
        "禁止",
        "推荐",
        "成功",
        "失败",
        "步骤",
        "流程",
        "结果",
        "目标",
        "实现",
        "新增",
        "删除",
    )

    def _compress_memory_content(self, content: str) -> str:
        """规则式摘要压缩：对超长记忆内容做提取式压缩。

        策略（保留关键信息、控制体积）：
        1. 用 token 估算判断是否超过压缩阈值，未超过则原样返回。
        2. 超过阈值时：
           - 保留开头若干句（背景/上下文）
           - 提取含高信号关键词的句子（决策/结论/偏好/事实等）
           - 保留结尾若干句（结论/总结）
           - 去重后拼接，避免重复句子。
        3. 压缩结果仍可能较长时做字符级截断兜底。

        返回:
            str: 压缩后的内容；未超阈值时返回原内容。
        """
        text = (content or "").strip()
        if not text:
            return text

        try:
            if get_context_token_count(text) <= get_memory_compress_threshold():
                return text
        except Exception:
            # token 估算失败时退化为字符长度判断
            if len(text) <= get_memory_compress_threshold() * 2:
                return text

        # 按句子切分
        import re

        sentences = [s.strip() for s in re.split(r"[。！？!?\n]+", text) if s.strip()]

        # 保留开头 3 句与结尾 3 句
        head = sentences[:3]
        tail = sentences[-3:] if len(sentences) > 6 else []

        # 提取含高信号关键词的句子
        signal = []
        for s in sentences[3:-3] if len(sentences) > 6 else []:
            lowered = s.lower()
            if any(kw in lowered for kw in self._HIGH_SIGNAL_KEYWORDS):
                signal.append(s)

        # 去重（保持顺序）
        seen = set()
        merged = []
        for s in head + signal + tail:
            key = s[:20]
            if key not in seen:
                seen.add(key)
                merged.append(s)

        compressed = "；".join(merged)
        # 字符级兜底截断，防止极端超长
        max_chars = max(600, int(len(text) * 0.6))
        if len(compressed) > max_chars:
            compressed = compressed[:max_chars]
        return compressed

    def _save_single_memory(
        self, memory_data: Dict[str, Any], agent: Any = None
    ) -> Dict[str, Any]:
        """保存单条记忆"""
        memory_type = memory_data["memory_type"]  # 作用域: project/global/short_term
        nature = memory_data.get(
            "nature", "long_term"
        )  # 性质: long_term/procedural/episodic
        tags = memory_data.get("tags", [])
        content = memory_data.get("content", "")

        # 写时记忆价值过滤：未显式标注 importance 且内容无价值时丢弃
        if is_enable_memory_value_filter() and not self._should_store_memory(
            memory_data
        ):
            return {
                "memory_id": None,
                "memory_type": memory_type,
                "nature": nature,
                "tags": tags,
                "storage": "filtered",
                "message": "记忆内容价值不足，已过滤不保存",
            }

        # 存储前压缩：超长内容做规则式摘要，原始内容保留到 original_content
        original_content = content
        if is_enable_memory_compress() and content:
            try:
                compressed = self._compress_memory_content(content)
                if compressed != content:
                    content = compressed
            except Exception:
                # 压缩失败不影响保存，保留原文
                content = original_content

        # 收集记忆标签到 agent 的 memory_tags 属性
        if agent and hasattr(agent, "add_memory_tags") and tags:
            try:
                agent.add_memory_tags(tags)
            except Exception:
                # 添加标签失败不影响保存记忆的主要功能
                pass

        # 生成记忆ID
        memory_id = self._generate_memory_id()

        # 创建记忆对象
        memory_obj = {
            "id": memory_id,
            "memory_type": memory_type,
            "nature": nature,
            "tags": tags,
            "content": content,
            "importance": memory_data.get("importance", "medium"),
            "source": memory_data.get("source", ""),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        # 压缩过时保留原始完整内容，便于必要时查原文
        if content != original_content:
            memory_obj["original_content"] = original_content

        if memory_type == "short_term":
            # 短期记忆保存到全局变量
            add_short_term_memory(memory_obj)

            # 将内容添加到agent的recent_memories列表
            if agent and hasattr(agent, "recent_memories"):
                # 过滤空内容
                if content and content.strip():
                    agent.recent_memories.append(content.strip())
                    # 维护最大10条限制
                    if len(agent.recent_memories) > agent.MAX_RECENT_MEMORIES:
                        agent.recent_memories.pop(0)

            result = {
                "memory_id": memory_id,
                "memory_type": memory_type,
                "nature": nature,
                "tags": tags,
                "storage": "memory",
                "message": f"短期记忆已成功保存到内存，ID: {memory_id}",
            }
        else:
            # 长期记忆保存到文件
            # 获取存储目录并确保存在
            memory_dir = self._get_memory_dir(memory_type, nature)
            memory_dir.mkdir(parents=True, exist_ok=True)

            # 保存记忆文件
            memory_file = memory_dir / f"{memory_id}.json"
            with open(memory_file, "w", encoding="utf-8") as f:
                json.dump(memory_obj, f, ensure_ascii=False, indent=2)

            # 将内容添加到agent的recent_memories列表
            if agent and hasattr(agent, "recent_memories"):
                # 过滤空内容
                if content and content.strip():
                    agent.recent_memories.append(content.strip())
                    # 维护最大10条限制
                    if len(agent.recent_memories) > agent.MAX_RECENT_MEMORIES:
                        agent.recent_memories.pop(0)

            result = {
                "memory_id": memory_id,
                "memory_type": memory_type,
                "nature": nature,
                "tags": tags,
                "file_path": str(memory_file),
                "message": f"记忆已成功保存，ID: {memory_id}",
            }

        return result

    def _execute_save(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行保存记忆操作"""
        try:
            # 获取agent实例（v1.0协议通过arguments注入）
            agent = args.get("agent")
            memories = args.get("memories", [])

            if not memories:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "没有提供要保存的记忆",
                }

            results = []
            success_count = 0
            failed_count = 0

            # 保存每条记忆
            for i, memory_data in enumerate(memories):
                try:
                    result = self._save_single_memory(memory_data, agent)
                    results.append(result)
                    success_count += 1

                    memory_data["memory_type"]
                    memory_data.get("tags", [])

                except Exception as e:
                    failed_count += 1
                    error_msg = f"保存第 {i + 1} 条记忆失败: {str(e)}"
                    PrettyOutput.auto_print(f"❌ {error_msg}")
                    results.append(
                        {
                            "error": error_msg,
                            "memory_type": memory_data.get("memory_type", "unknown"),
                            "tags": memory_data.get("tags", []),
                        }
                    )

            # 统一打印固定到pin_content的汇总信息
            if (
                agent
                and hasattr(agent, "pin_content")
                and agent.pin_content
                and success_count > 0
            ):
                PrettyOutput.auto_print(f"📌 已固定 {success_count} 条记忆内容")

            # 生成总结报告
            output = {
                "total": len(memories),
                "success": success_count,
                "failed": failed_count,
                "results": results,
            }

            return {
                "success": True,
                "stdout": json.dumps(output, ensure_ascii=False, indent=2),
                "stderr": "",
            }

        except Exception as e:
            error_msg = f"保存记忆失败: {str(e)}"
            PrettyOutput.auto_print(f"❌ {error_msg}")
            return {"success": False, "stdout": "", "stderr": error_msg}

    # ========== retrieve 操作相关方法 ==========

    def _retrieve_from_type(
        self,
        memory_type: str,
        tags: Optional[List[str]] = None,
        natures: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """从指定作用域(memory_type)与性质(natures)中检索记忆"""
        memories: List[Dict[str, Any]] = []

        if memory_type == "short_term":
            # 从全局变量获取短期记忆
            memories = get_short_term_memories(tags)
        else:
            # 从文件系统获取记忆（按性质分别读取）
            nature_list = natures or ["long_term", "procedural", "episodic"]
            for nature in nature_list:
                memory_dir = self._get_memory_dir(memory_type, nature)
                if not memory_dir.exists():
                    continue

                # 遍历记忆文件
                for memory_file in memory_dir.glob("*.json"):
                    try:
                        with open(memory_file, "r", encoding="utf-8") as f:
                            memory_data = json.load(f)

                        # 如果指定了标签，检查是否匹配
                        if tags:
                            memory_tags = memory_data.get("tags", [])
                            if not any(tag in memory_tags for tag in tags):
                                continue

                        memories.append(memory_data)
                    except Exception as e:
                        PrettyOutput.auto_print(
                            f"⚠️ 读取记忆文件 {memory_file} 失败: {str(e)}"
                        )

        return memories

    def _execute_retrieve(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行检索记忆操作"""
        try:
            memory_types = args.get("memory_types", [])  # 作用域过滤
            natures = args.get("natures", [])  # 性质过滤
            tags = args.get("tags", [])
            limit = args.get("limit", None)
            smart_search = args.get("smart_search", False)
            query = args.get("query", "")

            # 如果启用智能检索模式
            if smart_search:
                return self._execute_smart_search(
                    args, memory_types, query, limit, natures
                )

            # 确定要检索的作用域
            if not memory_types or "all" in memory_types:
                types_to_search = ["project", "global", "short_term"]
            else:
                types_to_search = memory_types

            # 确定要检索的性质
            if not natures or "all" in natures:
                natures_to_search = ["long_term", "procedural", "episodic"]
            else:
                natures_to_search = natures

            # 从各个作用域+性质组合中检索记忆
            all_memories = []
            for memory_type in types_to_search:
                memories = self._retrieve_from_type(
                    memory_type, tags, natures_to_search
                )
                all_memories.extend(memories)

            # 按创建时间排序（最新的在前）
            all_memories.sort(key=lambda x: x.get("created_at", ""), reverse=True)

            # 优先使用剩余token数量，回退到输入窗口限制
            memory_token_limit = None
            agent = args.get("agent")
            if agent and hasattr(agent, "model"):
                try:
                    remaining_tokens = agent.model.get_remaining_token_count()
                    # 使用剩余token的2/3或64k的最小值
                    memory_token_limit = calculate_token_limit(remaining_tokens)
                    if memory_token_limit <= 0:
                        memory_token_limit = None
                except Exception as e:
                    save_exception(
                        e, module="jarvis_tools.memory", function="_execute_retrieve"
                    )
                    pass

            # 回退方案：使用输入窗口的2/3
            if memory_token_limit is None:
                max_input_tokens = get_max_input_token_count()
                memory_token_limit = int(max_input_tokens * 2 / 3)

            # 基于token限制和条数限制筛选记忆
            filtered_memories: List[Dict[str, Any]] = []
            total_tokens = 0

            for memory in all_memories:
                # 计算当前记忆的token数量
                memory_content = json.dumps(memory, ensure_ascii=False)
                memory_tokens = get_context_token_count(memory_content)

                # 检查是否超过token限制
                if total_tokens + memory_tokens > memory_token_limit:
                    break

                # 检查是否超过50条限制
                if len(filtered_memories) >= 50:
                    break

                filtered_memories.append(memory)
                total_tokens += memory_tokens

            all_memories = filtered_memories

            # 如果指定了额外的限制，只返回前N个
            if limit and len(all_memories) > limit:
                all_memories = all_memories[:limit]

            # 格式化为Markdown输出
            markdown_output = "# 记忆检索结果\n\n"
            markdown_output += f"**检索到 {len(all_memories)} 条记忆**\n\n"

            if tags:
                markdown_output += f"**使用标签过滤**: {', '.join(tags)}\n\n"

            markdown_output += f"**作用域**: {', '.join(types_to_search)}\n\n"

            markdown_output += "---\n\n"

            # 输出所有记忆
            for i, memory in enumerate(all_memories):
                markdown_output += f"## {i + 1}. {memory.get('id', '未知ID')}\n\n"
                markdown_output += (
                    f"**作用域**: {memory.get('memory_type', '未知')}\n\n"
                )
                markdown_output += f"**性质**: {memory.get('nature', '未知')}\n\n"
                markdown_output += f"**标签**: {', '.join(memory.get('tags', []))}\n\n"
                markdown_output += (
                    f"**创建时间**: {memory.get('created_at', '未知时间')}\n\n"
                )

                # 内容部分
                content = memory.get("content", "")
                if content:
                    markdown_output += f"**内容**:\n\n{content}\n\n"

                # 如果有额外的元数据
                metadata = {
                    k: v
                    for k, v in memory.items()
                    if k
                    not in [
                        "id",
                        "memory_type",
                        "nature",
                        "tags",
                        "created_at",
                        "content",
                    ]
                }
                if metadata:
                    markdown_output += "**其他信息**:\n"
                    for key, value in metadata.items():
                        markdown_output += f"- {key}: {value}\n"
                    markdown_output += "\n"

                markdown_output += "---\n\n"

            return {
                "success": True,
                "stdout": markdown_output,
                "stderr": "",
            }

        except Exception as e:
            error_msg = f"检索记忆失败: {str(e)}"
            PrettyOutput.auto_print(f"❌ {error_msg}")
            return {"success": False, "stdout": "", "stderr": error_msg}

    def _execute_smart_search(
        self,
        args: Dict[str, Any],
        memory_types: List[str],
        query: str,
        limit: Optional[int],
        natures: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """执行智能语义检索"""
        try:
            if not query:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "智能检索模式需要提供 query 参数",
                }

            # 确定要检索的作用域（智能检索不支持 short_term）
            if not memory_types or "all" in memory_types:
                types_to_search = ["project", "global"]
            else:
                types_to_search = [
                    t for t in memory_types if t in ["project", "global"]
                ]

            if not types_to_search:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "智能检索模式仅支持 project 和 global 作用域",
                }

            # 确定要检索的性质
            if not natures or "all" in natures:
                natures_to_search = ["long_term", "procedural", "episodic"]
            else:
                natures_to_search = natures

            # 使用 SmartRetriever 进行语义检索
            retriever = _get_smart_retriever()
            search_limit = limit if limit else 10
            memories = retriever.semantic_search(
                query=query,
                memory_types=types_to_search,
                natures=natures_to_search,
                limit=search_limit,
            )

            # 基于 token 预算筛选返回的记忆，防止单条超长记忆撑爆上下文
            # （与普通检索 _execute_retrieve 的 token 限制逻辑保持一致）
            memory_token_limit = None
            agent = args.get("agent")
            if agent and hasattr(agent, "model"):
                try:
                    remaining_tokens = agent.model.get_remaining_token_count()
                    memory_token_limit = calculate_token_limit(remaining_tokens)
                    if memory_token_limit <= 0:
                        memory_token_limit = None
                except Exception as e:
                    save_exception(
                        e,
                        module="jarvis_tools.memory",
                        function="_execute_smart_search",
                    )
                    pass

            # 回退方案：使用输入窗口的2/3
            if memory_token_limit is None:
                max_input_tokens = get_max_input_token_count()
                memory_token_limit = int(max_input_tokens * 2 / 3)

            filtered_memories = []
            total_tokens = 0
            for memory in memories:
                memory_content = memory.content or ""
                memory_tokens = get_context_token_count(memory_content)
                if total_tokens + memory_tokens > memory_token_limit:
                    break
                if len(filtered_memories) >= 50:
                    break
                filtered_memories.append(memory)
                total_tokens += memory_tokens
            memories = filtered_memories

            # 格式化为Markdown输出
            markdown_output = "# 智能语义检索结果\n\n"
            markdown_output += f"**查询**: {query}\n\n"
            markdown_output += f"**检索到 {len(memories)} 条相关记忆**\n\n"
            markdown_output += f"**作用域**: {', '.join(types_to_search)}\n\n"
            markdown_output += f"**性质**: {', '.join(natures_to_search)}\n\n"
            markdown_output += "---\n\n"

            # 输出所有记忆
            for i, memory in enumerate(memories):
                markdown_output += f"## {i + 1}. {memory.id}\n\n"
                markdown_output += (
                    f"**类型**: {memory.memory_type} / {memory.nature}\n\n"
                )
                markdown_output += f"**标签**: {', '.join(memory.tags)}\n\n"
                markdown_output += f"**创建时间**: {memory.created_at}\n\n"

                # 内容部分
                if memory.content:
                    markdown_output += f"**内容**:\n\n{memory.content}\n\n"

                markdown_output += "---\n\n"

            return {
                "success": True,
                "stdout": markdown_output,
                "stderr": "",
            }

        except Exception as e:
            error_msg = f"智能检索失败: {str(e)}"
            PrettyOutput.auto_print(f"❌ {error_msg}")
            return {"success": False, "stdout": "", "stderr": error_msg}

    # ========== clear 操作相关方法 ==========

    def _clear_short_term_memories(
        self, tags: Optional[List[str]] = None, memory_ids: Optional[List[str]] = None
    ) -> Dict[str, int]:
        """清除短期记忆"""
        global short_term_memories

        initial_count = len(short_term_memories)
        removed_count = 0

        if memory_ids:
            # 按ID清除
            new_memories = []
            for memory in short_term_memories:
                if memory.get("id") not in memory_ids:
                    new_memories.append(memory)
                else:
                    removed_count += 1
            short_term_memories[:] = new_memories
        elif tags:
            # 按标签清除
            new_memories = []
            for memory in short_term_memories:
                memory_tags = memory.get("tags", [])
                if not any(tag in memory_tags for tag in tags):
                    new_memories.append(memory)
                else:
                    removed_count += 1
            short_term_memories[:] = new_memories
        else:
            # 清除所有
            clear_short_term_memories()
            removed_count = initial_count

        return {"total": initial_count, "removed": removed_count}

    def _clear_long_term_memories(
        self,
        memory_type: str,
        nature: str,
        tags: Optional[List[str]] = None,
        memory_ids: Optional[List[str]] = None,
    ) -> Dict[str, int]:
        """清除长期记忆（指定作用域+性质）"""
        memory_dir = self._get_memory_dir(memory_type, nature)

        if not memory_dir.exists():
            return {"total": 0, "removed": 0}

        total_count = 0
        removed_count = 0

        # 获取所有记忆文件
        memory_files = list(memory_dir.glob("*.json"))
        total_count = len(memory_files)

        for memory_file in memory_files:
            try:
                # 读取记忆内容
                with open(memory_file, "r", encoding="utf-8") as f:
                    memory_data = json.load(f)

                should_remove = False

                if memory_ids:
                    # 按ID判断
                    if memory_data.get("id") in memory_ids:
                        should_remove = True
                elif tags:
                    # 按标签判断
                    memory_tags = memory_data.get("tags", [])
                    if any(tag in memory_tags for tag in tags):
                        should_remove = True
                else:
                    # 清除所有
                    should_remove = True

                if should_remove:
                    memory_file.unlink()
                    removed_count += 1

            except Exception as e:
                PrettyOutput.auto_print(
                    f"⚠️ 处理记忆文件 {memory_file} 时出错: {str(e)}"
                )

        # 如果目录为空，可以删除目录
        if not any(memory_dir.iterdir()) and memory_dir != self.project_memory_dir:
            memory_dir.rmdir()

        return {"total": total_count, "removed": removed_count}

    def _execute_clear(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行清除记忆操作"""
        try:
            memory_types = args.get("memory_types", [])  # 作用域
            natures = args.get("natures", [])  # 性质
            tags = args.get("tags", [])
            memory_ids = args.get("memory_ids", [])
            confirm = args.get("confirm", False)

            if not confirm:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "必须设置 confirm=true 才能执行清除操作",
                }

            # 确定要清除的作用域
            if not memory_types or "all" in memory_types:
                types_to_clear = ["project", "global", "short_term"]
            else:
                types_to_clear = memory_types

            # 确定要清除的性质
            if not natures or "all" in natures:
                natures_to_clear = ["long_term", "procedural", "episodic"]
            else:
                natures_to_clear = natures

            # 统计结果
            results = {}
            total_removed = 0

            # 清除各作用域+性质的记忆
            for memory_type in types_to_clear:
                if memory_type == "short_term":
                    result = self._clear_short_term_memories(tags, memory_ids)
                    results[memory_type] = result
                    total_removed += result["removed"]
                else:
                    for nature in natures_to_clear:
                        result = self._clear_long_term_memories(
                            memory_type, nature, tags, memory_ids
                        )
                        key = f"{memory_type}/{nature}"
                        results[key] = result
                        total_removed += result["removed"]

            # 生成结果报告
            report = "# 记忆清除报告\n\n"
            report += f"**总计清除**: {total_removed} 条记忆\n\n"

            if tags:
                report += f"**使用标签过滤**: {', '.join(tags)}\n\n"

            if memory_ids:
                report += f"**指定记忆ID**: {', '.join(memory_ids)}\n\n"

            report += "## 详细结果\n\n"

            for memory_type, result in results.items():
                report += f"### {memory_type}\n"
                report += f"- 原有记忆: {result['total']} 条\n"
                report += f"- 已清除: {result['removed']} 条\n"
                report += f"- 剩余: {result['total'] - result['removed']} 条\n\n"

            return {
                "success": True,
                "stdout": report,
                "stderr": "",
            }

        except Exception as e:
            error_msg = f"清除记忆失败: {str(e)}"
            PrettyOutput.auto_print(f"❌ {error_msg}")
            return {"success": False, "stdout": "", "stderr": error_msg}

    # ========== 主入口方法 ==========

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行记忆操作"""
        try:
            action = args.get("action", "")

            if not action:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "必须指定操作类型（save/retrieve/clear）",
                }

            # 根据操作类型路由到对应的方法
            if action == "save":
                return self._execute_save(args)
            elif action == "retrieve":
                return self._execute_retrieve(args)
            elif action == "clear":
                return self._execute_clear(args)
            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"未知的操作类型: {action}，支持的操作类型：save/retrieve/clear",
                }

        except Exception as e:
            error_msg = f"执行记忆操作失败: {str(e)}"
            PrettyOutput.auto_print(f"❌ {error_msg}")
            return {"success": False, "stdout": "", "stderr": error_msg}
