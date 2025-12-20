# -*- coding: utf-8 -*-
"""Jsonnet 兼容层 - 提供类似 json5.loads() 的接口"""

import json
from typing import Any
from typing import Dict
from typing import Match

import _jsonnet


def _fix_jsonnet_multiline_strings(s: str) -> tuple[str, Dict[str, str]]:
    """
    修复 jsonnet ||| 多行字符串的缩进问题。

    jsonnet 要求 ||| 之后的第一行内容必须有缩进（至少一个空格），
    否则会报错 "text block's first line must start with whitespace"。

    此函数会自动检测并修复这个问题。

    参数:
        s: 输入字符串

    返回:
        (修复后的字符串, 第一行原始缩进信息字典)
        缩进信息字典的键是修复后字符串中 ||| 多行字符串的标记，
        值是第一行的原始缩进级别（如果第一行原本有缩进但后续行没有）
    """

    import re

    # 匹配 ||| 多行字符串模式
    # 格式：||| 后跟可选空白和换行，然后是内容，最后是 |||
    # 使用非贪婪匹配，确保匹配到最近的 |||
    pattern = r"(\|\|\|)(\s*\n)(.*?)(\n\s*\|\|\|)"

    def fix_match(match: Match[str]) -> tuple[str, Dict[str, str]]:
        start_marker = match.group(1)  # |||
        whitespace_after = match.group(2)  # 空白和换行
        content = match.group(3)  # 多行内容
        end_marker = match.group(4)  # 换行、空白和 |||

        # jsonnet 要求结束标记 ||| 必须单独一行且没有缩进（从行首开始）
        # 无论原来是什么格式，统一修复为 '\n|||'
        end_marker = "\n|||"

        # 如果内容为空，返回修复后的结束标记
        if not content.strip():
            return start_marker + whitespace_after + content + end_marker, {}

        # 按行分割内容

        lines = content.split("\n")

        # 确定缩进级别：
        # 1. 如果第一行有缩进，使用第一行的缩进级别
        # 2. 如果第一行是空行，查找第一个非空行的缩进级别
        # 3. 如果第一行没有缩进，使用默认的一个空格
        # 4. 如果所有行都为空，使用默认的一个空格
        indent_level = 1  # 默认缩进级别
        first_line_has_indent = False
        first_line_indent = 0

        if lines:
            first_line = lines[0]
            if first_line.strip() and first_line.startswith((" ", "\t")):
                # 第一行已有缩进，记录其缩进级别
                first_line_indent = len(first_line) - len(first_line.lstrip())
                first_line_has_indent = True
                indent_level = first_line_indent
                # 确保至少有一个空格
                if indent_level == 0:
                    indent_level = 1
            elif not first_line.strip():
                # 第一行是空行，查找第一个非空行的缩进级别
                for line in lines[1:]:
                    if line.strip():
                        if line.startswith((" ", "\t")):
                            # 找到第一个非空行，使用其缩进级别
                            indent_level = len(line) - len(line.lstrip())
                            # 确保至少有一个空格
                            if indent_level == 0:
                                indent_level = 1
                        else:
                            # 第一个非空行没有缩进，使用默认的一个空格
                            indent_level = 1
                        break

        # 对每一行都统一缩进级别
        # jsonnet 的 ||| 要求所有行都有相同的缩进级别，并会去除所有行的最小共同缩进前缀
        # 为了保留第一行的缩进，我们需要：
        # 1. 让所有行都有相同的缩进（满足 jsonnet 的要求）
        # 2. 记录第一行的原始缩进级别，以便在解析后恢复
        # 3. 在解析后，为第一行添加原始缩进

        # 检查是否有后续行没有缩进（需要修复）
        has_unindented_lines = False
        if first_line_has_indent:
            for line in lines[1:]:
                if line.strip() and not line.startswith((" ", "\t")):
                    has_unindented_lines = True
                    break

        # 记录所有行的原始缩进信息（用于恢复）
        # 如果存在不同缩进级别的行，我们需要记录每行的原始缩进
        original_indents = {}  # 键：行内容（去除缩进后），值：原始缩进级别
        has_mixed_indents = False

        # 记录所有行的原始缩进信息（无论是否混合缩进，都需要记录以便恢复）
        # 保存原始缩进字符串而不是长度，以保留 Tab 等特殊字符
        if lines:
            seen_indents = set()
            for line in lines:
                if line.strip():
                    line_indent = len(line) - len(line.lstrip())
                    seen_indents.add(line_indent)
                    line_content = line.lstrip()
                    # 记录原始缩进字符串（保留 Tab 等字符）
                    original_indents[line_content] = line[:line_indent]

            # 如果有多个不同的缩进级别，说明是混合缩进
            if len(seen_indents) > 1:
                has_mixed_indents = True

        # 如果第一行有缩进，但后续行没有，我们也需要记录
        if first_line_has_indent and has_unindented_lines:
            has_mixed_indents = True
            # 记录第一行的原始缩进字符串
            first_line_content = lines[0].lstrip()
            original_indents[first_line_content] = lines[0][:first_line_indent]

        # jsonnet的text block规则：所有行缩进必须 >= 首行缩进
        # 因此我们统一所有行为相同的基础缩进，通过恢复逻辑还原原始缩进
        base_indent = 1  # 统一使用1空格缩进

        # 统一所有行的缩进为基础缩进（满足jsonnet要求）

        for i in range(len(lines)):
            line = lines[i]
            if line.strip():  # 只处理非空行
                line_content = line.lstrip()
                lines[i] = " " * base_indent + line_content

        # 重新组合内容
        fixed_content = "\n".join(lines)

        # 返回修复后的内容和原始缩进信息
        # 只要有混合缩进，就返回缩进信息以便恢复
        indent_info = original_indents if has_mixed_indents else {}

        return start_marker + whitespace_after + fixed_content + end_marker, indent_info

    # 使用 DOTALL 标志，使 . 匹配换行符
    # 收集所有修复后的内容和缩进信息
    all_indent_info = {}
    fixed_parts = []
    last_end = 0

    for match in re.finditer(pattern, s, flags=re.DOTALL):
        # 添加匹配前的部分
        fixed_parts.append(s[last_end : match.start()])

        # 修复匹配的部分
        fixed_content, indent_info = fix_match(match)
        fixed_parts.append(fixed_content)

        # 合并缩进信息
        all_indent_info.update(indent_info)

        last_end = match.end()

    # 添加剩余部分
    fixed_parts.append(s[last_end:])
    fixed = "".join(fixed_parts)

    return fixed, all_indent_info


def _restore_first_line_indent(obj: Any, indent_info: Dict[str, str]) -> Any:
    """
    恢复第一行的原始缩进。

    参数:
        obj: 解析后的对象
        indent_info: 缩进信息字典

    返回:
        恢复缩进后的对象
    """
    if not indent_info:
        return obj

    if isinstance(obj, dict):
        return {k: _restore_first_line_indent(v, indent_info) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_restore_first_line_indent(item, indent_info) for item in obj]
    elif isinstance(obj, str):
        # 检查字符串的每一行是否原本有缩进
        # 如果存在原始缩进信息，恢复每行的原始缩进
        if indent_info:
            lines = obj.split("\n")
            restored_lines = []
            for line in lines:
                if line.strip():
                    # 去除当前行的缩进，获取内容
                    line_content = line.lstrip()
                    # 检查是否有对应的原始缩进信息
                    if line_content in indent_info:
                        # 恢复原始缩进（直接使用保存的缩进字符串，保留 Tab 等字符）
                        original_indent = indent_info[line_content]
                        restored_lines.append(original_indent + line_content)
                    else:
                        # 没有原始缩进信息，保持原样
                        restored_lines.append(line)
                else:
                    # 空行保持原样
                    restored_lines.append(line)
            return "\n".join(restored_lines)
        return obj
    else:
        return obj


def _convert_backtick_multiline_strings(s: str) -> str:
    """
    将 JSON 值中的 ``` 多行字符串标识转换为 |||。

    此函数识别 JSON 值位置（如 "key": ```）的 ``` 标记，并将其转换为 |||，
    以便与 jsonnet 的 ||| 多行字符串语法兼容。

    识别规则：
    - 在 JSON 值位置（冒号后）的 ``` 会被转换为 |||
    - 已经去除 markdown 代码块标记后，剩余的 ``` 通常是多行字符串标识

    参数:
        s: 输入字符串（应该已经去除 markdown 代码块标记）

    返回:
        转换后的字符串（``` 转换为 |||）
    """

    import re

    # 匹配 JSON 值中的 ``` 多行字符串
    # 格式：": ``` 或 ":``` 后跟可选空白和换行，然后是内容，最后是换行和 ```
    # 使用非贪婪匹配，确保匹配到最近的 ```
    # 注意：这个模式匹配的是 JSON 值位置（冒号后）的 ```
    pattern = r"(:\s*)(```)(\s*\n)(.*?)(\n\s*```)"

    def convert_match(match: Match[str]) -> str:
        colon = match.group(1)  # 冒号和可选空白
        match.group(2)  # ``` (保留用于匹配，但不使用)
        whitespace_after = match.group(3)  # 空白和换行
        content = match.group(4)  # 多行内容
        match.group(5)  # 换行、空白和 ``` (保留用于匹配，但不使用)

        # 将 ``` 转换为 |||
        return colon + "|||" + whitespace_after + content + "\n|||"

    # 替换所有匹配的模式
    result = re.sub(pattern, convert_match, s, flags=re.DOTALL)

    return result


def _strip_markdown_code_blocks(s: str) -> str:
    """
    去除字符串中的 markdown 代码块标记（如 ```json5、```json、``` 等）

    支持以下场景：
    - 代码块前后有空白/换行：\n```json\n{...}\n```
    - 代码块不在字符串开头：prefix\n```json\n{...}\n```
    - 标准格式：```json\n{...}\n```

    参数:
        s: 输入字符串

    返回:
        清理后的字符串（如果输入不是字符串，则原样返回）
    """

    import re

    # 如果输入不是字符串，则原样返回
    if not isinstance(s, str):
        return s

    # 先去除首尾空白，但保留内部结构
    block = s.strip()

    # 使用正则表达式匹配并去除代码块标记
    # 尝试多种模式，从严格到宽松

    # 模式1：标准格式，代码块在开头和结尾
    # 匹配：```language + 可选空白 + 可选换行 + 内容 + 可选换行 + 可选空白 + ```
    pattern1 = r"^```[a-zA-Z0-9_+-]*\s*\n?(.*?)\n?\s*```\s*$"
    match = re.match(pattern1, block, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 模式2：代码块前后可能有额外空白/换行，但要求代码块在字符串的开头或结尾
    # 只匹配整个字符串被代码块包裹的情况，不匹配 JSON 值内部的 ```
    # 匹配：字符串开头（可选空白）+ ```language + 可选空白 + 换行 + 内容 + 换行 + 可选空白 + ``` + 字符串结尾（可选空白）
    pattern2 = r"^\s*```[a-zA-Z0-9_+-]*\s*\n(.*?)\n\s*```\s*$"
    match = re.match(pattern2, block, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 模式3：更宽松的匹配，不要求换行，但要求代码块在字符串的开头或结尾
    # 只匹配整个字符串被代码块包裹的情况，不匹配 JSON 值内部的 ```
    # 匹配：字符串开头（可选空白）+ ```language + 可选空白 + 内容 + 可选空白 + ``` + 字符串结尾（可选空白）
    pattern3 = r"^\s*```[a-zA-Z0-9_+-]*\s*(.*?)\s*```\s*$"
    match = re.match(pattern3, block, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 如果正则都不匹配，尝试手动去除（向后兼容）
    # 但只处理整个字符串被代码块包裹的情况（代码块在开头且结尾也有 ```）
    block_stripped = block.strip()
    if block_stripped.startswith("```") and block_stripped.rstrip().endswith("```"):
        # 找到开头的 ``` 后的内容
        after_start = 3  # 跳过 ```
        # 跳过语言标识（如果有）
        while after_start < len(block_stripped) and block_stripped[after_start] not in (
            "\n",
            "\r",
            " ",
            "\t",
        ):
            after_start += 1
        # 跳过空白字符
        while after_start < len(block_stripped) and block_stripped[after_start] in (
            " ",
            "\t",
        ):
            after_start += 1
        # 跳过换行符（如果有）
        if after_start < len(block_stripped) and block_stripped[after_start] in (
            "\n",
            "\r",
        ):
            after_start += 1
            # 处理 \r\n
            if (
                after_start < len(block_stripped)
                and block_stripped[after_start] == "\n"
                and block_stripped[after_start - 1] == "\r"
            ):
                after_start += 1

        # 找到结尾的 ``` 的位置
        before_end = block_stripped.rfind("```")
        if before_end > after_start:
            # 提取内容（去除结尾的 ``` 和前面的空白）
            content = block_stripped[after_start:before_end].rstrip()
            return content

    return block.strip()


def loads(s: str) -> Any:
    """
    解析 JSON/Jsonnet 格式的字符串，返回 Python 对象

    使用 jsonnet 来解析，支持 JSON5 特性（注释、尾随逗号、||| 或 ``` 分隔符多行字符串等）

    自动处理：
    - markdown 代码块标记：如果输入包含 ```json5、```json、``` 等代码块标记，
      会自动去除这些标记后再解析。
    - ``` 多行字符串：支持使用 ``` 代替 ||| 作为多行字符串标识（在 JSON 值位置）。
    - ||| 多行字符串缩进：自动为 ||| 多行字符串的第一行添加必要的缩进，
      避免 "text block's first line must start with whitespace" 错误。

    参数:
        s: 要解析的字符串（可能包含 markdown 代码块标记）

    返回:
        解析后的 Python 对象

    异常:
        ValueError: 如果解析失败
    """
    if not isinstance(s, str) or not s.strip():
        raise ValueError("输入字符串为空")

    # 自动去除 markdown 代码块标记
    cleaned = _strip_markdown_code_blocks(s)

    # 验证：确保没有残留的代码块标记（在字符串开头或结尾）
    # 字符串内容中的 ``` 是合法的，不需要处理
    cleaned_stripped = cleaned.strip()
    if cleaned_stripped.startswith("```") or cleaned_stripped.rstrip().endswith("```"):
        # 如果还有代码块标记，可能是手动去除逻辑没有正确工作
        # 再次尝试去除（防止边界情况）
        cleaned = _strip_markdown_code_blocks(cleaned)
        cleaned_stripped = cleaned.strip()
        # 如果仍然有，说明可能是格式问题，记录警告但继续处理
        if cleaned_stripped.startswith("```") or cleaned_stripped.rstrip().endswith(
            "```"
        ):
            # 最后尝试：手动去除开头和结尾的 ```
            while cleaned_stripped.startswith("```"):
                # 找到第一个换行或字符串结尾
                first_newline = cleaned_stripped.find("\n", 3)
                if first_newline >= 0:
                    cleaned_stripped = cleaned_stripped[first_newline + 1 :]
                else:
                    # 没有换行，可能是 ```language 格式
                    cleaned_stripped = cleaned_stripped[3:].lstrip()
                    # 跳过语言标识
                    while cleaned_stripped and cleaned_stripped[0] not in (
                        "\n",
                        "\r",
                        " ",
                        "\t",
                    ):
                        cleaned_stripped = cleaned_stripped[1:]
                    break
            while cleaned_stripped.rstrip().endswith("```"):
                last_backticks = cleaned_stripped.rfind("```")
                if last_backticks >= 0:
                    cleaned_stripped = cleaned_stripped[:last_backticks].rstrip()
                else:
                    break
            cleaned = cleaned_stripped

    # 将 JSON 值中的 ``` 多行字符串标识转换为 |||
    cleaned = _convert_backtick_multiline_strings(cleaned)

    # 自动修复 ||| 多行字符串的缩进问题
    cleaned, indent_info = _fix_jsonnet_multiline_strings(cleaned)

    # 使用 jsonnet 解析，支持 JSON5 和 Jsonnet 语法
    try:
        result_json = _jsonnet.evaluate_snippet("<input>", cleaned)
    except RuntimeError as e:
        # 提供更详细的错误信息
        error_msg = str(e)
        if "Could not lex the character" in error_msg or "`" in error_msg:
            # 检查是否还有残留的代码块标记
            if "```" in cleaned:
                # 找到所有 ``` 的位置
                import re

                matches = list(re.finditer(r"```", cleaned))
                for match in matches:
                    pos = match.start()
                    context = cleaned[max(0, pos - 30) : min(len(cleaned), pos + 50)]
                    # 检查是否在字符串内部（被引号包围）
                    before = cleaned[:pos]
                    # 简单检查：如果前面有奇数个引号，说明在字符串内部
                    quote_count = before.count('"') - before.count('\\"')
                    if quote_count % 2 == 0:
                        # 不在字符串内部，可能是残留的代码块标记
                        raise ValueError(
                            f"检测到残留的代码块标记 ``` 在位置 {pos}。"
                            f"上下文: {repr(context)}。"
                            f"原始错误: {error_msg}"
                        )
        raise ValueError(f"JSON 解析失败: {error_msg}")

    # jsonnet 返回的是 JSON 字符串，需要再次解析
    result = json.loads(result_json)

    # 如果第一行原本有缩进，恢复第一行的缩进
    if indent_info:
        result = _restore_first_line_indent(result, indent_info)

    return result


def dumps(obj: Any, **kwargs: Any) -> str:
    """
    将 Python 对象序列化为 JSON 字符串

    参数:
        obj: 要序列化的对象
        **kwargs: 传递给 json.dumps 的其他参数

    返回:
        JSON 字符串
    """
    return json.dumps(obj, **kwargs)
