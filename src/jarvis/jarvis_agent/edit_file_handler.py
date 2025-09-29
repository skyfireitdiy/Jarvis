import os
import re
from typing import Any, Dict, List, Tuple

from jarvis.jarvis_agent.output_handler import OutputHandler
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.tag import ct, ot


class EditFileHandler(OutputHandler):
    def __init__(self):
        self.patch_pattern = re.compile(
            ot("PATCH file=(?:'([^']+)'|\"([^\"]+)\"|([^>]+))") + r"\s*"
            r"(?:"
            + ot("DIFF")
            + r"\s*(?:"
            # 可选的RANGE标签，限制替换行号范围
            + r"(?:" + ot("RANGE") + r"(.*?)" + ct("RANGE") + r"\s*)?"
            + r"(?:"
            # 单点替换（SEARCH/REPLACE）
            + ot("SEARCH")
            + r"(.*?)"
            + ct("SEARCH")
            + r"\s*"
            + ot("REPLACE")
            + r"(.*?)"
            + ct("REPLACE")
            + r"|"
            # 区间替换（SEARCH_START/SEARCH_END/REPLACE）
            + ot("SEARCH_START")
            + r"(.*?)"
            + ct("SEARCH_START")
            + r"\s*"
            + ot("SEARCH_END")
            + r"(.*?)"
            + ct("SEARCH_END")
            + r"\s*"
            + ot("REPLACE")
            + r"(.*?)"
            + ct("REPLACE")
            + r")"
            + r")\s*"
            + ct("DIFF")
            + r"\s*)+"
            + r"^" + ct("PATCH"),
            re.DOTALL | re.MULTILINE,
        )
        self.diff_pattern = re.compile(
            ot("DIFF")
            + r"\s*(?:" + ot("RANGE") + r"(.*?)" + ct("RANGE") + r"\s*)?"
            + ot("SEARCH")
            + r"(.*?)"
            + ct("SEARCH")
            + r"\s*"
            + ot("REPLACE")
            + r"(.*?)"
            + ct("REPLACE")
            + r"\s*"
            + ct("DIFF"),
            re.DOTALL,
        )
        self.diff_range_pattern = re.compile(
            ot("DIFF")
            + r"\s*(?:" + ot("RANGE") + r"(.*?)" + ct("RANGE") + r"\s*)?"
            + ot("SEARCH_START")
            + r"(.*?)"
            + ct("SEARCH_START")
            + r"\s*"
            + ot("SEARCH_END")
            + r"(.*?)"
            + ct("SEARCH_END")
            + r"\s*"
            + ot("REPLACE")
            + r"(.*?)"
            + ct("REPLACE")
            + r"\s*"
            + ct("DIFF"),
            re.DOTALL,
        )

    def handle(self, response: str, agent: Any) -> Tuple[bool, str]:
        """处理文件编辑响应

        Args:
            response: 包含文件编辑指令的响应字符串
            agent: 执行处理的agent实例

        Returns:
            Tuple[bool, str]: 返回处理结果元组，第一个元素表示是否处理成功，第二个元素为处理结果汇总字符串
        """
        patches = self._parse_patches(response)
        if not patches:
            return False, "未找到有效的文件编辑指令"

        # 记录 edit_file 工具调用统计
        from jarvis.jarvis_stats.stats import StatsManager

        StatsManager.increment("edit_file", group="tool")

        results = []

        for file_path, diffs in patches.items():
            file_path = os.path.abspath(file_path)
            file_patches = diffs

            success, result = self._fast_edit(file_path, file_patches)

            if success:
                results.append(f"✅ 文件 {file_path} 修改成功")
            else:
                results.append(f"❌ 文件 {file_path} 修改失败: {result}")

        summary = "\n".join(results)
        return False, summary

    def can_handle(self, response: str) -> bool:
        """判断是否能处理给定的响应

        Args:
            response: 需要判断的响应字符串

        Returns:
            bool: 返回是否能处理该响应
        """
        return bool(self.patch_pattern.search(response))

    def prompt(self) -> str:
        """获取处理器的提示信息

        Returns:
            str: 返回处理器的提示字符串
        """
        from jarvis.jarvis_utils.config import get_patch_format

        patch_format = get_patch_format()

        search_prompt = f"""{ot("DIFF")}
{ot("SEARCH")}原始代码{ct("SEARCH")}
{ot("REPLACE")}新代码{ct("REPLACE")}
{ct("DIFF")}"""

        search_range_prompt = f"""{ot("DIFF")}
{ot("RANGE")}起止行号(如: 10-50)，可选{ct("RANGE")}
{ot("SEARCH_START")}起始标记{ct("SEARCH_START")}
{ot("SEARCH_END")}结束标记{ct("SEARCH_END")}
{ot("REPLACE")}替换内容{ct("REPLACE")}
{ct("DIFF")}"""

        if patch_format == "search":
            formats = search_prompt
            supported_formats = "仅支持单点替换（SEARCH/REPLACE）"
        elif patch_format == "search_range":
            formats = search_range_prompt
            supported_formats = "仅支持区间替换（SEARCH_START/SEARCH_END/REPLACE），可选RANGE限定行号范围"
        else:  # all
            formats = f"{search_prompt}\n或\n{search_range_prompt}"
            supported_formats = "支持两种DIFF块：单点替换（SEARCH/REPLACE）与区间替换（SEARCH_START/SEARCH_END/REPLACE）"

        return f"""文件编辑指令格式：
{ot("PATCH file=文件路径")}
{formats}
{ct("PATCH")}

注意：
- {ot("PATCH")} 和 {ct("PATCH")} 必须出现在行首，否则不生效（会被忽略）
- {supported_formats}
- {ot("RANGE")}start-end{ct("RANGE")} 仅用于区间替换模式（SEARCH_START/SEARCH_END），表示只在指定行号范围内进行匹配与替换（1-based，闭区间）；省略则在整个文件范围内处理
- 单点替换要求 SEARCH 在有效范围内唯一匹配（仅替换第一个匹配）
- 区间替换会从包含 {ot("SEARCH_START")} 的行首开始，到包含 {ot("SEARCH_END")} 的行尾结束，替换整个区域
否则编辑将失败。"""

    def name(self) -> str:
        """获取处理器的名称

        Returns:
            str: 返回处理器的名称字符串
        """
        return "PATCH"

    def _parse_patches(self, response: str) -> Dict[str, List[Dict[str, str]]]:
        """解析响应中的补丁信息

        该方法使用正则表达式从响应文本中提取文件编辑指令(PATCH块)，
        每个PATCH块可以包含多个DIFF块，每个DIFF块包含一组搜索和替换内容。
        解析后会返回一个字典，键是文件路径，值是该文件对应的补丁列表。
        如果同一个文件路径出现多次，会将所有DIFF块合并到一起。

        Args:
            response: 包含补丁信息的响应字符串，格式应符合PATCH指令规范

        Returns:
            Dict[str, List[Dict[str, str]]]:
                返回解析后的补丁信息字典，结构为:
                {
                    "文件路径1": [
                        {"SEARCH": "搜索文本1", "REPLACE": "替换文本1"},
                        {"SEARCH": "搜索文本2", "REPLACE": "替换文本2"}
                    ],
                    "文件路径2": [...]
                }
        """
        patches: Dict[str, List[Dict[str, str]]] = {}

        for match in self.patch_pattern.finditer(response):
            # Get the file path from the appropriate capture group
            file_path = match.group(1) or match.group(2) or match.group(3)
            diffs: List[Dict[str, str]] = []

            # 逐块解析，保持 DIFF 顺序
            diff_block_pattern = re.compile(ot("DIFF") + r"(.*?)" + ct("DIFF"), re.DOTALL)
            for block_match in diff_block_pattern.finditer(match.group(0)):
                block_text = block_match.group(1)

                # 提取可选的行号范围
                range_scope = None
                range_scope_match = re.match(
                    r"^\s*" + ot("RANGE") + r"(.*?)" + ct("RANGE") + r"\s*",
                    block_text,
                    re.DOTALL,
                )
                if range_scope_match:
                    range_scope = range_scope_match.group(1).strip()
                    # 仅移除块首部的RANGE标签，避免误删内容中的同名标记
                    block_text = block_text[range_scope_match.end():]
                # 统一按 all 解析：无视配置，始终尝试区间替换
                range_match = re.search(
                    ot("SEARCH_START")
                    + r"(.*?)"
                    + ct("SEARCH_START")
                    + r"\s*"
                    + ot("SEARCH_END")
                    + r"(.*?)"
                    + ct("SEARCH_END")
                    + r"\s*"
                    + ot("REPLACE")
                    + r"(.*?)"
                    + ct("REPLACE"),
                    block_text,
                    re.DOTALL,
                )
                if range_match:
                    diff_item: Dict[str, str] = {
                        "SEARCH_START": range_match.group(1),  # 原始SEARCH_START内容
                        "SEARCH_END": range_match.group(2),  # 原始SEARCH_END内容
                        "REPLACE": range_match.group(3),  # 原始REPLACE内容
                    }
                    if range_scope:
                        diff_item["RANGE"] = range_scope
                    diffs.append(diff_item)
                    continue

                # 解析单点替换（统一按 all 解析：无视配置，始终尝试单点替换）
                single_match = re.search(
                    ot("SEARCH")
                    + r"(.*?)"
                    + ct("SEARCH")
                    + r"\s*"
                    + ot("REPLACE")
                    + r"(.*?)"
                    + ct("REPLACE"),
                    block_text,
                    re.DOTALL,
                )
                if single_match:
                    diff_item = {
                        "SEARCH": single_match.group(1),  # 原始SEARCH内容
                        "REPLACE": single_match.group(2),  # 原始REPLACE内容
                    }
                    # SEARCH 模式不支持 RANGE，直接忽略
                    diffs.append(diff_item)

            if diffs:
                if file_path in patches:
                    patches[file_path].extend(diffs)
                else:
                    patches[file_path] = diffs
        return patches

    @staticmethod
    def _fast_edit(file_path: str, patches: List[Dict[str, str]]) -> Tuple[bool, str]:
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
            range_items: List[Tuple[int, int, int, Dict[str, str]]] = []
            non_range_items: List[Tuple[int, Dict[str, str]]] = []
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
                        error_msg = "SEARCH 在指定范围内出现多次，要求唯一匹配"
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
