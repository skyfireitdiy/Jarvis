# -*- coding: utf-8 -*-
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.globals import add_short_term_memory


class SaveMemoryTool:
    """保存记忆工具，用于将信息保存到长短期记忆系统"""

    name = "save_memory"
    description = """保存信息到长短期记忆系统。
    
    支持的记忆类型：
    - project_long_term: 项目长期记忆（与当前项目相关的信息）
    - global_long_term: 全局长期记忆（通用的信息、用户喜好、知识、方法等）
    - short_term: 短期记忆（当前任务相关的信息）
    
    项目长期记忆存储在当前目录的 .jarvis/memory 下
    全局长期记忆和短期记忆存储在数据目录的 memory 子目录下
    """

    parameters = {
        "type": "object",
        "properties": {
            "memory_type": {
                "type": "string",
                "enum": ["project_long_term", "global_long_term", "short_term"],
                "description": "记忆类型",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "用于索引记忆的标签列表",
            },
            "content": {"type": "string", "description": "要保存的记忆内容"},
        },
        "required": ["memory_type", "tags", "content"],
    }

    def __init__(self):
        """初始化保存记忆工具"""
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

    def _generate_memory_id(self) -> str:
        """生成唯一的记忆ID"""
        return datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行保存记忆操作"""
        try:
            memory_type = args["memory_type"]
            tags = args.get("tags", [])
            content = args.get("content", "")

            # 生成记忆ID
            memory_id = self._generate_memory_id()

            # 创建记忆对象
            memory_data = {
                "id": memory_id,
                "type": memory_type,
                "tags": tags,
                "content": content,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }

            if memory_type == "short_term":
                # 短期记忆保存到全局变量
                add_short_term_memory(memory_data)

                # 打印成功信息
                PrettyOutput.print(
                    f"短期记忆已保存\n"
                    f"ID: {memory_id}\n"
                    f"类型: {memory_type}\n"
                    f"标签: {', '.join(tags)}\n"
                    f"存储位置: 内存（非持久化）",
                    OutputType.SUCCESS,
                )

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
                    json.dump(memory_data, f, ensure_ascii=False, indent=2)

                # 打印成功信息
                PrettyOutput.print(
                    f"记忆已保存\n"
                    f"ID: {memory_id}\n"
                    f"类型: {memory_type}\n"
                    f"标签: {', '.join(tags)}\n"
                    f"位置: {memory_file}",
                    OutputType.SUCCESS,
                )

                result = {
                    "memory_id": memory_id,
                    "memory_type": memory_type,
                    "tags": tags,
                    "file_path": str(memory_file),
                    "message": f"记忆已成功保存，ID: {memory_id}",
                }

            return {
                "success": True,
                "stdout": json.dumps(result, ensure_ascii=False, indent=2),
                "stderr": "",
            }

        except Exception as e:
            error_msg = f"保存记忆失败: {str(e)}"
            PrettyOutput.print(error_msg, OutputType.ERROR)
            return {"success": False, "stdout": "", "stderr": error_msg}
