"""整文件覆写工具：用 content 覆盖写入整个文件。"""

import os
from typing import Any
from typing import Dict

from jarvis.jarvis_tools.edit_file_common import (
    generate_diff_preview,
    is_file_in_workspace_subdir,
    read_file_with_backup,
    write_file_with_rollback,
)
from jarvis.jarvis_utils.config import save_exception
from jarvis.jarvis_utils.output import PrettyOutput


class write_file:
    """整文件覆写工具，用 content 覆盖写入整个文件"""

    name = "write_file"
    description = (
        "用 content 覆盖写入整个文件（整文件重写）。"
        "适用于新建文件或大范围重写：直接给出文件的完整新内容即可，无需提供 search。"
        "若只想修改文件中的一小部分，请改用 edit_file（查找替换）或 edit_file_by_line（按行号替换）。"
    )

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要写入的文件路径（支持绝对路径和相对路径）",
            },
            "content": {
                "type": "string",
                "description": "文件的完整新内容（会覆盖原文件全部内容；空字符串表示清空文件）",
            },
        },
        "required": ["file_path", "content"],
    }

    def __init__(self) -> None:
        """初始化整文件覆写工具"""
        pass

    @staticmethod
    def _validate_args(args: Dict[str, Any]) -> Dict[str, Any] | None:
        """验证参数，失败时返回错误响应，否则返回 None"""
        file_path = args.get("file_path")
        if not file_path:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必需参数：file_path",
            }
        if not isinstance(file_path, str):
            return {
                "success": False,
                "stdout": "",
                "stderr": "file_path 参数必须是字符串",
            }
        if "content" not in args:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必需参数：content",
            }
        if not isinstance(args.get("content"), str):
            return {
                "success": False,
                "stdout": "",
                "stderr": "content 参数必须是字符串",
            }
        return None

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """用 content 覆盖写入整个文件"""
        try:
            error_response = write_file._validate_args(args)
            if error_response:
                return error_response

            file_path = args["file_path"]
            content = args["content"]
            agent = args.get("agent")

            # 读取原内容并创建备份（文件不存在时返回空内容）
            (
                original_content,
                backup_path,
                detected_encoding,
            ) = read_file_with_backup(file_path)

            abs_path = os.path.abspath(file_path)
            write_success, write_error = write_file_with_rollback(
                abs_path, content, backup_path, detected_encoding
            )
            if not write_success:
                PrettyOutput.auto_print(f"❌ {file_path}: {write_error}")
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"{file_path}: {write_error}",
                }

            # 写入成功，删除备份文件
            if backup_path and os.path.exists(backup_path):
                try:
                    os.remove(backup_path)
                except Exception as e:
                    save_exception(
                        e, module="jarvis_tools.write_file", function="execute"
                    )
                    pass

            encoding_info = detected_encoding or "utf-8"
            all_results = [f"✅ {file_path}: 写入成功 (🔤 编码: {encoding_info})"]

            # 文件不在当前工作目录子目录下（或非 code_agent）时，打印 diff 预览
            in_workspace = is_file_in_workspace_subdir(abs_path)
            if not (agent and agent.agent_type() == "code_agent" and in_workspace):
                try:
                    diff_text = generate_diff_preview(
                        original_content, content, file_path
                    )
                    from jarvis.jarvis_code_agent.diff_visualizer import (
                        visualize_diff_enhanced,
                    )

                    visualize_diff_enhanced(
                        diff_text,
                        file_path=file_path,
                        mode="side_by_side",
                        show_line_numbers=True,
                        context_lines=3,
                    )
                    all_results.append(
                        f"\n📝 {file_path} 的 diff（文件不在当前工作目录的子级目录下）:"
                    )
                    all_results.append(diff_text)
                except Exception as diff_error:
                    # diff 生成或打印失败不影响主流程
                    PrettyOutput.auto_print(f"⚠️ 生成 diff 时出错: {str(diff_error)}")

            return {
                "success": True,
                "stdout": "\n".join(all_results),
                "stderr": "",
            }

        except Exception as e:
            error_msg = f"文件写入失败: {str(e)}"
            PrettyOutput.auto_print(f"❌ {error_msg}")
            return {"success": False, "stdout": "", "stderr": error_msg}


__all__ = ["write_file"]
