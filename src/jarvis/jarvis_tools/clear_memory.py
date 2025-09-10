# -*- coding: utf-8 -*-
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.globals import (
    clear_short_term_memories,
    short_term_memories,
)


class ClearMemoryTool:
    """清除记忆工具，用于批量清除指定的记忆"""

    name = "clear_memory"
    description = """批量清除指定的记忆。
    
    支持的清除方式：
    1. 按记忆类型清除所有记忆
    2. 按标签清除特定记忆
    3. 按记忆ID清除单个记忆
    
    支持的记忆类型：
    - project_long_term: 项目长期记忆
    - global_long_term: 全局长期记忆
    - short_term: 短期记忆
    - all: 所有类型的记忆
    
    注意：清除操作不可恢复，请谨慎使用
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
                "description": "要清除的记忆类型列表",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要清除的记忆标签列表（可选，如果指定则只清除带有这些标签的记忆）",
            },
            "memory_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要清除的具体记忆ID列表（可选）",
            },
            "confirm": {
                "type": "boolean",
                "description": "确认清除操作（必须为true才会执行清除）",
                "default": False,
            },
        },
        "required": ["memory_types", "confirm"],
    }

    def __init__(self):
        """初始化清除记忆工具"""
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
                PrettyOutput.print(
                    f"处理记忆文件 {memory_file} 时出错: {str(e)}", OutputType.WARNING
                )

        # 如果目录为空，可以删除目录
        if not any(memory_dir.iterdir()) and memory_dir != self.project_memory_dir:
            memory_dir.rmdir()

        return {"total": total_count, "removed": removed_count}

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
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

            # 详细报告
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
            PrettyOutput.print(error_msg, OutputType.ERROR)
            return {"success": False, "stdout": "", "stderr": error_msg}
