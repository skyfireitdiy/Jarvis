# -*- coding: utf-8 -*-
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.globals import get_short_term_memories


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

            # 如果指定了限制，只返回前N个
            if limit:
                all_memories = all_memories[:limit]

            # 打印结果摘要
            PrettyOutput.print(f"检索到 {len(all_memories)} 条记忆", OutputType.INFO)

            if tags:
                PrettyOutput.print(f"使用标签过滤: {', '.join(tags)}", OutputType.INFO)

            # 格式化输出
            result = {
                "total_count": len(all_memories),
                "memory_types": types_to_search,
                "filter_tags": tags,
                "memories": all_memories,
            }

            # 如果记忆较多，显示摘要
            if len(all_memories) > 5:
                PrettyOutput.print(f"记忆较多，仅显示前5条摘要：", OutputType.INFO)
                for i, memory in enumerate(all_memories[:5]):
                    content_preview = memory.get("content", "")[:100]
                    if len(memory.get("content", "")) > 100:
                        content_preview += "..."
                    PrettyOutput.print(
                        f"{i+1}. [{memory.get('type')}] {memory.get('id')}\n"
                        f"   标签: {', '.join(memory.get('tags', []))}\n"
                        f"   内容: {content_preview}",
                        OutputType.INFO,
                    )

            return {
                "success": True,
                "stdout": json.dumps(result, ensure_ascii=False, indent=2),
                "stderr": "",
            }

        except Exception as e:
            error_msg = f"检索记忆失败: {str(e)}"
            PrettyOutput.print(error_msg, OutputType.ERROR)
            return {"success": False, "stdout": "", "stderr": error_msg}
