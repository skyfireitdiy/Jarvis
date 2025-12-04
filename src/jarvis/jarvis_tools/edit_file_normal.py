# -*- coding: utf-8 -*-
"""普通文件编辑工具（基于 search/replace 的非结构化编辑）"""

import os
from typing import Any, Dict, List, Optional, Tuple

from jarvis.jarvis_tools.edit_file_structed import EditFileTool


class EditFileNormalTool:
    """普通文件编辑工具，完全基于 search/replace 进行文件编辑"""

    name = "edit_file_normal"
    description = (
        "使用 search/replace 对文件进行普通文本编辑（不依赖块id），支持同时修改多个文件。\n\n"
        "💡 使用方式：\n"
        "1. 直接指定要编辑的文件路径\n"
        "2. 为每个文件提供一组 search/replace 操作\n"
        "3. 所有匹配将被替换为新文本（等价于 Python 的 str.replace，默认替换全部匹配）\n\n"
        "⚠️ 提示：\n"
        "- search 为普通字符串匹配，不支持正则表达式\n"
        "- search 不能为空字符串\n"
        "- 如果某个 search 在文件中完全找不到，将导致该文件的编辑失败，文件内容会回滚到原始状态"
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
                                        "description": "要搜索的原始文本（不支持正则表达式，不能为空）",
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
        """验证基本参数（与结构化编辑保持一致的 files 验证逻辑）"""
        return EditFileTool._validate_basic_args(args)

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
    def _apply_normal_edits_to_content(
        original_content: str, diffs: List[Dict[str, Any]]
    ) -> Tuple[bool, str]:
        """对文件内容按顺序应用普通 search/replace 编辑

        返回:
            (是否成功, 新内容或错误信息)
        """
        content = original_content

        for idx, diff in enumerate(diffs, start=1):
            search = diff["search"]
            replace = diff["replace"]
            count = diff.get("count", -1)

            match_count = content.count(search)
            if match_count == 0:
                # 任意一个 search 找不到就视为失败，避免静默不生效
                error_msg = (
                    f"第 {idx} 个diff失败：在文件内容中未找到要搜索的文本: {search[:100]}..."
                )
                return False, error_msg

            # 应用替换
            if count is None or count < 0:
                content = content.replace(search, replace)
            elif count == 0:
                # 0 次替换，相当于跳过
                continue
            else:
                content = content.replace(search, replace, count)

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
                original_content, backup_path = EditFileTool._read_file_with_backup(
                    file_path
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
                write_success, write_error = EditFileTool._write_file_with_rollback(
                    abs_path, result_or_error, backup_path
                )
                if write_success:
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


