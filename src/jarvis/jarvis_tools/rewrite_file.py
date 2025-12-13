from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
import os
from typing import Any, Dict


class RewriteFileTool:
    """文件重写工具，用于完全重写文件内容"""

    name = "rewrite_file"
    description = (
        "完全重写文件内容，适用于新增文件或大范围改写。具备失败回滚能力。"
        "局部修改请优先使用 edit_file_normal（普通 search/replace）或 edit_file_free（基于上下文的模糊匹配）。\n\n"
        "    ⚠️ 重要提示：\n"
        "    - 不要一次重写太多内容，建议分多次进行，避免超过LLM的上下文窗口大小\n"
        "    - 如果文件内容较长（超过2048字符），建议采用以下策略：\n"
        "      1. 第一次调用 rewrite_file 写入部分内容（如文件的前半部分或关键部分）\n"
        "      2. 然后多次调用 edit_file_normal工具，使用追加/替换操作补充后续内容\n"
        "    - 这样可以避免单次操作内容过长导致上下文溢出"
    )

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
                PrettyOutput.auto_print(f"❌ {error_msg}")
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": error_msg,
                }

        except Exception as e:
            error_msg = f"文件重写失败: {str(e)}"
            PrettyOutput.auto_print(f"❌ {error_msg}")
            return {"success": False, "stdout": "", "stderr": error_msg}
