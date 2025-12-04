# -*- coding: utf-8 -*-
"""自由文件编辑工具（支持 diff 格式）"""

import difflib
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from jarvis.jarvis_tools.edit_file_structed import EditFileTool


class EditFileFreeTool:
    """自由文件编辑工具，支持 diff 格式（+/-/空格）自动识别"""

    name = "edit_file_free"
    description = (
        "基于 diff 格式自动定位并编辑文件的工具，支持同时修改多个文件。\n\n"
        "💡 使用方式：\n"
        "1. 提供要修改的文件路径\n"
        "2. 提供 diff 格式的内容（+表示新增、-表示删除、空格表示不变）\n"
        "3. 工具会自动识别 diff 格式，查找匹配位置并进行编辑\n\n"
        "📝 Diff 格式说明：\n"
        "- 以 `+` 开头的行：新增的代码\n"
        "- 以 `-` 开头的行：删除的代码\n"
        "- 以空格开头的行：不变的代码（用于上下文匹配）\n"
        "- 工具会自动识别是否为 diff 格式，如果不是则按普通代码处理\n\n"
        "📝 工作原理：\n"
        "- 如果内容包含 diff 格式（有 `+` 或 `-` 前缀），工具会解析出旧代码和新代码\n"
        "- 使用旧代码在文件中查找匹配位置（模糊匹配，相似度阈值 0.7）\n"
        "- 找到匹配后，用新代码替换匹配的旧代码\n"
        "- 如果找不到匹配或相似度低于阈值，操作会失败\n\n"
        "⚠️ 重要提示：\n"
        "- 必须提供足够的上下文（空格开头的行）以确保能够准确匹配\n"
        "- 如果匹配失败，请检查代码上下文是否正确，或增加更多上下文行\n"
        "- 如果内容不包含 diff 格式，工具会按普通代码片段处理（查找相似代码并替换）"
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
                                    "content": {
                                        "type": "string",
                                        "description": "代码内容，支持 diff 格式（+/-/空格）或普通代码片段",
                                    },
                                },
                                "required": ["content"],
                            },
                            "description": "编辑操作列表，每个操作包含代码内容（支持 diff 格式）",
                        },
                    },
                    "required": ["file_path", "diffs"],
                },
                "description": "要修改的文件列表，每个文件包含文件路径和对应的编辑操作列表",
            },
        },
        "required": ["files"],
    }

    def __init__(self):
        """初始化自由文件编辑工具"""
        pass

    @staticmethod
    def _validate_basic_args(args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """验证基本参数（与结构化编辑保持一致的 files 验证逻辑）"""
        return EditFileTool._validate_basic_args(args)

    @staticmethod
    def _is_diff_format(content: str) -> bool:
        """判断内容是否为 diff 格式

        Args:
            content: 代码内容

        Returns:
            True 如果是 diff 格式，False 否则
        """
        lines = content.splitlines()
        if not lines:
            return False

        # 检查是否有以 + 或 - 开头的行（排除以 +++ 或 --- 开头的，这些可能是其他格式）
        has_plus = False
        has_minus = False
        for line in lines:
            if line.startswith("+") and not line.startswith("+++"):
                has_plus = True
            if line.startswith("-") and not line.startswith("---"):
                has_minus = True
            if has_plus or has_minus:
                break

        return has_plus or has_minus

    @staticmethod
    def _parse_diff_content(content: str) -> Tuple[str, str]:
        """解析 diff 格式内容，提取旧代码和新代码

        Args:
            content: diff 格式的内容

        Returns:
            (旧代码, 新代码)
        """
        lines = content.splitlines(keepends=True)
        old_lines = []
        new_lines = []

        for line in lines:
            if line.startswith(" "):
                # 空格开头：不变的代码，同时出现在旧代码和新代码中
                # 去掉前缀空格
                code_line = line[1:] if len(line) > 1 else line
                old_lines.append(code_line)
                new_lines.append(code_line)
            elif line.startswith("-"):
                # - 开头：删除的代码，只出现在旧代码中
                # 去掉前缀 -
                code_line = line[1:] if len(line) > 1 else line
                old_lines.append(code_line)
            elif line.startswith("+"):
                # + 开头：新增的代码，只出现在新代码中
                # 去掉前缀 +
                code_line = line[1:] if len(line) > 1 else line
                new_lines.append(code_line)
            else:
                # 其他情况：按空格处理（不变）
                old_lines.append(line)
                new_lines.append(line)

        old_code = "".join(old_lines)
        new_code = "".join(new_lines)

        return old_code, new_code

    @staticmethod
    def _validate_free_diff(
        diff: Dict[str, Any], idx: int
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """验证并转换 free 类型的 diff

        Returns:
            (错误响应或None, 规范化后的diff或None)
        """
        content = diff.get("content")

        if content is None:
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx} 个diff缺少content参数",
                },
                None,
            )
        if not isinstance(content, str):
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx} 个diff的content参数必须是字符串",
                },
                None,
            )
        if content.strip() == "":
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx} 个diff的content参数不能为空",
                },
                None,
            )

        # 判断是否为 diff 格式
        is_diff = EditFileFreeTool._is_diff_format(content)

        if is_diff:
            # 解析 diff 格式
            old_code, new_code = EditFileFreeTool._parse_diff_content(content)
            return (
                None,
                {
                    "content": content,
                    "is_diff": True,
                    "old_code": old_code,
                    "new_code": new_code,
                },
            )
        else:
            # 普通代码格式
            return (
                None,
                {
                    "content": content,
                    "is_diff": False,
                    "old_code": content,  # 普通代码时，旧代码和新代码相同
                    "new_code": content,
                },
            )

    @staticmethod
    def _extract_code_features(code: str) -> Dict[str, Any]:
        """提取代码特征用于匹配

        Args:
            code: 代码片段

        Returns:
            特征字典
        """
        features = {
            "function_names": [],
            "class_names": [],
            "imports": [],
            "keywords": [],
        }

        # 提取函数定义
        function_pattern = r"def\s+(\w+)\s*\("
        functions = re.findall(function_pattern, code)
        features["function_names"] = functions

        # 提取类定义
        class_pattern = r"class\s+(\w+)"
        classes = re.findall(class_pattern, code)
        features["class_names"] = classes

        # 提取导入语句
        import_pattern = r"^(?:from\s+\S+\s+)?import\s+(\S+)"
        imports = re.findall(import_pattern, code, re.MULTILINE)
        features["imports"] = imports

        # 提取关键标识符（变量名、函数调用等）
        identifier_pattern = r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b"
        identifiers = re.findall(identifier_pattern, code)
        # 过滤掉 Python 关键字
        python_keywords = {
            "def",
            "class",
            "import",
            "from",
            "if",
            "else",
            "elif",
            "for",
            "while",
            "return",
            "pass",
            "break",
            "continue",
            "try",
            "except",
            "finally",
            "with",
            "as",
            "and",
            "or",
            "not",
            "in",
            "is",
            "None",
            "True",
            "False",
        }
        keywords = [id for id in identifiers if id not in python_keywords]
        features["keywords"] = list(set(keywords))[:10]  # 最多保留10个

        return features

    @staticmethod
    def _find_best_match_position(
        content: str, old_code: str, use_context_lines: bool = False
    ) -> Tuple[Optional[Tuple[int, int, float]], Optional[str]]:
        """在文件中查找最佳匹配位置

        Args:
            content: 文件内容
            old_code: 要匹配的旧代码片段
            use_context_lines: 如果为 True，使用前几行和后几行分别匹配（用于非 diff 格式）

        Returns:
            ((start_pos, end_pos, similarity), error_msg) 或 (None, error_msg)
        """
        content_lines = content.splitlines(keepends=True)
        old_code_lines = old_code.splitlines(keepends=True)

        if len(old_code_lines) == 0:
            return None, "old_code 不能为空"

        # 使用代码片段进行模糊匹配（不依赖特定编程语言特性）
        old_code_stripped = old_code.strip()
        if not old_code_stripped:
            return None, "old_code 不能只包含空白字符"

        # 提取核心代码（去除前后空白行）
        old_code_core_lines = []
        for line in old_code_lines:
            if line.strip():
                old_code_core_lines.append(line)
        if not old_code_core_lines:
            return None, "old_code 不能只包含空白行"

        old_code_core = "".join(old_code_core_lines)
        core_line_count = len(old_code_core_lines)

        best_match: Optional[Tuple[int, int, float]] = None
        best_similarity = 0.0

        if use_context_lines:
            # 非 diff 格式：使用前几行和后几行分别匹配
            # 使用前 3 行和后 3 行作为上下文（如果代码足够长）
            context_lines = 3
            if core_line_count <= context_lines * 2:
                # 如果代码太短，使用全部代码匹配
                prefix_code = old_code_core
                suffix_code = old_code_core
            else:
                # 提取前几行和后几行
                prefix_lines = old_code_core_lines[:context_lines]
                suffix_lines = old_code_core_lines[-context_lines:]
                prefix_code = "".join(prefix_lines)
                suffix_code = "".join(suffix_lines)

            # 先匹配前缀（前几行）
            prefix_match: Optional[Tuple[int, float]] = None
            prefix_similarity = 0.0
            for start_line in range(len(content_lines)):
                for line_diff in [-1, 0, 1]:
                    end_line = start_line + len(prefix_lines) + line_diff
                    if end_line <= start_line or end_line > len(content_lines):
                        continue

                    window_lines = content_lines[start_line:end_line]
                    window_content = "".join(window_lines)

                    if not window_content.strip():
                        continue

                    similarity = difflib.SequenceMatcher(
                        None, prefix_code, window_content, autojunk=False
                    ).ratio()

                    if similarity > prefix_similarity:
                        prefix_similarity = similarity
                        start_pos = sum(
                            len(content_lines[i]) for i in range(start_line)
                        )
                        prefix_match = (start_pos, similarity)

                    if similarity >= 0.95:
                        break
                if prefix_similarity >= 0.95:
                    break

            # 如果前缀匹配成功（相似度 >= 0.7），继续匹配后缀
            if prefix_match and prefix_similarity >= 0.7:
                prefix_start_pos, _ = prefix_match
                # 在前缀匹配位置之后查找后缀
                prefix_start_line = 0
                for i, line in enumerate(content_lines):
                    if sum(len(content_lines[j]) for j in range(i)) >= prefix_start_pos:
                        prefix_start_line = i
                        break

                suffix_match: Optional[Tuple[int, float]] = None
                suffix_similarity = 0.0
                # 在前缀之后查找后缀（最多向后搜索 50 行）
                search_end = min(len(content_lines), prefix_start_line + 50)
                for start_line in range(prefix_start_line, search_end):
                    for line_diff in [-1, 0, 1]:
                        end_line = start_line + len(suffix_lines) + line_diff
                        if end_line <= start_line or end_line > len(content_lines):
                            continue

                        window_lines = content_lines[start_line:end_line]
                        window_content = "".join(window_lines)

                        if not window_content.strip():
                            continue

                        similarity = difflib.SequenceMatcher(
                            None, suffix_code, window_content, autojunk=False
                        ).ratio()

                        if similarity > suffix_similarity:
                            suffix_similarity = similarity
                            suffix_start_pos = sum(
                                len(content_lines[i]) for i in range(start_line)
                            )
                            suffix_match = (suffix_start_pos, similarity)

                        if similarity >= 0.95:
                            break
                    if suffix_similarity >= 0.95:
                        break

                # 如果前后缀都匹配成功，计算综合相似度
                if suffix_match and suffix_similarity >= 0.7:
                    suffix_start_pos, _ = suffix_match
                    # 综合相似度取平均值
                    combined_similarity = (prefix_similarity + suffix_similarity) / 2.0
                    # 返回插入位置（前缀位置）
                    return (
                        prefix_start_pos,
                        prefix_start_pos,
                        combined_similarity,
                    ), None

            # 如果前后缀匹配失败，回退到使用全部代码匹配
            use_context_lines = False

        if not use_context_lines:
            # 在文件中滑动窗口查找最相似的片段
            # 限制搜索范围，避免匹配到空内容或过短的内容
            for start_line in range(len(content_lines)):
                # 尝试匹配不同长度的代码块
                for line_diff in [-2, -1, 0, 1, 2]:
                    end_line = start_line + core_line_count + line_diff
                    if end_line <= start_line or end_line > len(content_lines):
                        continue

                    window_lines = content_lines[start_line:end_line]
                    window_content = "".join(window_lines)

                    # 跳过空内容或过短的内容
                    if (
                        not window_content.strip()
                        or len(window_content.strip())
                        < len(old_code_core.strip()) * 0.3
                    ):
                        continue

                    # 计算相似度
                    similarity = difflib.SequenceMatcher(
                        None, old_code_core, window_content, autojunk=False
                    ).ratio()

                    if similarity > best_similarity:
                        best_similarity = similarity
                        # 计算字符位置
                        start_pos = sum(
                            len(content_lines[i]) for i in range(start_line)
                        )
                        end_pos = start_pos + len(window_content)
                        best_match = (start_pos, end_pos, similarity)

                    # 如果找到很好的匹配，提前退出
                    if similarity >= 0.95:
                        break

                # 如果已经找到很好的匹配，可以提前退出
                if best_similarity >= 0.95:
                    break

        # 只有当相似度足够高时才返回匹配（阈值 0.6，但调用者会根据情况进一步过滤）
        if best_match is not None and best_similarity >= 0.6:
            return best_match, None

        # 如果找不到匹配，返回 None（表示需要追加）
        return None, None

    @staticmethod
    def _apply_free_edit_to_content(
        content: str, diff: Dict[str, Any]
    ) -> Tuple[bool, str, Optional[str]]:
        """对文件内容应用自由编辑

        Returns:
            (是否成功, 新内容或错误信息, 警告信息)
        """
        is_diff = diff.get("is_diff", False)
        old_code = diff.get("old_code", "")
        new_code = diff.get("new_code", "")

        # 如果是 diff 格式且旧代码为空（只有新增），直接失败
        if is_diff and not old_code.strip():
            return False, "diff 格式中旧代码为空，无法确定插入位置", None

        # 确定用于匹配的代码和相似度阈值
        # 如果是 diff 格式，使用 old_code 来匹配
        # 如果不是 diff 格式，使用 new_code 的前几行和后几行分别匹配
        # 相似度阈值统一设置为 0.7
        if is_diff:
            match_code = old_code
            use_context_lines = False
        else:
            match_code = new_code
            use_context_lines = True  # 非 diff 格式使用前后几行分别匹配
        min_similarity = 0.7

        # 尝试查找匹配位置
        match_result, error_msg = EditFileFreeTool._find_best_match_position(
            content, match_code, use_context_lines=use_context_lines
        )

        if match_result is None:
            # 找不到匹配则直接失败
            if error_msg:
                return False, f"未找到匹配位置: {error_msg}", None
            else:
                return False, "未找到匹配位置，请检查代码上下文是否正确", None

        start_pos, end_pos, similarity = match_result

        # 如果相似度太低，视为未找到匹配，直接失败
        if similarity < min_similarity:
            return (
                False,
                f"匹配相似度较低 ({similarity:.2%})，低于阈值 ({min_similarity:.2%})，请检查代码上下文是否正确",
                None,
            )

        # 检查相似度
        warning = None
        if similarity < 0.8:
            warning = (
                f"⚠️ 匹配相似度较低 ({similarity:.2%})，"
                f"请确认替换位置是否正确。匹配位置: 字符 {start_pos}-{end_pos}"
            )

        # 执行替换或插入
        if is_diff:
            # diff 格式：替换匹配的旧代码
            new_content = content[:start_pos] + new_code + content[end_pos:]
        else:
            # 非 diff 格式：在匹配位置插入新代码
            # 如果匹配位置是同一个位置（前后缀匹配），则在该位置插入
            if start_pos == end_pos:
                new_content = content[:start_pos] + new_code + content[start_pos:]
            else:
                # 如果匹配到了代码块，替换它
                new_content = content[:start_pos] + new_code + content[end_pos:]

        return True, new_content, warning

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行自由文件编辑操作（支持同时修改多个文件）"""
        try:
            # 验证基本参数（files 结构）
            error_response = EditFileFreeTool._validate_basic_args(args)
            if error_response:
                return error_response

            files = args.get("files", [])

            # 记录 PATCH 操作调用统计
            try:
                from jarvis.jarvis_stats.stats import StatsManager

                StatsManager.increment("patch_free", group="tool")
            except Exception:
                pass

            all_results = []
            overall_success = True
            successful_files = []
            failed_files = []
            warnings = []

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

                    error, normalized = EditFileFreeTool._validate_free_diff(diff, idx)
                    if error:
                        all_results.append(
                            f"❌ {file_path}: {error.get('stderr', '参数验证失败')}"
                        )
                        failed_files.append(file_path)
                        overall_success = False
                        normalized_diffs = []
                        break

                    normalized_diffs.append(normalized)

                if not normalized_diffs:
                    # 该文件的diffs有问题，已记录错误，跳过
                    continue

                # 读取原始内容并创建备份
                original_content, backup_path = EditFileTool._read_file_with_backup(
                    file_path
                )

                # 按顺序应用所有自由编辑
                current_content = original_content
                file_warnings = []

                for idx, diff in enumerate(normalized_diffs, start=1):
                    success, result_or_error, warning = (
                        EditFileFreeTool._apply_free_edit_to_content(
                            current_content, diff
                        )
                    )

                    if not success:
                        # 不写入文件，删除备份文件
                        if backup_path and os.path.exists(backup_path):
                            try:
                                os.remove(backup_path)
                            except Exception:
                                pass
                        all_results.append(
                            f"❌ {file_path}: 第 {idx} 个diff失败 - {result_or_error}"
                        )
                        failed_files.append(file_path)
                        overall_success = False
                        current_content = None
                        break

                    current_content = result_or_error
                    if warning:
                        file_warnings.append(f"第 {idx} 个diff: {warning}")

                if current_content is None:
                    # 编辑失败，已处理
                    continue

                # 写入文件（失败时回滚）
                abs_path = os.path.abspath(file_path)
                write_success, write_error = EditFileTool._write_file_with_rollback(
                    abs_path, current_content, backup_path
                )
                if write_success:
                    # 写入成功，删除备份文件
                    if backup_path and os.path.exists(backup_path):
                        try:
                            os.remove(backup_path)
                        except Exception:
                            pass
                    result_msg = f"✅ {file_path}: 修改成功"
                    if file_warnings:
                        result_msg += "\n" + "\n".join(f"  {w}" for w in file_warnings)
                    all_results.append(result_msg)
                    successful_files.append(file_path)
                    warnings.extend([f"{file_path}: {w}" for w in file_warnings])
                else:
                    all_results.append(f"❌ {file_path}: {write_error}")
                    failed_files.append(file_path)
                    overall_success = False

            # 构建输出信息
            output_lines = []
            if successful_files:
                output_lines.append(f"✅ 成功修改 {len(successful_files)} 个文件:")
                for file_path in successful_files:
                    output_lines.append(f"   - {file_path}")

            if failed_files:
                output_lines.append(f"\n❌ 失败 {len(failed_files)} 个文件:")
                for file_path in failed_files:
                    output_lines.append(f"   - {file_path}")

            if warnings:
                output_lines.append(f"\n⚠️ 警告 ({len(warnings)} 条):")
                for warning in warnings:
                    output_lines.append(f"   - {warning}")

            stdout_text = "\n".join(all_results)
            summary = "\n".join(output_lines) if output_lines else ""

            if overall_success:
                return {
                    "success": True,
                    "stdout": stdout_text + ("\n\n" + summary if summary else ""),
                    "stderr": "",
                }
            else:
                return {
                    "success": False,
                    "stdout": stdout_text + ("\n\n" + summary if summary else ""),
                    "stderr": summary if summary else "部分文件修改失败",
                }

        except Exception as e:
            error_msg = f"文件编辑失败: {str(e)}"
            print(f"❌ {error_msg}")
            return {"success": False, "stdout": "", "stderr": error_msg}


__all__ = ["EditFileFreeTool"]
