# -*- coding: utf-8 -*-
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from jarvis.jarvis_utils.config import get_data_dir, get_max_input_token_count
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.globals import get_short_term_memories
from jarvis.jarvis_utils.embedding import get_context_token_count


class RetrieveMemoryTool:
    """检索记忆工具，用于从长短期记忆系统中检索信息"""

    name = "retrieve_memory"
    description = """从长短期记忆系统中检索信息。
    
    支持的记忆类型：
    - project_long_term: 项目长期记忆（与当前项目相关的信息）
    - global_long_term: 全局长期记忆（通用的信息、用户喜好、知识、方法等）
    - short_term: 短期记忆（当前任务相关的信息）
    - all: 从所有类型中检索
    
    可以通过标签过滤检索结果，支持多个标签（满足任一标签即可）
    注意：标签数量建议不要超过10个，以保证检索效率
    """

    parameters = {
        "type": "object",
        "properties": {
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
                "description": "要检索的记忆类型列表，如果包含'all'则检索所有类型",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "用于过滤的标签列表（可选）",
            },
            "limit": {
                "type": "integer",
                "description": "返回结果的最大数量（可选，默认返回所有）",
                "minimum": 1,
            },
        },
        "required": ["memory_types"],
    }

    def __init__(self):
        """初始化检索记忆工具"""
        self.project_memory_dir = Path(".jarvis/memory")
        self.global_memory_dir = Path(get_data_dir()) / "memory"

    def _get_memory_dir(self, memory_type: str) -> Path:
        """根据记忆类型获取存储目录"""
        if memory_type == "project_long_term":
            return self.project_memory_dir
        elif memory_type in ["global_long_term", "short_term"]:
            return self.global_memory_dir / memory_type
        else:
            raise ValueError(f"未知的记忆类型: {memory_type}")

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
                    PrettyOutput.print(
                        f"读取记忆文件 {memory_file} 失败: {str(e)}", OutputType.WARNING
                    )

        return memories

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行检索记忆操作"""
        try:
            memory_types = args.get("memory_types", [])
            tags = args.get("tags", [])
            limit = args.get("limit", None)

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

            # 获取最大输入token数的2/3作为记忆的token限制
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

            # 打印结果摘要

            if tags:
                pass

            # 格式化为Markdown输出
            markdown_output = "# 记忆检索结果\n\n"
            markdown_output += f"**检索到 {len(all_memories)} 条记忆**\n\n"

            if tags:
                markdown_output += f"**使用标签过滤**: {', '.join(tags)}\n\n"

            markdown_output += f"**记忆类型**: {', '.join(types_to_search)}\n\n"

            markdown_output += "---\n\n"

            # 输出所有记忆
            for i, memory in enumerate(all_memories):
                markdown_output += f"## {i+1}. {memory.get('id', '未知ID')}\n\n"
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

            # 如果记忆较多，在终端显示摘要
            if len(all_memories) > 5:
                # 静默模式下不再打印摘要，完整结果已包含在返回的markdown_output中
                for i, memory in enumerate(all_memories[:5]):
                    content_preview = memory.get("content", "")[:100]
                    if len(memory.get("content", "")) > 100:
                        content_preview += "..."

            return {
                "success": True,
                "stdout": markdown_output,
                "stderr": "",
            }

        except Exception as e:
            error_msg = f"检索记忆失败: {str(e)}"
            PrettyOutput.print(error_msg, OutputType.ERROR)
            return {"success": False, "stdout": "", "stderr": error_msg}
