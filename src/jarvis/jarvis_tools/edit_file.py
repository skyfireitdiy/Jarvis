"""查找替换工具：在文件中查找 search 文本并替换为 replace。"""

import os
from typing import Any
from typing import Dict

from jarvis.jarvis_tools.edit_file_common import (
    count_matches,
    find_actual_search_text,
    generate_diff_preview,
    is_file_in_workspace_subdir,
    preserve_quote_style,
    read_file_with_backup,
    write_file_with_rollback,
)
from jarvis.jarvis_utils.config import save_exception
from jarvis.jarvis_utils.output import PrettyOutput


class edit_file:
    """查找替换工具，在文件中查找 search 文本并替换为 replace"""

    name = "edit_file"
    description = (
        "在文件中查找 search 文本并替换为 replace（精确匹配）。"
        "search 需包含足够的上下文以唯一定位目标位置；若匹配到多处，默认不替换并报错，"
        "可显式设置 replace_all=true 替换全部匹配。"
        "若想整文件重写，请改用 write_file；若想按行号替换，请改用 edit_file_by_line。"
    )

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要编辑的文件路径（支持绝对路径和相对路径）",
            },
            "search": {
                "type": "string",
                "description": "要查找的原文（需精确匹配，建议包含足够上下文以唯一定位）",
            },
            "replace": {
                "type": "string",
                "description": "用于替换 search 的新文本（空字符串表示删除）",
            },
            "replace_all": {
                "type": "boolean",
                "description": "是否替换所有匹配项，默认 false（仅当匹配唯一时才替换）",
            },
        },
        "required": ["file_path", "search", "replace"],
    }

    def __init__(self) -> None:
        """初始化查找替换工具"""
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

        if "search" not in args or not isinstance(args.get("search"), str):
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必需的字符串参数：search",
            }
        if "replace" not in args or not isinstance(args.get("replace"), str):
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必需的字符串参数：replace",
            }

        replace_all = args.get("replace_all", False)
        if not isinstance(replace_all, bool):
            return {
                "success": False,
                "stdout": "",
                "stderr": "replace_all 参数必须是布尔值",
            }
        return None

    @staticmethod
    def _build_not_found_error(search: str, file_path: str) -> str:
        """构建未找到匹配文本时的详细错误信息"""
        error_info = "未找到可匹配的文本"
        if search:
            error_info += f"\n搜索文本: {search[:200]}..."
            error_info += (
                "\n💡 提示：如果搜索文本在文件中存在但未找到匹配，可能是因为："
            )
            error_info += (
                "\n   1. 搜索文本包含不可见字符或格式不匹配（建议检查空格、换行等）"
            )
            error_info += "\n   2. 文件中的实际文本与 search 存在引号或换行风格差异"
            error_info += "\n   3. **文件可能已被更新**：如果文件在其他地方被修改了，搜索文本可能已经不存在或已改变"
            error_info += f"\n   💡 建议：使用 `read_code` 工具重新读取文件 `{file_path}` 查看当前内容，"
            error_info += (
                "\n      确认文件是否已被更新，然后根据实际内容调整 search 文本"
            )
        return error_info

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """在文件中查找 search 文本并替换为 replace"""
        try:
            error_response = edit_file._validate_args(args)
            if error_response:
                return error_response

            file_path = args["file_path"]
            search = args["search"]
            replace = args["replace"]
            replace_all = args.get("replace_all", False)
            agent = args.get("agent")

            if search == "":
                error_msg = (
                    "search 不能为空字符串。若想重写整个文件，请使用 write_file 工具。"
                )
                PrettyOutput.auto_print(f"❌ {file_path}: {error_msg}")
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"{file_path}: {error_msg}",
                }

            # 检查 search 和 replace 是否完全一致（无效操作）
            if search == replace:
                error_msg = (
                    "search 和 replace 内容完全相同，这是一个无效操作（没有实际修改）"
                )
                PrettyOutput.auto_print(f"❌ {file_path}: {error_msg}")
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"{file_path}: {error_msg}",
                }

            # 读取原内容并创建备份（文件不存在时返回空内容）
            (
                original_content,
                backup_path,
                detected_encoding,
            ) = read_file_with_backup(file_path)

            def _cleanup_backup() -> None:
                if backup_path and os.path.exists(backup_path):
                    try:
                        os.remove(backup_path)
                    except Exception as e:
                        save_exception(
                            e, module="jarvis_tools.edit_file", function="execute"
                        )
                        pass

            actual_search = find_actual_search_text(original_content, search)
            if actual_search is None:
                _cleanup_backup()
                error_msg = edit_file._build_not_found_error(search, file_path)
                PrettyOutput.auto_print(f"❌ {file_path}: {error_msg}")
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"{file_path}: {error_msg}",
                }

            styled_replace = preserve_quote_style(search, actual_search, replace)
            match_count = count_matches(original_content, actual_search)

            if match_count == 1:
                new_content = original_content.replace(actual_search, styled_replace, 1)
            elif replace_all:
                new_content = original_content.replace(actual_search, styled_replace)
            else:
                _cleanup_backup()
                error_msg = (
                    f"search 文本匹配到 {match_count} 处，但 replace_all=false，不会自动替换全部匹配。"
                    "\n💡 建议：提供更精确的上下文以唯一定位目标位置，或显式设置 replace_all=true。"
                )
                PrettyOutput.auto_print(f"❌ {file_path}: {error_msg}")
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"{file_path}: {error_msg}",
                }

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
            _cleanup_backup()

            encoding_info = detected_encoding or "utf-8"
            all_results = [f"✅ {file_path}: 修改成功 (🔤 编码: {encoding_info})"]

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


__all__ = ["edit_file"]
