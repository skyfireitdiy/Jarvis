# -*- coding: utf-8 -*-
"""普通文件编辑工具（基于 search/replace 的非结构化编辑）"""

import os
import shutil
from typing import Any, Dict, List, Optional, Tuple


class EditFileNormalTool:
    """普通文件编辑工具，完全基于 search/replace 进行文件编辑"""

    name = "edit_file"
    description = (
        "使用 search/replace 对文件进行普通文本编辑（不依赖块id），支持同时修改多个文件。\n\n"
        "💡 使用方式：\n"
        "1. 直接指定要编辑的文件路径\n"
        "2. 为每个文件提供一组 search/replace 操作\n"
        "3. 使用精确匹配查找 search 文本，找到匹配后替换为新文本\n\n"
        "⚠️ 提示：\n"
        "- search 使用精确字符串匹配，不支持正则表达式\n"
        "- search 不能为空字符串\n"
        "- **重要：search 必须提供足够的上下文来唯一定位目标位置**，避免匹配到错误的位置。建议包含：\n"
        "  * 目标代码的前后几行上下文（至少包含目标代码所在函数的签名或关键标识）\n"
        "  * 目标代码附近的唯一标识符（如函数名、变量名、注释等）\n"
        "  * 避免使用过短的 search 文本（如单个单词、短字符串），除非能确保唯一性\n"
        "- 如果某个 search 在文件中找不到精确匹配，将导致该文件的编辑失败，文件内容会回滚到原始状态\n"
        "- 如果存在多个匹配，可以通过 count 参数控制替换次数（-1 表示替换全部，1 表示只替换第一次）\n"
        "- 建议在 search 中包含足够的上下文，确保能唯一匹配到目标位置，避免误匹配"
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
                                        "description": "要搜索的原始文本（不支持正则表达式，不能为空）。**重要：必须提供足够的上下文来唯一定位目标位置**，建议包含目标代码的前后几行上下文、函数签名或唯一标识符，避免匹配到错误的位置。",
                                    },
                                    "replace": {
                                        "type": "string",
                                        "description": "替换后的文本（可以为空字符串）",
                                    },
                                    "count": {
                                        "type": "integer",
                                        "description": "替换次数，-1 或缺省表示替换全部匹配，1 表示只替换第一次匹配",
                                        "default": -1,
                                    },
                                },
                                "required": ["search", "replace"],
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

    def __init__(self):
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
    def _read_file_with_backup(file_path: str) -> Tuple[str, Optional[str]]:
        """读取文件并创建备份

        Args:
            file_path: 文件路径

        Returns:
            (文件内容, 备份文件路径或None)
        """
        abs_path = os.path.abspath(file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        file_content = ""
        backup_path = None
        if os.path.exists(abs_path):
            with open(abs_path, "r", encoding="utf-8") as f:
                file_content = f.read()
            # 创建备份文件
            backup_path = abs_path + ".bak"
            try:
                shutil.copy2(abs_path, backup_path)
            except Exception:
                # 备份失败不影响主流程
                backup_path = None

        return file_content, backup_path

    @staticmethod
    def _write_file_with_rollback(
        abs_path: str, content: str, backup_path: Optional[str]
    ) -> Tuple[bool, Optional[str]]:
        """写入文件，失败时回滚

        Args:
            abs_path: 文件绝对路径
            content: 要写入的内容
            backup_path: 备份文件路径或None

        Returns:
            (是否成功, 错误信息或None)
        """
        try:
            with open(abs_path, "w", encoding="utf-8") as f:
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
            print(f"❌ {error_msg}")
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
        count = diff.get("count", -1)

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
        if search == "":
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx} 个diff的search参数不能为空字符串",
                },
                None,
            )

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

        if count is None:
            count = -1
        if not isinstance(count, int):
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx} 个diff的count参数必须是整数",
                },
                None,
            )

        return (
            None,
            {
                "search": search,
                "replace": replace,
                "count": count,
            },
        )

    @staticmethod
    def _find_best_match_position(
        content: str, search_text: str
    ) -> Tuple[Optional[Tuple[int, int]], Optional[str]]:
        """在文件中查找精确匹配位置

        Args:
            content: 文件内容
            search_text: 要搜索的文本

        Returns:
            ((start_pos, end_pos), error_msg) 或 (None, error_msg)
        """
        if not search_text.strip():
            return None, "search 文本不能为空或只包含空白字符"

        # 使用精确字符串匹配
        start_pos = content.find(search_text)
        if start_pos == -1:
            return None, "未找到精确匹配的文本"

        end_pos = start_pos + len(search_text)
        return (start_pos, end_pos), None

    @staticmethod
    def _apply_normal_edits_to_content(
        original_content: str, diffs: List[Dict[str, Any]]
    ) -> Tuple[bool, str]:
        """对文件内容按顺序应用普通 search/replace 编辑（使用精确匹配）

        返回:
            (是否成功, 新内容或错误信息)
        """
        content = original_content

        for idx, diff in enumerate(diffs, start=1):
            search = diff["search"]
            replace = diff["replace"]
            count = diff.get("count", -1)

            # 使用精确匹配查找位置
            match_result, error_msg = EditFileNormalTool._find_best_match_position(
                content, search
            )

            if match_result is None:
                # 找不到匹配则失败
                error_info = f"第 {idx} 个diff失败：{error_msg}"
                if search:
                    error_info += f"\n搜索文本: {search[:200]}..."
                    error_info += (
                        "\n💡 提示：如果搜索文本在文件中存在但未找到匹配，可能是因为："
                    )
                    error_info += (
                        "\n   1. 搜索文本不够唯一，存在多个匹配（建议增加上下文）"
                    )
                    error_info += "\n   2. 搜索文本包含不可见字符或格式不匹配（建议检查空格、换行等）"
                    error_info += (
                        "\n   3. 搜索文本需要包含足够的上下文来唯一定位目标位置"
                    )
                return False, error_info

            start_pos, end_pos = match_result

            # 执行替换
            new_content = content[:start_pos] + replace + content[end_pos:]

            # 处理 count 参数
            if count is None or count < 0:
                # 替换全部匹配
                content = new_content
                # 继续查找并替换剩余的所有匹配
                search_start_pos = start_pos + len(replace)
                while True:
                    remaining_content = content[search_start_pos:]
                    next_match, _ = EditFileNormalTool._find_best_match_position(
                        remaining_content, search
                    )
                    if next_match is None:
                        break
                    next_start, next_end = next_match
                    # 调整位置（相对于原始 content）
                    actual_start = search_start_pos + next_start
                    actual_end = search_start_pos + next_end
                    content = content[:actual_start] + replace + content[actual_end:]
                    # 更新搜索起始位置（跳过已替换的内容）
                    search_start_pos = actual_start + len(replace)
            elif count == 0:
                # 0 次替换，相当于跳过
                continue
            elif count == 1:
                # 只替换第一次匹配
                content = new_content
            else:
                # 替换指定次数
                content = new_content
                remaining_count = count - 1
                search_start_pos = start_pos + len(replace)
                while remaining_count > 0:
                    remaining_content = content[search_start_pos:]
                    next_match, _ = EditFileNormalTool._find_best_match_position(
                        remaining_content, search
                    )
                    if next_match is None:
                        break
                    next_start, next_end = next_match
                    # 调整位置（相对于原始 content）
                    actual_start = search_start_pos + next_start
                    actual_end = search_start_pos + next_end
                    content = content[:actual_start] + replace + content[actual_end:]
                    # 更新搜索起始位置（跳过已替换的内容）
                    search_start_pos = actual_start + len(replace)
                    remaining_count -= 1

        return True, content

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行普通 search/replace 文件编辑操作（支持同时修改多个文件）"""
        try:
            # 验证基本参数（files 结构）
            error_response = EditFileNormalTool._validate_basic_args(args)
            if error_response:
                return error_response

            files = args.get("files", [])

            # 记录 PATCH 操作调用统计
            try:
                from jarvis.jarvis_stats.stats import StatsManager

                StatsManager.increment("patch_normal", group="tool")
            except Exception:
                pass

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

                    normalized_diffs.append(normalized)

                if not normalized_diffs:
                    # 该文件的diffs有问题，已记录错误，跳过
                    continue

                # 读取原始内容并创建备份
                original_content, backup_path = (
                    EditFileNormalTool._read_file_with_backup(file_path)
                )

                # 应用所有普通编辑
                success, result_or_error = (
                    EditFileNormalTool._apply_normal_edits_to_content(
                        original_content, normalized_diffs
                    )
                )

                if not success:
                    # 不写入文件，删除备份文件
                    if backup_path and os.path.exists(backup_path):
                        try:
                            os.remove(backup_path)
                        except Exception:
                            pass
                    all_results.append(f"❌ {file_path}: {result_or_error}")
                    failed_files.append(file_path)
                    overall_success = False
                    continue

                # 写入文件（失败时回滚）
                abs_path = os.path.abspath(file_path)
                write_success, write_error = (
                    EditFileNormalTool._write_file_with_rollback(
                        abs_path, result_or_error, backup_path
                    )
                )
                if write_success:
                    # 写入成功，删除备份文件
                    if backup_path and os.path.exists(backup_path):
                        try:
                            os.remove(backup_path)
                        except Exception:
                            pass
                    all_results.append(f"✅ {file_path}: 修改成功")
                    successful_files.append(file_path)
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


__all__ = ["EditFileNormalTool"]
