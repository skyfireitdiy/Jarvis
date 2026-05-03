"""普通文件编辑工具（基于 search/replace 的非结构化编辑）"""

import os
import shutil
import sys

from jarvis.jarvis_utils.config import (
    detect_file_encoding,
    get_default_encoding,
    read_text_file,
)
from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple


class EditFileNormalTool:
    """普通文件编辑工具，完全基于 search/replace 进行文件编辑"""

    name = "edit_file"
    description = (
        "使用 search/replace 或行号范围对文件进行普通文本编辑，支持同时修改多个文件。\n\n"
        "💡 使用方式：\n"
        "1. 直接指定要编辑的文件路径\n"
        "2. 为每个文件提供一组编辑操作（search/replace 或行号范围）\n"
        "3. 使用精确匹配查找 search 文本，找到匹配后替换为新文本\n\n"
        "🚀 特殊功能：\n"
        '- 当 search 为空字符串 "" 时，表示直接重写整个文件，replace 的内容将作为文件的完整新内容\n'
        "- 如果存在多个diffs且第一个diff的search为空字符串，将只应用第一个diff（重写整个文件），跳过后续所有diffs\n"
        "- **支持部分成功**：当某个文件的多个 diffs 中有部分失败时，已成功的修改仍会保留到文件中，并会详细报告每个 diff 的执行结果\n"
        "- **支持行号范围编辑**：通过 start_line 和 end_line 参数指定行范围，直接替换指定行范围内的内容\n\n"
        "⚠️ 提示：\n"
        "- search 使用精确字符串匹配，不支持正则表达式\n"
        "- **重要：search 必须提供足够的上下文来唯一定位目标位置**，避免匹配到错误的位置。建议包含：\n"
        "  * 目标代码的前后几行上下文（至少包含目标代码所在函数的签名或关键标识）\n"
        "  * 目标代码附近的唯一标识符（如函数名、变量名、注释等）\n"
        "  * 避免使用过短的 search 文本（如单个单词、短字符串），除非能确保唯一性\n"
        "- 如果某个 search 在文件中找不到精确匹配（search非空时），该 diff 会失败，但已成功的修改会保留\n"
        "- 建议在 search 中包含足够的上下文，确保能唯一匹配到目标位置，避免误匹配\n"
        "- 行号范围编辑模式：当指定 start_line 和 end_line 时，将忽略 search 参数，直接替换指定行范围（从1开始，end_line包含）"
    )

    parameters = {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "要修改的文件路径（支持绝对路径和相对路径）",
                        },
                        "diffs": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "search": {
                                        "type": "string",
                                        "description": '要搜索的原始文本（不支持正则表达式）。当为空字符串""时，表示直接重写整个文件，replace的内容将作为文件的完整新内容。非空时，**重要：必须提供足够的上下文来唯一定位目标位置**，建议包含目标代码的前后几行上下文、函数签名或唯一标识符，避免匹配到错误的位置。',
                                    },
                                    "replace": {
                                        "type": "string",
                                        "description": "替换后的文本（可以为空字符串）",
                                    },
                                    "replace_all": {
                                        "type": "boolean",
                                        "description": "是否替换所有匹配项。默认false：要求search唯一匹配；为true时允许替换全部匹配。",
                                    },
                                    "start_line": {
                                        "type": "integer",
                                        "description": "起始行号（从1开始），与 end_line 配合使用可按行号范围替换内容。当指定 start_line 和 end_line 时，将忽略 search 参数。",
                                    },
                                    "end_line": {
                                        "type": "integer",
                                        "description": "结束行号（包含此行），与 start_line 配合使用可按行号范围替换内容。",
                                    },
                                },
                                "required": ["replace"],
                            },
                            "description": "普通文本替换操作列表，按顺序依次应用到文件内容",
                        },
                    },
                    "required": ["file_path", "diffs"],
                },
                "description": "要修改的文件列表，每个文件包含文件路径和对应的 search/replace 操作列表",
            },
        },
        "required": ["files"],
    }

    def __init__(self) -> None:
        """初始化普通文件编辑工具"""
        pass

    @staticmethod
    def _validate_basic_args(args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """验证基本参数

        Returns:
            如果验证失败，返回错误响应；否则返回None
        """
        files = args.get("files")

        if not files:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必需参数：files",
            }

        if not isinstance(files, list):
            return {
                "success": False,
                "stdout": "",
                "stderr": "files参数必须是数组类型",
            }

        if len(files) == 0:
            return {
                "success": False,
                "stdout": "",
                "stderr": "files数组不能为空",
            }

        # 验证每个文件项
        for idx, file_item in enumerate(files):
            if not isinstance(file_item, dict):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"files数组第 {idx + 1} 项必须是字典类型",
                }

            file_path = file_item.get("file_path")
            diffs = file_item.get("diffs", [])

            if not file_path:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"files数组第 {idx + 1} 项缺少必需参数：file_path",
                }

            if not diffs:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"files数组第 {idx + 1} 项缺少必需参数：diffs",
                }

            if not isinstance(diffs, list):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"files数组第 {idx + 1} 项的diffs参数必须是数组类型",
                }

        return None

    @staticmethod
    def _get_preferred_encodings() -> List[str]:
        """获取工具级优先编码顺序。Windows 优先 gbk，其他平台优先 utf-8。"""
        if sys.platform == "win32":
            return ["gbk", "utf-8"]
        return ["utf-8", "gbk"]

    @staticmethod
    def _read_text_with_preferred_encoding(
        file_path: str,
    ) -> Tuple[str, Optional[str]]:
        """使用 detect_file_encoding 直接识别编码并读取文本文件。"""
        detected_encoding = detect_file_encoding(file_path)
        if detected_encoding:
            try:
                content = read_text_file(
                    file_path,
                    encoding=detected_encoding,
                    detect_encoding=False,
                    errors="strict",
                )
                return content, detected_encoding
            except (UnicodeDecodeError, LookupError):
                pass

        # 回退到默认读取方式
        content = read_text_file(file_path)
        return content, detected_encoding

    @staticmethod
    def _read_file_with_backup(
        file_path: str,
    ) -> Tuple[str, Optional[str], Optional[str]]:
        """读取文件并创建备份

        Args:
            file_path: 文件路径

        Returns:
            (文件内容, 备份文件路径或None, 检测到的编码或None)
        """
        abs_path = os.path.abspath(file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        file_content = ""
        backup_path = None
        detected_encoding = None
        if os.path.exists(abs_path):
            file_content, detected_encoding = (
                EditFileNormalTool._read_text_with_preferred_encoding(abs_path)
            )
            # 创建备份文件
            backup_path = abs_path + ".bak"
            try:
                shutil.copy2(abs_path, backup_path)
            except Exception:
                # 备份失败不影响主流程
                backup_path = None

        return file_content, backup_path, detected_encoding

    @staticmethod
    def _write_file_with_rollback(
        abs_path: str,
        content: str,
        backup_path: Optional[str],
        encoding: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """写入文件，失败时回滚

        Args:
            abs_path: 文件绝对路径
            content: 要写入的内容
            backup_path: 备份文件路径或None
            encoding: 指定编码，若为None则自动检测

        Returns:
            (是否成功, 错误信息或None)
        """
        enc = encoding or get_default_encoding()
        try:
            with open(abs_path, "w", encoding=enc, errors="replace") as f:
                f.write(content)
            return (True, None)
        except Exception as write_error:
            # 写入失败，尝试回滚
            if backup_path and os.path.exists(backup_path):
                try:
                    shutil.copy2(backup_path, abs_path)
                    os.remove(backup_path)
                except Exception:
                    pass
            error_msg = f"文件写入失败: {str(write_error)}"
            PrettyOutput.auto_print(f"❌ {error_msg}")
            return (False, error_msg)

    @staticmethod
    def _validate_normal_diff(
        diff: Dict[str, Any], idx: int
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """验证并转换 normal 类型的 diff

        Returns:
            (错误响应或None, 规范化后的diff或None)
        """
        search = diff.get("search")
        replace = diff.get("replace")
        replace_all = diff.get("replace_all", False)
        start_line = diff.get("start_line")
        end_line = diff.get("end_line")

        # 检查是否使用行号模式
        use_line_mode = start_line is not None or end_line is not None

        if use_line_mode:
            # 行号模式验证
            if start_line is None or end_line is None:
                return (
                    {
                        "success": False,
                        "stdout": "",
                        "stderr": f"第 {idx} 个diff使用行号模式时，必须同时提供start_line和end_line参数",
                    },
                    None,
                )
            if not isinstance(start_line, int) or not isinstance(end_line, int):
                return (
                    {
                        "success": False,
                        "stdout": "",
                        "stderr": f"第 {idx} 个diff的start_line和end_line参数必须是整数",
                    },
                    None,
                )
            if start_line < 1:
                return (
                    {
                        "success": False,
                        "stdout": "",
                        "stderr": f"第 {idx} 个diff的start_line必须大于等于1",
                    },
                    None,
                )
            if end_line < start_line:
                return (
                    {
                        "success": False,
                        "stdout": "",
                        "stderr": f"第 {idx} 个diff的end_line必须大于等于start_line",
                    },
                    None,
                )
            return (
                None,
                {
                    "replace": replace,
                    "start_line": start_line,
                    "end_line": end_line,
                },
            )
        else:
            # search/replace 模式验证
            if search is None:
                return (
                    {
                        "success": False,
                        "stdout": "",
                        "stderr": f"第 {idx} 个diff缺少search参数",
                    },
                    None,
                )
            if not isinstance(search, str):
                return (
                    {
                        "success": False,
                        "stdout": "",
                        "stderr": f"第 {idx} 个diff的search参数必须是字符串",
                    },
                    None,
                )
            # 允许空字符串作为search参数，表示直接重写整个文件
            if replace is None:
                return (
                    {
                        "success": False,
                        "stdout": "",
                        "stderr": f"第 {idx} 个diff缺少replace参数",
                    },
                    None,
                )
            if not isinstance(replace, str):
                return (
                    {
                        "success": False,
                        "stdout": "",
                        "stderr": f"第 {idx} 个diff的replace参数必须是字符串",
                    },
                    None,
                )
            if not isinstance(replace_all, bool):
                return (
                    {
                        "success": False,
                        "stdout": "",
                        "stderr": f"第 {idx} 个diff的replace_all参数必须是布尔值",
                    },
                    None,
                )
            return (
                None,
                {
                    "search": search,
                    "replace": replace,
                    "replace_all": replace_all,
                },
            )

    @staticmethod
    def _normalize_line_endings(text: str) -> str:
        """统一换行符，便于进行保守的等价匹配。"""
        return text.replace("\r\n", "\n").replace("\r", "\n")

    @staticmethod
    def _normalize_quotes(text: str) -> str:
        """归一化常见引号风格，便于在文件中定位实际匹配文本。"""
        return (
            text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
        )

    @staticmethod
    def _find_actual_search_text(content: str, search_text: str) -> Optional[str]:
        """查找文件中的实际匹配文本。

        先尝试精确匹配；若失败，再尝试基于换行和引号归一化后的定位，
        并从原始文件内容中截取实际匹配片段。
        """
        if not search_text:
            return search_text

        if search_text in content:
            return search_text

        normalized_content = EditFileNormalTool._normalize_quotes(
            EditFileNormalTool._normalize_line_endings(content)
        )
        normalized_search = EditFileNormalTool._normalize_quotes(
            EditFileNormalTool._normalize_line_endings(search_text)
        )
        search_index = normalized_content.find(normalized_search)
        if search_index == -1:
            return None
        return content[search_index : search_index + len(search_text)]

    @staticmethod
    def _is_opening_quote_context(characters: List[str], index: int) -> bool:
        """判断当前位置的引号是否处于开引号上下文。"""
        if index == 0:
            return True
        previous_character = characters[index - 1]
        return previous_character in {" ", "\t", "\n", "\r", "(", "[", "{", "—", "–"}

    @staticmethod
    def _apply_curly_double_quotes(text: str) -> str:
        """将直双引号转换为弯双引号。"""
        characters = list(text)
        result: List[str] = []
        for index, character in enumerate(characters):
            if character == '"':
                result.append(
                    "“"
                    if EditFileNormalTool._is_opening_quote_context(characters, index)
                    else "”"
                )
            else:
                result.append(character)
        return "".join(result)

    @staticmethod
    def _apply_curly_single_quotes(text: str) -> str:
        """将直单引号转换为弯单引号，同时保留常见缩写中的撇号。"""
        characters = list(text)
        result: List[str] = []
        for index, character in enumerate(characters):
            if character != "'":
                result.append(character)
                continue

            previous_character = characters[index - 1] if index > 0 else ""
            next_character = (
                characters[index + 1] if index < len(characters) - 1 else ""
            )
            if previous_character.isalpha() and next_character.isalpha():
                result.append("’")
                continue

            result.append(
                "‘"
                if EditFileNormalTool._is_opening_quote_context(characters, index)
                else "’"
            )
        return "".join(result)

    @staticmethod
    def _preserve_quote_style(
        search_text: str, actual_search_text: str, replace_text: str
    ) -> str:
        """当 search 因引号归一化匹配到实际文本时，尽量保持实际文本中的弯引号风格。"""
        if search_text == actual_search_text:
            return replace_text

        has_curly_double_quotes = "“" in actual_search_text or "”" in actual_search_text
        has_curly_single_quotes = "‘" in actual_search_text or "’" in actual_search_text

        styled_replace_text = replace_text
        if has_curly_double_quotes:
            styled_replace_text = EditFileNormalTool._apply_curly_double_quotes(
                styled_replace_text
            )
        if has_curly_single_quotes:
            styled_replace_text = EditFileNormalTool._apply_curly_single_quotes(
                styled_replace_text
            )
        return styled_replace_text

    @staticmethod
    def _count_matches(content: str, search_text: str) -> int:
        """统计文本在内容中的匹配次数

        Args:
            content: 文件内容
            search_text: 要搜索的文本

        Returns:
            匹配次数
        """
        if not search_text:
            return 0
        return content.count(search_text)

    @staticmethod
    def _is_file_in_workspace_subdir(file_path: str) -> bool:
        """检查文件是否在当前工作目录的子级目录下

        Args:
            file_path: 文件路径（可以是绝对路径或相对路径）

        Returns:
            True 如果文件在当前工作目录的子级目录下，False 否则
        """
        try:
            abs_file_path = os.path.abspath(file_path)
            abs_workspace_path = os.path.abspath(os.getcwd())

            # 检查文件路径是否以工作目录路径开头
            # 使用 os.path.commonpath 来正确处理路径
            try:
                common_path = os.path.commonpath([abs_file_path, abs_workspace_path])
                # 如果公共路径等于工作目录路径，说明文件在工作目录或其子目录下
                return os.path.abspath(common_path) == abs_workspace_path
            except ValueError:
                # 如果路径不在同一驱动器上（Windows），commonpath 会抛出 ValueError
                return False
        except Exception:
            # 如果出现任何异常，默认返回 False
            return False

    @staticmethod
    def _generate_diff_preview(
        original_content: str,
        modified_content: str,
        file_path: str,
    ) -> str:
        """生成修改后的预览diff

        Args:
            original_content: 原始文件内容
            modified_content: 修改后的文件内容
            file_path: 文件路径

        Returns:
            预览diff字符串
        """
        import difflib

        # 生成统一的diff格式
        original_lines = original_content.splitlines(keepends=True)
        modified_lines = modified_content.splitlines(keepends=True)

        # 使用difflib生成统一的diff
        diff = list(
            difflib.unified_diff(
                original_lines,
                modified_lines,
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                lineterm="",
            )
        )

        diff_preview = "".join(diff)
        return diff_preview

    @staticmethod
    def _apply_normal_edits_to_content(
        original_content: str,
        diffs: List[Dict[str, Any]],
        file_path: Optional[str] = None,
    ) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """对文件内容按顺序应用普通 search/replace 编辑。"""
        content = original_content
        diff_results: List[Dict[str, Any]] = []
        all_success = True

        for idx, diff in enumerate(diffs, start=1):
            # 检查是否使用行号模式
            start_line = diff.get("start_line")
            end_line = diff.get("end_line")

            if start_line is not None and end_line is not None:
                # 行号范围编辑模式
                replace = diff["replace"]
                lines = content.splitlines(keepends=True)
                total_lines = len(lines)

                # 验证行号范围
                if start_line > total_lines:
                    all_success = False
                    error_info = (
                        f"start_line ({start_line}) 超出文件总行数 ({total_lines})"
                    )
                    diff_results.append(
                        {"idx": idx, "success": False, "error": error_info}
                    )
                    continue

                # 构建新内容：保留 start_line 之前的行 + 替换内容 + 保留 end_line 之后的行
                before_lines = lines[
                    : start_line - 1
                ]  # start_line 之前的行（0-indexed）
                after_lines = (
                    lines[end_line:] if end_line < total_lines else []
                )  # end_line 之后的行

                # 确保替换内容以换行符结尾（如果后面还有行）
                replace_content = replace
                if after_lines and not replace_content.endswith("\n"):
                    replace_content += "\n"

                # 组合新内容
                new_content_parts = []
                if before_lines:
                    new_content_parts.append("".join(before_lines))
                new_content_parts.append(replace_content)
                if after_lines:
                    if not replace_content.endswith("\n") and new_content_parts:
                        new_content_parts.append("\n")
                    new_content_parts.append("".join(after_lines))

                content = "".join(new_content_parts)
                diff_results.append({"idx": idx, "success": True, "error": None})
                continue

            # search/replace 模式
            search = diff.get("search")
            replace = diff["replace"]
            replace_all = diff.get("replace_all", False)

            # 处理空字符串search的特殊情况
            if search == "":
                # 空字符串表示直接重写整个文件
                content = replace
                # 记录这个 diff 成功
                diff_results.append({"idx": idx, "success": True, "error": None})
                # 空search只处理第一个diff，跳过后续所有diffs
                break

            # 检查 search 和 replace 是否完全一致（无效操作）
            if search == replace:
                all_success = False
                error_info = (
                    "search 和 replace 内容完全相同，这是一个无效操作（没有实际修改）"
                )
                diff_results.append({"idx": idx, "success": False, "error": error_info})
                continue  # 继续处理后续 diffs

            # 验证 search 文本
            if not isinstance(search, str):
                all_success = False
                error_info = "search 文本必须是字符串"
                diff_results.append({"idx": idx, "success": False, "error": error_info})
                continue

            actual_search = EditFileNormalTool._find_actual_search_text(content, search)
            if actual_search is None:
                all_success = False
                error_info = "未找到可匹配的文本"
                if search:
                    error_info += f"\n搜索文本: {search[:200]}..."
                    error_info += (
                        "\n💡 提示：如果搜索文本在文件中存在但未找到匹配，可能是因为："
                    )
                    error_info += "\n   1. 搜索文本包含不可见字符或格式不匹配（建议检查空格、换行等）"
                    error_info += (
                        "\n   2. 文件中的实际文本与 search 存在引号或换行风格差异"
                    )
                    error_info += "\n   3. **文件可能已被更新**：如果文件在其他地方被修改了，搜索文本可能已经不存在或已改变"
                    if file_path:
                        error_info += f"\n   💡 建议：使用 `read_code` 工具重新读取文件 `{file_path}` 查看当前内容，"
                        error_info += "\n      确认文件是否已被更新，然后根据实际内容调整 search 文本"
                diff_results.append({"idx": idx, "success": False, "error": error_info})
                continue

            styled_replace = EditFileNormalTool._preserve_quote_style(
                search, actual_search, replace
            )
            match_count = EditFileNormalTool._count_matches(content, actual_search)

            if match_count == 1:
                content = content.replace(actual_search, styled_replace, 1)
                diff_results.append({"idx": idx, "success": True, "error": None})
            elif replace_all:
                content = content.replace(actual_search, styled_replace)
                diff_results.append({"idx": idx, "success": True, "error": None})
            else:
                all_success = False
                error_info = (
                    f"search 文本匹配到 {match_count} 处，但 replace_all=false，不会自动替换全部匹配。"
                    "\n💡 建议：提供更精确的上下文以唯一定位目标位置，或显式设置 replace_all=true。"
                )
                diff_results.append({"idx": idx, "success": False, "error": error_info})
                continue

        return all_success, content, diff_results

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行普通 search/replace 文件编辑操作（支持同时修改多个文件）"""
        try:
            # 验证基本参数（files 结构）
            error_response = EditFileNormalTool._validate_basic_args(args)
            if error_response:
                return error_response

            files = args.get("files", [])
            # 获取 agent 实例（v1.0 协议中 agent 在 args 中）
            agent = args.get("agent")

            all_results = []
            overall_success = True
            successful_files = []
            failed_files = []

            for file_item in files:
                file_path = file_item.get("file_path")
                diffs = file_item.get("diffs", [])

                # 校验并规范化 diffs
                normalized_diffs: List[Dict[str, Any]] = []
                for idx, diff in enumerate(diffs, start=1):
                    if not isinstance(diff, dict):
                        all_results.append(
                            f"❌ {file_path}: 第 {idx} 个diff必须是字典类型"
                        )
                        failed_files.append(file_path)
                        overall_success = False
                        normalized_diffs = []
                        break

                    error, normalized = EditFileNormalTool._validate_normal_diff(
                        diff, idx
                    )
                    if error:
                        all_results.append(
                            f"❌ {file_path}: {error.get('stderr', '参数验证失败')}"
                        )
                        failed_files.append(file_path)
                        overall_success = False
                        normalized_diffs = []
                        break

                    if normalized is not None:
                        normalized_diffs.append(normalized)

                if not normalized_diffs:
                    # 该文件的diffs有问题，已记录错误，跳过
                    continue

                # 读取原始内容并创建备份
                (
                    original_content,
                    backup_path,
                    detected_encoding,
                ) = EditFileNormalTool._read_file_with_backup(file_path)

                success, result_or_error, diff_results = (
                    EditFileNormalTool._apply_normal_edits_to_content(
                        original_content,
                        normalized_diffs,
                        file_path=file_path,
                    )
                )

                if not success:
                    error_msg_parts = []
                    for diff_result in diff_results:
                        if not diff_result.get("success"):
                            error_msg_parts.append(
                                f"Diff #{diff_result.get('idx')}: {diff_result.get('error', '未知错误')}"
                            )
                    result_or_error = (
                        "\n".join(error_msg_parts)
                        if error_msg_parts
                        else "处理失败：未知错误"
                    )

                    # 处理失败
                    if backup_path and os.path.exists(backup_path):
                        try:
                            os.remove(backup_path)
                        except Exception:
                            pass
                    all_results.append(f"❌ {file_path}: {result_or_error}")
                    failed_files.append(file_path)
                    overall_success = False
                    continue

                # 编辑成功，继续写入文件
                result_or_error = result_or_error  # 此时 result_or_error 是新内容

                # 写入文件（失败时回滚）
                abs_path = os.path.abspath(file_path)
                (
                    write_success,
                    write_error,
                ) = EditFileNormalTool._write_file_with_rollback(
                    abs_path, result_or_error, backup_path, detected_encoding
                )
                if write_success:
                    # 写入成功，删除备份文件
                    if backup_path and os.path.exists(backup_path):
                        try:
                            os.remove(backup_path)
                        except Exception:
                            pass

                    # 检查文件是否不在当前工作目录的子级目录下
                    # 如果不在，生成并打印 diff
                    in_workspace = EditFileNormalTool._is_file_in_workspace_subdir(
                        abs_path
                    )

                    if not (
                        agent and agent.agent_type() == "code_agent" and in_workspace
                    ):
                        try:
                            # 生成 diff
                            diff_text = EditFileNormalTool._generate_diff_preview(
                                original_content,
                                result_or_error,
                                file_path,
                            )

                            # 打印 diff（使用 diff_visualizer）
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

                            # 将 diff 添加到 stdout
                            all_results.append(
                                f"\n📝 {file_path} 的 diff（文件不在当前工作目录的子级目录下）:"
                            )
                            all_results.append(diff_text)
                        except Exception as diff_error:
                            # diff 生成或打印失败不影响主流程
                            PrettyOutput.auto_print(
                                f"⚠️ 生成 diff 时出错: {str(diff_error)}"
                            )

                    # 检查是否是部分成功（有失败的 diff）
                    failed_diffs = [dr for dr in diff_results if not dr.get("success")]
                    if failed_diffs:
                        # 部分成功，生成详细报告
                        success_count = sum(
                            1 for dr in diff_results if dr.get("success")
                        )
                        all_results.append(
                            f"⚠️ {file_path}: 部分成功 ({success_count}/{len(diff_results)} 个diff成功)"
                        )
                        # 添加每个 diff 的详细信息
                        for dr in diff_results:
                            idx = dr.get("idx", 0)
                            if dr.get("success"):
                                all_results.append(f"   ✅ Diff #{idx}: 成功")
                            else:
                                error = dr.get("error", "未知错误")
                                # 简化错误信息显示（每行错误缩进显示）
                                for line in error.split("\n"):
                                    all_results.append(f"   ❌ Diff #{idx}: {line}")
                        successful_files.append(
                            file_path
                        )  # 仍然算作成功文件（部分成功也算成功）
                        # 部分成功时，不将文件添加到 failed_files，因为文件已成功写入
                        # 但需要将整体操作标记为失败
                        overall_success = False
                    else:
                        encoding_info = detected_encoding or "utf-8"
                        all_results.append(
                            f"✅ {file_path}: 修改成功 (🔤 编码: {encoding_info})"
                        )
                        successful_files.append((file_path, encoding_info))
                else:
                    all_results.append(f"❌ {file_path}: {write_error}")
                    failed_files.append(file_path)
                    overall_success = False

            # 构建输出信息
            output_lines = []
            if successful_files:
                output_lines.append(f"✅ 成功修改 {len(successful_files)} 个文件:")
                for file_path, encoding in successful_files:
                    output_lines.append(f"   - {file_path} (🔤 编码: {encoding})")

            if failed_files:
                output_lines.append(f"\n❌ 失败 {len(failed_files)} 个文件:")
                for file_path in failed_files:
                    output_lines.append(f"   - {file_path}")

            stdout_text = "\n".join(all_results)
            summary = "\n".join(output_lines) if output_lines else ""

            if overall_success:
                return {
                    "success": True,
                    "stdout": stdout_text + ("\n\n" + summary if summary else ""),
                    "stderr": "",
                }
            else:
                # 失败时，stderr 应该包含详细的错误信息，而不仅仅是文件列表
                # 从 all_results 中提取失败和部分成功的详细错误信息
                failed_details = []
                for result in all_results:
                    # 提取失败信息（包含❌）和部分成功的警告（包含⚠️）
                    # 检查是否包含这些标记，而不是只检查开头，因为详细错误信息可能有缩进
                    if "❌" in result or "⚠️" in result:
                        failed_details.append(result)

                # 如果有详细的错误信息，使用它们；否则使用 summary
                stderr_content = (
                    "\n".join(failed_details)
                    if failed_details
                    else (summary if summary else "部分文件修改失败")
                )

                return {
                    "success": False,
                    "stdout": stdout_text + ("\n\n" + summary if summary else ""),
                    "stderr": stderr_content,
                }

        except Exception as e:
            error_msg = f"文件编辑失败: {str(e)}"
            PrettyOutput.auto_print(f"❌ {error_msg}")
            return {"success": False, "stdout": "", "stderr": error_msg}


__all__ = ["EditFileNormalTool"]
