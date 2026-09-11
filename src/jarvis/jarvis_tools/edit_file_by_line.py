"""按行号替换工具：用 content 替换文件中指定行号区间的内容。"""

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


class edit_file_by_line:
    """按行号替换工具，用 content 替换闭区间 [start_line, end_line] 的内容"""

    name = "edit_file_by_line"
    description = (
        "用 content 替换文件中指定行号区间的内容（闭区间 [start_line, end_line]）。"
        "适用于已知目标行的场景：先用 read_code 确认行号，再指定要替换的行范围。"
        "若想按内容查找替换，请改用 edit_file；若想整文件重写，请改用 write_file。"
    )

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要编辑的文件路径（支持绝对路径和相对路径）",
            },
            "start_line": {
                "type": "integer",
                "description": "起始行号（从 1 开始，包含该行）",
            },
            "end_line": {
                "type": "integer",
                "description": "结束行号（从 1 开始，包含该行）",
            },
            "content": {
                "type": "string",
                "description": "用于替换该行号区间的新内容",
            },
        },
        "required": ["file_path", "start_line", "end_line", "content"],
    }

    def __init__(self) -> None:
        """初始化按行号替换工具"""
        pass

    @staticmethod
    def _validate_args(args: Dict[str, Any]) -> Dict[str, Any] | None:
        """验证参数，失败时返回错误响应，否则返回 None"""
        file_path = args.get("file_path")
        if not file_path or not isinstance(file_path, str):
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必需的字符串参数：file_path",
            }

        start_line = args.get("start_line")
        end_line = args.get("end_line")
        if not isinstance(start_line, int) or isinstance(start_line, bool):
            return {
                "success": False,
                "stdout": "",
                "stderr": "start_line 参数必须是整数",
            }
        if not isinstance(end_line, int) or isinstance(end_line, bool):
            return {
                "success": False,
                "stdout": "",
                "stderr": "end_line 参数必须是整数",
            }
        if start_line < 1:
            return {
                "success": False,
                "stdout": "",
                "stderr": "start_line 必须大于等于 1",
            }
        if end_line < start_line:
            return {
                "success": False,
                "stdout": "",
                "stderr": "end_line 必须大于等于 start_line",
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

    @staticmethod
    def _replace_line_range(
        content: str, start_line: int, end_line: int, replace: str
    ) -> str:
        """用 replace 替换 content 中闭区间 [start_line, end_line] 的内容"""
        lines = content.splitlines(keepends=True)
        total_lines = len(lines)

        before_lines = lines[: start_line - 1]
        after_lines = lines[end_line:] if end_line < total_lines else []

        # 确保替换内容以换行符结尾（如果后面还有行）
        replace_content = replace
        if after_lines and not replace_content.endswith("\n"):
            replace_content += "\n"

        new_content_parts = []
        if before_lines:
            new_content_parts.append("".join(before_lines))
        new_content_parts.append(replace_content)
        if after_lines:
            if not replace_content.endswith("\n") and new_content_parts:
                new_content_parts.append("\n")
            new_content_parts.append("".join(after_lines))

        return "".join(new_content_parts)

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """用 content 替换文件中闭区间 [start_line, end_line] 的内容"""
        try:
            error_response = edit_file_by_line._validate_args(args)
            if error_response:
                return error_response

            file_path = args["file_path"]
            start_line = args["start_line"]
            end_line = args["end_line"]
            replace = args["content"]
            agent = args.get("agent")

            # 读取原内容并创建备份（文件不存在时返回空内容）
            (
                original_content,
                backup_path,
                detected_encoding,
            ) = read_file_with_backup(file_path)

            total_lines = len(original_content.splitlines(keepends=True))
            if start_line > total_lines:
                if backup_path and os.path.exists(backup_path):
                    try:
                        os.remove(backup_path)
                    except Exception as e:
                        save_exception(
                            e,
                            module="jarvis_tools.edit_file_by_line",
                            function="execute",
                        )
                        pass
                error_msg = f"start_line ({start_line}) 超出文件总行数 ({total_lines})"
                PrettyOutput.auto_print(f"❌ {file_path}: {error_msg}")
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"{file_path}: {error_msg}",
                }

            new_content = edit_file_by_line._replace_line_range(
                original_content, start_line, end_line, replace
            )

            abs_path = os.path.abspath(file_path)
            write_success, write_error = write_file_with_rollback(
                abs_path, new_content, backup_path, detected_encoding
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
                        e,
                        module="jarvis_tools.edit_file_by_line",
                        function="execute",
                    )
                    pass

            encoding_info = detected_encoding or "utf-8"
            all_results = [
                f"✅ {file_path}: 修改成功 (🔤 编码: {encoding_info})",
                f"   已替换第 {start_line}-{end_line} 行",
            ]

            # 文件不在当前工作目录子目录下（或非 code_agent）时，打印 diff 预览
            in_workspace = is_file_in_workspace_subdir(abs_path)
            if not (agent and agent.agent_type() == "code_agent" and in_workspace):
                try:
                    diff_text = generate_diff_preview(
                        original_content, new_content, file_path
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
            error_msg = f"文件编辑失败: {str(e)}"
            PrettyOutput.auto_print(f"❌ {error_msg}")
            return {"success": False, "stdout": "", "stderr": error_msg}


__all__ = ["edit_file_by_line"]
