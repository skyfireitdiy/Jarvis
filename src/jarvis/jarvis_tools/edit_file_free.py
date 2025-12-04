# -*- coding: utf-8 -*-
"""自由文件编辑工具（仅需新代码片段）"""

import difflib
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from jarvis.jarvis_tools.edit_file_structed import EditFileTool


class EditFileFreeTool:
    """自由文件编辑工具，仅需提供新代码片段，自动定位插入位置"""

    name = "edit_file_free"
    description = (
        "基于新代码片段自动定位并编辑文件的工具，支持同时修改多个文件。\n\n"
        "💡 使用方式：\n"
        "1. 提供要修改的文件路径\n"
        "2. 提供新代码片段（包含部分上下文，如前后3行）\n"
        "3. 工具会自动在文件中查找最匹配的位置并进行替换或插入\n\n"
        "📝 工作原理：\n"
        "- 工具会分析新代码片段，提取关键特征（函数名、类名、代码结构等）\n"
        "- 在文件中查找相似或相关的代码位置\n"
        "- 如果找到相似代码，进行替换；如果找不到，在文件末尾追加\n"
        "- 支持模糊匹配，即使代码有轻微差异也能找到匹配位置\n\n"
        "⚠️ 提示：\n"
        "- 建议在新代码中包含足够的上下文（前后各3行）以提高匹配准确性\n"
        "- 如果代码片段包含函数定义或类定义，工具会尝试找到对应的位置进行替换\n"
        "- 如果找不到匹配位置，代码会在文件末尾追加"
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
                                    "new_code": {
                                        "type": "string",
                                        "description": "新代码片段（建议包含前后3行上下文以提高匹配准确性）",
                                    },
                                    "action": {
                                        "type": "string",
                                        "enum": ["replace", "append"],
                                        "description": "操作类型：replace（替换匹配的代码）、append（在文件末尾追加），默认自动推断",
                                        "default": "auto",
                                    },
                                    "min_similarity": {
                                        "type": "number",
                                        "description": "最小相似度阈值（0-1），用于匹配判断，默认0.6",
                                        "default": 0.6,
                                    },
                                },
                                "required": ["new_code"],
                            },
                            "description": "编辑操作列表，每个操作包含新代码片段",
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
    def _validate_free_diff(
        diff: Dict[str, Any], idx: int
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """验证并转换 free 类型的 diff

        Returns:
            (错误响应或None, 规范化后的diff或None)
        """
        new_code = diff.get("new_code")
        action = diff.get("action", "auto")
        min_similarity = diff.get("min_similarity", 0.6)

        if new_code is None:
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx} 个diff缺少new_code参数",
                },
                None,
            )
        if not isinstance(new_code, str):
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx} 个diff的new_code参数必须是字符串",
                },
                None,
            )
        if new_code.strip() == "":
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx} 个diff的new_code参数不能为空",
                },
                None,
            )

        # 验证操作类型
        if action not in ["replace", "append", "auto"]:
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx} 个diff的action参数必须是 replace、append 或 auto",
                },
                None,
            )

        # 验证相似度阈值
        if not isinstance(min_similarity, (int, float)) or not (
            0 <= min_similarity <= 1
        ):
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx} 个diff的min_similarity参数必须是0-1之间的数字",
                },
                None,
            )

        return (
            None,
            {
                "new_code": new_code,
                "action": action,
                "min_similarity": min_similarity,
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
        content: str, new_code: str, min_similarity: float = 0.6
    ) -> Tuple[Optional[Tuple[int, int, float]], Optional[str]]:
        """在文件中查找最佳匹配位置

        Args:
            content: 文件内容
            new_code: 新代码片段
            min_similarity: 最小相似度阈值

        Returns:
            ((start_pos, end_pos, similarity), error_msg) 或 (None, error_msg)
        """
        content_lines = content.splitlines(keepends=True)
        new_code_lines = new_code.splitlines(keepends=True)

        if len(new_code_lines) == 0:
            return None, "new_code 不能为空"

        # 提取新代码的特征
        new_features = EditFileFreeTool._extract_code_features(new_code)

        # 策略1: 如果有函数名或类名，尝试精确匹配
        if new_features["function_names"] or new_features["class_names"]:
            # 查找函数或类定义
            for name in new_features["function_names"] + new_features["class_names"]:
                # 构建匹配模式
                if name in new_features["function_names"]:
                    pattern = rf"def\s+{re.escape(name)}\s*\("
                else:
                    pattern = rf"class\s+{re.escape(name)}"

                # 在文件中查找
                for match in re.finditer(pattern, content):
                    # 找到匹配位置，尝试匹配整个代码块
                    match_start = match.start()
                    match_line = content[:match_start].count("\n")

                    # 尝试匹配后续的代码（基于行数）
                    # 计算新代码的行数
                    new_code_line_count = len(
                        [line for line in new_code_lines if line.strip()]
                    )

                    # 尝试匹配从匹配行开始的代码
                    if match_line + new_code_line_count <= len(content_lines):
                        # 提取匹配区域的代码
                        matched_lines = content_lines[
                            match_line : match_line + new_code_line_count
                        ]
                        matched_code = "".join(matched_lines)

                        # 计算相似度
                        similarity = difflib.SequenceMatcher(
                            None, new_code.strip(), matched_code.strip(), autojunk=False
                        ).ratio()

                        if similarity >= min_similarity:
                            # 计算精确位置
                            start_pos = sum(
                                len(content_lines[i]) for i in range(match_line)
                            )
                            end_pos = start_pos + len(matched_code)
                            return (start_pos, end_pos, similarity), None

        # 策略2: 使用代码片段进行模糊匹配
        new_code_stripped = new_code.strip()
        if not new_code_stripped:
            return None, "new_code 不能只包含空白字符"

        # 提取核心代码（去除前后空白行）
        new_code_core_lines = []
        for line in new_code_lines:
            if line.strip():
                new_code_core_lines.append(line)
        if not new_code_core_lines:
            return None, "new_code 不能只包含空白行"

        new_code_core = "".join(new_code_core_lines)
        core_line_count = len(new_code_core_lines)

        best_match: Optional[Tuple[int, int, float]] = None
        best_similarity = 0.0

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
                    or len(window_content.strip()) < len(new_code_core.strip()) * 0.3
                ):
                    continue

                # 计算相似度
                similarity = difflib.SequenceMatcher(
                    None, new_code_core, window_content, autojunk=False
                ).ratio()

                if similarity > best_similarity:
                    best_similarity = similarity
                    # 计算字符位置
                    start_pos = sum(len(content_lines[i]) for i in range(start_line))
                    end_pos = start_pos + len(window_content)
                    best_match = (start_pos, end_pos, similarity)

                # 如果找到很好的匹配，提前退出
                if similarity >= 0.95:
                    break

            # 如果已经找到很好的匹配，可以提前退出
            if best_similarity >= 0.95:
                break

        # 只有当相似度足够高时才返回匹配
        if best_match is not None and best_similarity >= min_similarity:
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
        new_code = diff["new_code"]
        action = diff.get("action", "auto")
        min_similarity = diff.get("min_similarity", 0.6)

        # 如果明确指定为 append，直接追加
        if action == "append":
            # 确保文件末尾有换行符
            if content and not content.endswith("\n"):
                new_content = content + "\n" + new_code
            else:
                new_content = content + new_code
            return True, new_content, None

        # 尝试查找匹配位置
        match_result, error_msg = EditFileFreeTool._find_best_match_position(
            content, new_code, min_similarity
        )

        if match_result is None:
            # 如果找不到匹配且不是强制替换，则追加
            if action == "replace":
                return (
                    False,
                    error_msg or "未找到匹配的代码位置，无法执行替换操作",
                    None,
                )
            else:
                # 自动模式：找不到匹配则追加
                if content and not content.endswith("\n"):
                    new_content = content + "\n" + new_code
                else:
                    new_content = content + new_code
                return True, new_content, "未找到匹配位置，代码已追加到文件末尾"

        start_pos, end_pos, similarity = match_result

        # 检查相似度
        warning = None
        if similarity < 0.8:
            warning = (
                f"⚠️ 匹配相似度较低 ({similarity:.2%})，"
                f"请确认替换位置是否正确。匹配位置: 字符 {start_pos}-{end_pos}"
            )

        # 执行替换
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
