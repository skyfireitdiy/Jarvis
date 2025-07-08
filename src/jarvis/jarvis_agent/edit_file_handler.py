import os
import re
from typing import Any, Dict, List, Tuple

from jarvis.jarvis_agent.output_handler import OutputHandler
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.git_utils import revert_file
from jarvis.jarvis_utils.globals import get_interrupt, set_interrupt
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.tag import ct, ot
from jarvis.jarvis_utils.utils import is_context_overflow


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

        results = []

        for file_path, diffs in patches.items():
            file_path = os.path.abspath(file_path)
            file_patches = [
                {"SEARCH": diff["SEARCH"], "REPLACE": diff["REPLACE"]} for diff in diffs
            ]

            print(f"📝 正在处理文件 {file_path}...")
            # 首先尝试fast_edit模式
            success, result = self._fast_edit(file_path, file_patches)
            if not success:
                # 如果fast_edit失败，尝试slow_edit模式
                success, result = EditFileHandler._slow_edit(
                    file_path, file_patches, agent
                )

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
        4. 如果失败会自动回滚修改

        Args:
            file_path: 要修改的文件路径，支持绝对路径和相对路径
            patches: 补丁列表，每个补丁包含search(搜索文本)和replace(替换文本)

        Returns:
            Tuple[bool, str]:
                返回处理结果元组，第一个元素表示是否成功(True/False)，
                第二个元素为结果信息，成功时为修改后的文件内容，失败时为错误信息
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
            for patch in patches:
                search_text = patch["SEARCH"]
                replace_text = patch["REPLACE"]
                patch_count += 1

                # 精确匹配搜索文本（保留原始换行和空格）
                exact_search = search_text

                if exact_search in modified_content:
                    # 直接执行替换（保留所有原始格式）
                    modified_content = modified_content.replace(
                        exact_search, replace_text
                    )
                    print(f"✅ 补丁 #{patch_count} 应用成功")
                else:
                    found = False
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

                    if not found:
                        PrettyOutput.print(
                            f"搜索文本在文件中不存在：\n{search_text}",
                            output_type=OutputType.WARNING,
                        )
                        return False, f"搜索文本在文件中不存在：\n{search_text}"

            # 写入修改后的内容
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(modified_content)

            print(f"✅ 文件 {file_path} 修改完成，应用了 {patch_count} 个补丁")
            return True, modified_content

        except Exception as e:
            print(f"❌ 文件修改失败: {str(e)}")
            revert_file(file_path)
            return False, f"文件修改失败: {str(e)}"

    @staticmethod
    def _slow_edit(
        file_path: str, patches: List[Dict[str, str]], agent: Any
    ) -> Tuple[bool, str]:
        """使用AI模型生成补丁并应用到文件

        当_fast_edit方法失败时调用此方法，使用AI模型生成更精确的补丁。
        特点：
        1. 适用于复杂修改场景或需要上下文理解的修改
        2. 会自动处理大文件上传问题
        3. 会尝试最多3次生成有效的补丁
        4. 生成的补丁会再次通过_fast_edit方法应用
        5. 如果失败会自动回滚修改

        Args:
            file_path: 要修改的文件路径，支持绝对路径和相对路径
            patches: 补丁列表，每个补丁包含search(搜索文本)和replace(替换文本)
            agent: 执行处理的agent实例，用于访问AI模型平台

        Returns:
            Tuple[bool, str]:
                返回处理结果元组，第一个元素表示是否成功(True/False)，
                第二个元素为结果信息，成功时为修改后的文件内容，失败时为错误信息
        """
        try:
            model = PlatformRegistry().get_normal_platform()

            # 读取原始文件内容
            file_content = ""
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    file_content = f.read()

            is_large_context = is_context_overflow(file_content)
            upload_success = False

            # 如果是大文件，尝试上传到模型平台
            if (
                is_large_context
                and model.support_upload_files()
                and model.upload_files([file_path])
            ):
                upload_success = True

            model.set_suppress_output(False)

            # 构建补丁内容
            patch_content = []
            for patch in patches:
                patch_content.append(
                    {
                        "SEARCH": patch["SEARCH"],
                        "REPLACE": patch["REPLACE"],
                    }
                )

            # 构建提示词
            main_prompt = f"""
# 代码补丁生成专家指南

## 任务描述
你是一位精确的代码补丁生成专家，需要根据补丁描述生成精确的代码差异。

### 补丁内容
```
{str(patch_content)}
```

## 补丁生成要求
1. **精确性**：严格按照补丁的意图修改代码
2. **格式一致性**：严格保持原始代码的格式风格，如果补丁中缩进或者空行与原代码不一致，则需要修正补丁中的缩进或者空行
3. **最小化修改**：只修改必要的代码部分，保持其他部分不变
4. **上下文完整性**：提供足够的上下文，确保补丁能准确应用

## 输出格式规范
- 使用{ot("DIFF")}块包围每个需要修改的代码段
- 每个{ot("DIFF")}块必须包含SEARCH部分和REPLACE部分
- SEARCH部分是需要查找的原始代码
- REPLACE部分是替换后的新代码
- 确保SEARCH部分能在原文件中**唯一匹配**
- 如果修改较大，可以使用多个{ot("DIFF")}块

## 输出模板
{ot("DIFF")}
{ot("SEARCH")}[需要查找的原始代码，包含足够上下文，避免出现可匹配多处的情况]{ct("SEARCH")}
{ot("REPLACE")}[替换后的新代码]{ct("REPLACE")}
{ct("DIFF")}

{ot("DIFF")}
{ot("SEARCH")}[另一处需要查找的原始代码，包含足够上下文，避免出现可匹配多处的情况]{ct("SEARCH")}
{ot("REPLACE")}[另一处替换后的新代码]{ct("REPLACE")}
{ct("DIFF")}
"""

            # 尝试最多3次生成补丁
            for _ in range(3):
                if is_large_context:
                    if upload_success:
                        response = model.chat_until_success(main_prompt)
                    else:
                        file_prompt = f"""
# 原始代码
{file_content}
"""
                        response = model.chat_until_success(main_prompt + file_prompt)
                else:
                    file_prompt = f"""
# 原始代码
{file_content}
"""
                    response = model.chat_until_success(main_prompt + file_prompt)

                # 检查是否被中断
                if get_interrupt():
                    set_interrupt(False)
                    user_input = agent.multiline_inputer(
                        "补丁应用被中断，请输入补充信息:"
                    )
                    if not user_input.strip():
                        return False, "用户中断了补丁应用"
                    return False, f"用户中断了补丁应用并提供了补充信息: {user_input}"

                # 解析生成的补丁
                diff_blocks = re.finditer(
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
                    response,
                    re.DOTALL,
                )

                generated_patches = []
                for match in diff_blocks:
                    generated_patches.append(
                        {
                            "SEARCH": match.group(1).strip(),
                            "REPLACE": match.group(2).strip(),
                        }
                    )

                if generated_patches:
                    # 尝试应用生成的补丁
                    success, result = EditFileHandler._fast_edit(
                        file_path, generated_patches
                    )
                    if success:
                        return True, result

            return False, "AI模型无法生成有效的补丁"

        except Exception as e:
            print(f"❌ 文件修改失败: {str(e)}")
            revert_file(file_path)
            return False, f"文件修改失败: {str(e)}"
