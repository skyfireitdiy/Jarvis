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
    description = """统一的记忆管理工具，支持三种操作：

1. **save**: 保存信息到长短期记忆系统。支持批量保存，记忆类型：project_long_term（项目长期）、global_long_term（全局长期）、short_term（短期）。

2. **retrieve**: 从长短期记忆系统中检索信息。支持按类型和标签过滤，支持智能语义检索。

3. **clear**: 清除指定的记忆。支持按类型、标签或ID清除。注意：清除操作不可恢复。

**重要提示**：
- 每次调用只能执行一种操作（save/retrieve/clear）
- 参数根据操作类型而有所不同"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["save", "retrieve", "clear"],
                "description": "操作类型：save（保存记忆）、retrieve（检索记忆）、clear（清除记忆）",
            },
            # save 操作的参数
            "memories": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "memory_type": {
                            "type": "string",
                            "enum": [
                                "project_long_term",
                                "global_long_term",
                                "short_term",
                            ],
                            "description": "记忆类型",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "用于索引记忆的标签列表",
                        },
                        "content": {
                            "type": "string",
                            "description": "要保存的记忆内容",
                        },
                    },
                    "required": ["memory_type", "tags", "content"],
                },
                "description": "要保存的记忆列表（仅 save 操作使用）",
            },
            # retrieve 操作的参数
            "memory_types": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "project_long_term",
                        "global_long_term",
                        "short_term",
                        "all",
                    ],
                },
                "description": "要检索的记忆类型列表（仅 retrieve 操作使用）",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "用于过滤的标签列表（可选，retrieve 和 clear 操作使用）",
            },
            "limit": {
                "type": "integer",
                "description": "返回结果的最大数量（可选，仅 retrieve 操作使用）",
                "minimum": 1,
            },
            "smart_search": {
                "type": "boolean",
                "description": "是否启用智能语义检索模式（可选，仅 retrieve 操作使用）",
                "default": False,
            },
            "query": {
                "type": "string",
                "description": "语义检索的查询文本（仅 retrieve 操作在 smart_search=True 时使用）",
            },
            # clear 操作的参数
            "memory_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要清除的具体记忆ID列表（可选，仅 clear 操作使用）",
            },
            "confirm": {
                "type": "boolean",
                "description": "确认清除操作（仅 clear 操作使用，必须为true才会执行清除）",
                "default": False,
            },
        },
        "required": ["action"],
    }

    def __init__(self) -> None:
        """初始化记忆管理工具"""
        self.project_memory_dir = Path(".jarvis/memory")
        self.global_memory_dir = Path(get_data_dir()) / "memory"

    def _get_memory_dir(self, memory_type: str) -> Path:
        """根据记忆类型获取存储目录"""
        if memory_type == "project_long_term":
            return Path(self.project_memory_dir)
        elif memory_type in ["global_long_term", "short_term"]:
            return Path(self.global_memory_dir) / memory_type
        else:
            raise ValueError(f"未知的记忆类型: {memory_type}")

    def _generate_memory_id(self) -> str:
        """生成唯一的记忆ID"""
        # 添加微秒级时间戳确保唯一性
        time.sleep(0.001)  # 确保不同记忆有不同的时间戳
        return datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    # ========== save 操作相关方法 ==========

    def _save_single_memory(
        self, memory_data: Dict[str, Any], agent: Any = None
    ) -> Dict[str, Any]:
        """保存单条记忆"""
        memory_type = memory_data["memory_type"]
        tags = memory_data.get("tags", [])
        content = memory_data.get("content", "")

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
            "type": memory_type,
            "tags": tags,
            "content": content,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

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
                "tags": tags,
                "storage": "memory",
                "message": f"短期记忆已成功保存到内存，ID: {memory_id}",
            }
        else:
            # 长期记忆保存到文件
            # 获取存储目录并确保存在
            memory_dir = self._get_memory_dir(memory_type)
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
        self, memory_type: str, tags: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """从指定类型中检索记忆"""
        memories: List[Dict[str, Any]] = []

        if memory_type == "short_term":
            # 从全局变量获取短期记忆
            memories = get_short_term_memories(tags)
        else:
            # 从文件系统获取长期记忆
            memory_dir = self._get_memory_dir(memory_type)

            if not memory_dir.exists():
                return memories

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
            memory_types = args.get("memory_types", [])
            tags = args.get("tags", [])
            limit = args.get("limit", None)
            smart_search = args.get("smart_search", False)
            query = args.get("query", "")

            # 如果启用智能检索模式
            if smart_search:
                return self._execute_smart_search(args, memory_types, query, limit)

            # 确定要检索的记忆类型
            if "all" in memory_types:
                types_to_search = [
                    "project_long_term",
                    "global_long_term",
                    "short_term",
                ]
            else:
                types_to_search = memory_types

            # 从各个类型中检索记忆
            all_memories = []
            for memory_type in types_to_search:
                memories = self._retrieve_from_type(memory_type, tags)
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
                except Exception:
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

            markdown_output += f"**记忆类型**: {', '.join(types_to_search)}\n\n"

            markdown_output += "---\n\n"

            # 输出所有记忆
            for i, memory in enumerate(all_memories):
                markdown_output += f"## {i + 1}. {memory.get('id', '未知ID')}\n\n"
                markdown_output += f"**类型**: {memory.get('type', '未知类型')}\n\n"
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
                    if k not in ["id", "type", "tags", "created_at", "content"]
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
    ) -> Dict[str, Any]:
        """执行智能语义检索"""
        try:
            if not query:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "智能检索模式需要提供 query 参数",
                }

            # 确定要检索的记忆类型（智能检索不支持 short_term）
            if "all" in memory_types:
                types_to_search = ["project_long_term", "global_long_term"]
            else:
                types_to_search = [
                    t
                    for t in memory_types
                    if t in ["project_long_term", "global_long_term"]
                ]

            if not types_to_search:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "智能检索模式仅支持 project_long_term 和 global_long_term 类型",
                }

            # 使用 SmartRetriever 进行语义检索
            retriever = _get_smart_retriever()
            search_limit = limit if limit else 10
            memories = retriever.semantic_search(
                query=query,
                memory_types=types_to_search,
                limit=search_limit,
            )

            # 格式化为Markdown输出
            markdown_output = "# 智能语义检索结果\n\n"
            markdown_output += f"**查询**: {query}\n\n"
            markdown_output += f"**检索到 {len(memories)} 条相关记忆**\n\n"
            markdown_output += f"**记忆类型**: {', '.join(types_to_search)}\n\n"
            markdown_output += "---\n\n"

            # 输出所有记忆
            for i, memory in enumerate(memories):
                markdown_output += f"## {i + 1}. {memory.id}\n\n"
                markdown_output += f"**类型**: {memory.type}\n\n"
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
        tags: Optional[List[str]] = None,
        memory_ids: Optional[List[str]] = None,
    ) -> Dict[str, int]:
        """清除长期记忆"""
        memory_dir = self._get_memory_dir(memory_type)

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
            memory_types = args.get("memory_types", [])
            tags = args.get("tags", [])
            memory_ids = args.get("memory_ids", [])
            confirm = args.get("confirm", False)

            if not confirm:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "必须设置 confirm=true 才能执行清除操作",
                }

            # 确定要清除的记忆类型
            if "all" in memory_types:
                types_to_clear = ["project_long_term", "global_long_term", "short_term"]
            else:
                types_to_clear = memory_types

            # 统计结果
            results = {}
            total_removed = 0

            # 清除各类型的记忆
            for memory_type in types_to_clear:
                if memory_type == "short_term":
                    result = self._clear_short_term_memories(tags, memory_ids)
                else:
                    result = self._clear_long_term_memories(
                        memory_type, tags, memory_ids
                    )

                results[memory_type] = result
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
