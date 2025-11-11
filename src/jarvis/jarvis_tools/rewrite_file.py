# -*- coding: utf-8 -*-
import json
import os
from typing import Any, Dict

from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class RewriteFileTool:
    """文件重写工具，用于完全重写文件内容"""

    name = "rewrite_file"
    description = """完全重写文件内容。

该工具用于完全替换文件内容，适用于新增文件或大范围改写。
整文件重写会完全替换文件内容，如需局部修改请使用 edit_file 操作。
该操作具备失败回滚能力。
"""

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要重写的文件路径（支持绝对路径和相对路径）",
            },
            "content": {
                "type": "string",
                "description": "新的文件完整内容",
            },
        },
        "required": ["file_path", "content"],
    }

    def __init__(self):
        """初始化文件重写工具"""
        pass

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行文件重写操作"""
        try:
            file_path = args.get("file_path")
            content = args.get("content")

            if not file_path:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "缺少必需参数：file_path",
                }

            if content is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "缺少必需参数：content",
                }

            abs_path = os.path.abspath(file_path)
            original_content = None
            processed = False

            try:
                file_exists = os.path.exists(abs_path)
                if file_exists:
                    with open(abs_path, "r", encoding="utf-8") as rf:
                        original_content = rf.read()

                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                with open(abs_path, "w", encoding="utf-8") as wf:
                    wf.write(content)
                processed = True

                # 记录 REWRITE 操作调用统计
                try:
                    from jarvis.jarvis_stats.stats import StatsManager

                    StatsManager.increment("rewrite_file", group="tool")
                except Exception:
                    pass

                return {
                    "success": True,
                    "stdout": f"文件 {abs_path} 重写成功",
                    "stderr": "",
                }

            except Exception as e:
                # 回滚已修改内容
                try:
                    if processed:
                        if original_content is None:
                            if os.path.exists(abs_path):
                                os.remove(abs_path)
                        else:
                            with open(abs_path, "w", encoding="utf-8") as wf:
                                wf.write(original_content)
                except Exception:
                    pass
                error_msg = f"文件重写失败: {str(e)}"
                PrettyOutput.print(error_msg, OutputType.ERROR)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": error_msg,
                }

        except Exception as e:
            error_msg = f"文件重写失败: {str(e)}"
            PrettyOutput.print(error_msg, OutputType.ERROR)
            return {"success": False, "stdout": "", "stderr": error_msg}

