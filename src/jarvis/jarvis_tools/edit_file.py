# -*- coding: utf-8 -*-
import json5 as json
import os
import re
from typing import Any, Dict, List

from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.tag import ct, ot
from jarvis.jarvis_utils.config import get_patch_format


class EditFileTool:
    """文件编辑工具，用于对文件进行局部修改"""

    name = "edit_file"
    description = """对文件进行局部修改。

支持两种修改模式：
1. 单点替换（SEARCH/REPLACE）：精确匹配并替换代码片段
2. 区间替换（SEARCH_START/SEARCH_END/REPLACE）：替换两个标记之间的内容

可选的行号范围限制（RANGE）：
- 可以指定行号范围来限制搜索和替换的范围
- 格式：start-end（1-based，闭区间）
- 省略则在整个文件范围内处理

单点替换要求 SEARCH 在有效范围内唯一匹配（仅替换第一个匹配）。
区间替换会从包含 SEARCH_START 的行首开始，到包含 SEARCH_END 的行尾结束，替换整个区域。
"""

    parameters = {
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
                    "oneOf": [
                        {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["search"],
                                    "description": "单点替换模式",
                                },
                                "range": {
                                    "type": "string",
                                    "description": "可选的行号范围，格式：start-end（1-based，闭区间）",
                                },
                                "search": {
                                    "type": "string",
                                    "description": "要搜索的原始代码",
                                },
                                "replace": {
                                    "type": "string",
                                    "description": "替换后的新代码",
                                },
                            },
                            "required": ["type", "search", "replace"],
                        },
                        {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["search_range"],
                                    "description": "区间替换模式",
                                },
                                "range": {
                                    "type": "string",
                                    "description": "可选的行号范围，格式：start-end（1-based，闭区间）",
                                },
                                "search_start": {
                                    "type": "string",
                                    "description": "起始标记",
                                },
                                "search_end": {
                                    "type": "string",
                                    "description": "结束标记",
                                },
                                "replace": {
                                    "type": "string",
                                    "description": "替换内容",
                                },
                            },
                            "required": ["type", "search_start", "search_end", "replace"],
                        },
                    ],
                },
                "description": "修改操作列表，每个操作包含一个DIFF块",
            },
        },
        "required": ["file_path", "diffs"],
    }

    def __init__(self):
        """初始化文件编辑工具"""
        pass

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行文件编辑操作"""
        try:
            file_path = args.get("file_path")
            diffs = args.get("diffs", [])

            if not file_path:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "缺少必需参数：file_path",
                }

            if not diffs:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "缺少必需参数：diffs",
                }

            # 转换为内部格式
            patches = []
            for diff in diffs:
                diff_type = diff.get("type")
                if diff_type == "search":
                    patch = {
                        "SEARCH": diff.get("search", ""),
                        "REPLACE": diff.get("replace", ""),
                    }
                    if "range" in diff:
                        patch["RANGE"] = diff["range"]
                    patches.append(patch)
                elif diff_type == "search_range":
                    patch = {
                        "SEARCH_START": diff.get("search_start", ""),
                        "SEARCH_END": diff.get("search_end", ""),
                        "REPLACE": diff.get("replace", ""),
                    }
                    if "range" in diff:
                        patch["RANGE"] = diff["range"]
                    patches.append(patch)
                else:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"不支持的diff类型: {diff_type}",
                    }

            # 记录 PATCH 操作调用统计
            try:
                from jarvis.jarvis_stats.stats import StatsManager

                StatsManager.increment("patch", group="tool")
            except Exception:
                pass

            # 执行编辑
            success, result = self._fast_edit(file_path, patches)

            if success:
                return {
                    "success": True,
                    "stdout": f"文件 {file_path} 修改成功",
                    "stderr": "",
                }
            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": result,
                }

        except Exception as e:
            error_msg = f"文件编辑失败: {str(e)}"
            PrettyOutput.print(error_msg, OutputType.ERROR)
            return {"success": False, "stdout": "", "stderr": error_msg}

    @staticmethod
    def _fast_edit(file_path: str, patches: List[Dict[str, str]]) -> tuple[bool, str]:
        """快速应用补丁到文件

        该方法直接尝试将补丁应用到目标文件，适用于简单、明确的修改场景。
        特点：
        1. 直接进行字符串替换，效率高
        2. 会自动处理缩进问题，尝试匹配不同缩进级别的代码
        3. 确保搜索文本在文件中唯一匹配
        4. 如果部分补丁失败，会继续应用剩余补丁，并报告失败信息

        Args:
            file_path: 要修改的文件路径，支持绝对路径和相对路径
            patches: 补丁列表，每个补丁包含search(搜索文本)和replace(替换文本)

        Returns:
            Tuple[bool, str]:
                返回处理结果元组，第一个元素表示是否所有补丁都成功应用，
                第二个元素为结果信息，全部成功时为修改后的文件内容，部分或全部失败时为错误信息
        """
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            # 读取原始文件内容
            file_content = ""
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    file_content = f.read()

            # 应用所有补丁
            modified_content = file_content
            patch_count = 0
            failed_patches: List[Dict[str, Any]] = []
            successful_patches = 0

            # 当存在RANGE时，确保按行号从后往前应用补丁，避免前面补丁影响后续RANGE的行号
            ordered_patches: List[Dict[str, str]] = []
            range_items: List[tuple[int, int, int, Dict[str, str]]] = []
            non_range_items: List[tuple[int, Dict[str, str]]] = []
            for idx, p in enumerate(patches):
                r = p.get("RANGE")
                if r and str(r).strip():
                    m = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*$", str(r))
                    if m:
                        start_line = int(m.group(1))
                        end_line = int(m.group(2))
                        range_items.append((start_line, end_line, idx, p))
                    else:
                        # RANGE格式无效的补丁保持原有顺序
                        non_range_items.append((idx, p))
                else:
                    # 无RANGE的补丁保持原有顺序
                    non_range_items.append((idx, p))
            # 先应用RANGE补丁：按start_line、end_line、原始索引逆序
            range_items.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
            ordered_patches = [item[3] for item in range_items] + [item[1] for item in non_range_items]

            patch_count = len(ordered_patches)
            for patch in ordered_patches:
                found = False

                # 处理可选的RANGE范围：格式 "start-end"（1-based, 闭区间）
                scoped = False
                prefix = suffix = ""
                base_content = modified_content
                if "RANGE" in patch and str(patch["RANGE"]).strip():
                    m = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*$", str(patch["RANGE"]))
                    if not m:
                        error_msg = "RANGE格式无效，应为 'start-end' 的行号范围（1-based, 闭区间）"
                        failed_patches.append({"patch": patch, "error": error_msg})
                        # 不进行本补丁其它处理
                        continue
                    start_line = int(m.group(1))
                    end_line = int(m.group(2))

                    # 拆分为三段
                    lines = modified_content.splitlines(keepends=True)
                    total_lines = len(lines)
                    if (
                        start_line < 1
                        or end_line < 1
                        or start_line > end_line
                        or start_line > total_lines
                    ):
                        error_msg = f"RANGE行号无效（文件共有{total_lines}行）"
                        failed_patches.append({"patch": patch, "error": error_msg})
                        continue
                    # 截断end_line不超过总行数
                    end_line = min(end_line, total_lines)

                    prefix = "".join(lines[: start_line - 1])
                    base_content = "".join(lines[start_line - 1 : end_line])
                    suffix = "".join(lines[end_line:])
                    scoped = True

                # 单点替换
                if "SEARCH" in patch:
                    search_text = patch["SEARCH"]
                    replace_text = patch["REPLACE"]

                    # 精确匹配搜索文本（保留原始换行和空格）
                    exact_search = search_text

                    def _count_occurrences(haystack: str, needle: str) -> int:
                        if not needle:
                            return 0
                        return haystack.count(needle)

                    # 1) 精确匹配，要求唯一
                    cnt = _count_occurrences(base_content, exact_search)
                    if cnt == 1:
                        base_content = base_content.replace(exact_search, replace_text, 1)
                        found = True
                    elif cnt > 1:
                        # 提供更详细的错误信息，帮助调试
                        range_info = f"（RANGE: {patch.get('RANGE', '无')}）" if "RANGE" in patch else ""
                        base_preview = base_content[:200] + "..." if len(base_content) > 200 else base_content
                        error_msg = (
                            f"SEARCH 在指定范围内出现多次，要求唯一匹配{range_info}。"
                            f"匹配次数: {cnt}。"
                            f"搜索内容: {repr(exact_search[:50])}。"
                            f"范围内容预览: {repr(base_preview)}"
                        )
                        failed_patches.append({"patch": patch, "error": error_msg})
                        # 不继续尝试其它变体
                        continue
                    else:
                        # 2) 若首尾均为换行，尝试去掉首尾换行后匹配，要求唯一
                        if (
                            search_text.startswith("\n")
                            and search_text.endswith("\n")
                            and replace_text.startswith("\n")
                            and replace_text.endswith("\n")
                        ):
                            stripped_search = search_text[1:-1]
                            stripped_replace = replace_text[1:-1]
                            cnt2 = _count_occurrences(base_content, stripped_search)
                            if cnt2 == 1:
                                base_content = base_content.replace(
                                    stripped_search, stripped_replace, 1
                                )
                                found = True
                            elif cnt2 > 1:
                                error_msg = "SEARCH 在指定范围内出现多次（去掉首尾换行后），要求唯一匹配"
                                failed_patches.append({"patch": patch, "error": error_msg})
                                continue

                        # 3) 尝试缩进适配（1..16个空格），要求唯一
                        if not found:
                            current_search = search_text
                            current_replace = replace_text
                            if (
                                current_search.startswith("\n")
                                and current_search.endswith("\n")
                                and current_replace.startswith("\n")
                                and current_replace.endswith("\n")
                            ):
                                current_search = current_search[1:-1]
                                current_replace = current_replace[1:-1]

                            for space_count in range(1, 17):
                                indented_search = "\n".join(
                                    " " * space_count + line if line.strip() else line
                                    for line in current_search.split("\n")
                                )
                                indented_replace = "\n".join(
                                    " " * space_count + line if line.strip() else line
                                    for line in current_replace.split("\n")
                                )
                                cnt3 = _count_occurrences(base_content, indented_search)
                                if cnt3 == 1:
                                    base_content = base_content.replace(
                                        indented_search, indented_replace, 1
                                    )
                                    found = True
                                    break
                                elif cnt3 > 1:
                                    error_msg = "SEARCH 在指定范围内出现多次（缩进适配后），要求唯一匹配"
                                    failed_patches.append({"patch": patch, "error": error_msg})
                                    # 多匹配直接失败，不再继续尝试其它缩进
                                    found = False
                                    break

                        if not found:
                            # 未找到任何可用的唯一匹配
                            failed_patches.append({"patch": patch, "error": "未找到唯一匹配的SEARCH"})

                # 区间替换
                elif "SEARCH_START" in patch and "SEARCH_END" in patch:
                    search_start = patch["SEARCH_START"]
                    search_end = patch["SEARCH_END"]
                    replace_text = patch["REPLACE"]

                    # 范围替换（包含边界），命中第一个起始标记及其后的第一个结束标记
                    start_idx = base_content.find(search_start)
                    if start_idx == -1:
                        error_msg = "未找到SEARCH_START"
                        failed_patches.append({"patch": patch, "error": error_msg})
                    else:
                        # 从 search_start 之后开始查找 search_end
                        end_idx = base_content.find(search_end, start_idx + len(search_start))
                        if end_idx == -1:
                            error_msg = "在SEARCH_START之后未找到SEARCH_END"
                            failed_patches.append({"patch": patch, "error": error_msg})
                        else:
                            # 将替换范围扩展到整行
                            # 找到 start_idx 所在行的行首
                            line_start_idx = base_content.rfind("\n", 0, start_idx) + 1

                            # 找到 end_idx 所在行的行尾
                            match_end_pos = end_idx + len(search_end)
                            line_end_idx = base_content.find("\n", match_end_pos)

                            if line_end_idx == -1:
                                # 如果没有找到换行符，说明是最后一行
                                end_of_range = len(base_content)
                            else:
                                # 包含换行符
                                end_of_range = line_end_idx + 1

                            final_replace_text = replace_text
                            original_slice = base_content[line_start_idx:end_of_range]

                            # 如果原始片段以换行符结尾，且替换内容不为空且不以换行符结尾，
                            # 则为替换内容添加换行符以保持格式
                            if (
                                final_replace_text
                                and original_slice.endswith("\n")
                                and not final_replace_text.endswith("\n")
                            ):
                                final_replace_text += "\n"

                            base_content = (
                                base_content[:line_start_idx]
                                + final_replace_text
                                + base_content[end_of_range:]
                            )
                            found = True

                else:
                    error_msg = "不支持的补丁格式"
                    failed_patches.append({"patch": patch, "error": error_msg})

                # 若使用了RANGE，则将局部修改写回整体内容
                if found:
                    if scoped:
                        modified_content = prefix + base_content + suffix
                    else:
                        modified_content = base_content
                    successful_patches += 1

            # 写入修改后的内容
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(modified_content)

            if failed_patches:
                error_details = []
                for p in failed_patches:
                    patch = p["patch"]
                    if "SEARCH" in patch:
                        patch_desc = patch["SEARCH"]
                    else:
                        patch_desc = (
                            "SEARCH_START:\n"
                            + (patch.get("SEARCH_START", ""))
                            + "\nSEARCH_END:\n"
                            + (patch.get("SEARCH_END", ""))
                        )
                    error_details.append(f"  - 失败的补丁: \n{patch_desc}\n    错误: {p['error']}")
                if successful_patches == 0:
                    summary = (
                        f"文件 {file_path} 修改失败（全部失败）。\n"
                        f"失败: {len(failed_patches)}/{patch_count}.\n"
                        f"失败详情:\n" + "\n".join(error_details)
                    )
                else:
                    summary = (
                        f"文件 {file_path} 修改部分成功。\n"
                        f"成功: {successful_patches}/{patch_count}, "
                        f"失败: {len(failed_patches)}/{patch_count}.\n"
                        f"失败详情:\n" + "\n".join(error_details)
                    )
                PrettyOutput.print(summary, OutputType.ERROR)
                return False, summary

            return True, modified_content

        except Exception as e:
            PrettyOutput.print(f"文件修改失败: {str(e)}", OutputType.ERROR)
            return False, f"文件修改失败: {str(e)}"

