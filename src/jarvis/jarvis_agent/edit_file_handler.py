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
            + r"\s*"
            + ot("SEARCH")
            + r"(.*?)"
            + ct("SEARCH")
            + r"\s*"
            + ot("REPLACE")
            + r"(.*?)"
            + ct("REPLACE")
            + r"\s*"
            + ct("DIFF")
            + r"\s*)+"
            + ct("PATCH"),
            re.DOTALL,
        )
        self.diff_pattern = re.compile(
            ot("DIFF")
            + r"\s*"
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
            file_patches = [
                {"SEARCH": diff["SEARCH"], "REPLACE": diff["REPLACE"]} for diff in diffs
            ]

            print(f"📝 正在处理文件 {file_path}...")
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
        return f"""文件编辑指令格式：
{ot("PATCH file=文件路径")}
{ot("DIFF")}
{ot("SEARCH")}原始代码{ct("SEARCH")}
{ot("REPLACE")}新代码{ct("REPLACE")}
{ct("DIFF")}
{ct("PATCH")}

可以返回多个PATCH块用于同时修改多个文件
每个PATCH块可以包含多个DIFF块，每个DIFF块包含一组搜索和替换内容。
搜索文本必须能在文件中唯一匹配，否则编辑将失败。"""

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
            diffs = []
            for diff_match in self.diff_pattern.finditer(match.group(0)):
                # 完全保留原始格式（包括所有空白和换行）
                diffs.append(
                    {
                        "SEARCH": diff_match.group(1),  # 原始SEARCH内容
                        "REPLACE": diff_match.group(2),  # 原始REPLACE内容
                    }
                )
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

            for patch in patches:
                patch_count += 1
                search_text = patch["SEARCH"]
                replace_text = patch["REPLACE"]

                # 精确匹配搜索文本（保留原始换行和空格）
                exact_search = search_text
                found = False

                if exact_search in modified_content:
                    # 直接执行替换（保留所有原始格式）
                    modified_content = modified_content.replace(
                        exact_search, replace_text
                    )
                    print(f"✅ 补丁 #{patch_count} 应用成功")
                    found = True
                else:
                    # 如果匹配不到，并且search与replace块的首尾都是换行，尝试去掉第一个和最后一个换行
                    if (
                        search_text.startswith("\n")
                        and search_text.endswith("\n")
                        and replace_text.startswith("\n")
                        and replace_text.endswith("\n")
                    ):
                        stripped_search = search_text[1:-1]
                        stripped_replace = replace_text[1:-1]
                        if stripped_search in modified_content:
                            modified_content = modified_content.replace(
                                stripped_search, stripped_replace
                            )
                            print(f"✅ 补丁 #{patch_count} 应用成功 (自动去除首尾换行)")
                            found = True

                    if not found:
                        # 尝试增加缩进重试
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
                            if indented_search in modified_content:
                                modified_content = modified_content.replace(
                                    indented_search, indented_replace
                                )
                                print(
                                    f"✅ 补丁 #{patch_count} 应用成功 (自动增加 {space_count} 个空格缩进)"
                                )
                                found = True
                                break

                if found:
                    successful_patches += 1
                else:
                    error_msg = "搜索文本在文件中不存在"
                    PrettyOutput.print(
                        f"{error_msg}：\n{search_text}",
                        output_type=OutputType.WARNING,
                    )
                    failed_patches.append({"patch": patch, "error": error_msg})

            # 写入修改后的内容
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(modified_content)

            if failed_patches:
                error_details = [
                    f"  - 失败的补丁: \n{p['patch']['SEARCH']}\n    错误: {p['error']}"
                    for p in failed_patches
                ]
                summary = (
                    f"文件 {file_path} 修改部分成功。\n"
                    f"成功: {successful_patches}/{patch_count}, "
                    f"失败: {len(failed_patches)}/{patch_count}.\n"
                    f"失败详情:\n" + "\n".join(error_details)
                )
                print(f"❌ {summary}")
                return False, summary

            print(f"✅ 文件 {file_path} 修改完成，应用了 {patch_count} 个补丁")
            return True, modified_content

        except Exception as e:
            print(f"❌ 文件修改失败: {str(e)}")
            return False, f"文件修改失败: {str(e)}"
