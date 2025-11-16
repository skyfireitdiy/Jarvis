# -*- coding: utf-8 -*-
"""Jsonnet 兼容层 - 提供类似 json5.loads() 的接口"""

import json
from typing import Any

import _jsonnet


def _fix_jsonnet_multiline_strings(s: str) -> tuple[str, dict]:
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
    if not isinstance(s, str):
        return s
    
    import re
    
    # 匹配 ||| 多行字符串模式
    # 格式：||| 后跟可选空白和换行，然后是内容，最后是 |||
    # 使用非贪婪匹配，确保匹配到最近的 |||
    pattern = r'(\|\|\|)(\s*\n)(.*?)(\n\s*\|\|\|)'
    
    def fix_match(match):
        start_marker = match.group(1)  # |||
        whitespace_after = match.group(2)  # 空白和换行
        content = match.group(3)  # 多行内容
        end_marker = match.group(4)  # 换行、空白和 |||
        
        # jsonnet 要求结束标记 ||| 必须单独一行且没有缩进（从行首开始）
        # 如果结束标记前面有空白，需要去除
        if end_marker.startswith('\n'):
            # 提取结束标记前的空白
            end_whitespace = end_marker[1:]  # 去除第一个换行
            if end_whitespace.startswith(' '):
                # 去除所有前导空白，只保留换行和 |||
                end_marker = '\n|||'
        
        # 如果内容为空，直接返回
        if not content.strip():
            return match.group(0), {}
        
        # 按行分割内容
        lines = content.split('\n')
        
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
            if first_line.strip() and first_line.startswith((' ', '\t')):
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
                        if line.startswith((' ', '\t')):
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
                if line.strip() and not line.startswith((' ', '\t')):
                    has_unindented_lines = True
                    break
        
        # 记录所有行的原始缩进信息（用于恢复）
        # 如果存在不同缩进级别的行，我们需要记录每行的原始缩进
        original_indents = {}  # 键：行内容（去除缩进后），值：原始缩进级别
        has_mixed_indents = False
        
        # 检查是否有混合缩进（不同行有不同的缩进级别）
        if lines:
            seen_indents = set()
            for line in lines:
                if line.strip():
                    line_indent = len(line) - len(line.lstrip())
                    if line_indent > 0:
                        seen_indents.add(line_indent)
                    line_content = line.lstrip()
                    # 记录原始缩进（如果有）
                    if line_indent > 0:
                        original_indents[line_content] = line_indent
            
            # 如果有多个不同的缩进级别，说明是混合缩进
            if len(seen_indents) > 1:
                has_mixed_indents = True
        
        # 如果第一行有缩进，但后续行没有，我们也需要记录
        if first_line_has_indent and has_unindented_lines:
            has_mixed_indents = True
            # 记录第一行的原始缩进
            first_line_content = lines[0].lstrip()
            original_indents[first_line_content] = first_line_indent
        
        # 统一所有行的缩进级别（以满足 jsonnet 的要求）
        # 但我们会记录原始缩进信息，以便在解析后恢复
        for i in range(len(lines)):
            line = lines[i]
            if line.strip():  # 只处理非空行
                line_content = line.lstrip()
                # 统一使用第一行的缩进级别（如果第一行有缩进）
                # 或者使用默认的缩进级别
                lines[i] = ' ' * indent_level + line_content
        
        # 重新组合内容
        fixed_content = '\n'.join(lines)
        
        # 返回修复后的内容和原始缩进信息
        indent_info = {}
        if has_mixed_indents and original_indents:
            indent_info = original_indents
        
        return start_marker + whitespace_after + fixed_content + end_marker, indent_info
    
    # 使用 DOTALL 标志，使 . 匹配换行符
    # 收集所有修复后的内容和缩进信息
    all_indent_info = {}
    fixed_parts = []
    last_end = 0
    
    for match in re.finditer(pattern, s, flags=re.DOTALL):
        # 添加匹配前的部分
        fixed_parts.append(s[last_end:match.start()])
        
        # 修复匹配的部分
        fixed_content, indent_info = fix_match(match)
        fixed_parts.append(fixed_content)
        
        # 合并缩进信息
        all_indent_info.update(indent_info)
        
        last_end = match.end()
    
    # 添加剩余部分
    fixed_parts.append(s[last_end:])
    fixed = ''.join(fixed_parts)
    
    return fixed, all_indent_info


def _restore_first_line_indent(obj: Any, indent_info: dict) -> Any:
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
            lines = obj.split('\n')
            restored_lines = []
            for line in lines:
                if line.strip():
                    # 去除当前行的缩进，获取内容
                    line_content = line.lstrip()
                    # 检查是否有对应的原始缩进信息
                    if line_content in indent_info:
                        # 恢复原始缩进
                        original_indent = indent_info[line_content]
                        restored_lines.append(' ' * original_indent + line_content)
                    else:
                        # 没有原始缩进信息，保持原样
                        restored_lines.append(line)
                else:
                    # 空行保持原样
                    restored_lines.append(line)
            return '\n'.join(restored_lines)
        return obj
    else:
        return obj


def _strip_markdown_code_blocks(s: str) -> str:
    """
    去除字符串中的 markdown 代码块标记（如 ```json5、```json、``` 等）
    
    参数:
        s: 输入字符串
        
    返回:
        清理后的字符串
    """
    if not isinstance(s, str):
        return s
    
    import re
    
    block = s.strip()
    
    # 使用正则表达式匹配并去除代码块标记
    # 匹配开头的 ```language 或 ```（可选语言标识，后跟换行或字符串结尾）
    # 匹配结尾的 ```（前面可能有换行和空白）
    pattern = r'^```[a-zA-Z0-9_+-]*\s*\n?(.*?)\n?```\s*$'
    match = re.match(pattern, block, re.DOTALL)
    if match:
        # 如果匹配成功，提取代码块内容
        block = match.group(1).strip()
    else:
        # 如果正则不匹配，尝试手动去除（向后兼容）
        # 去除开头的代码块标记（如 ```json5、```json、``` 等）
        if block.startswith("```"):
            # 找到第一个换行符或字符串结尾
            first_newline = block.find("\n")
            if first_newline >= 0:
                block = block[first_newline + 1:]
            else:
                # 没有换行符，说明整个块可能就是 ```language
                block = ""
        
        # 去除结尾的代码块标记（包括前面的换行）
        # 使用 rstrip 去除末尾空白后再检查，确保能匹配到 ``` 即使前面有空白
        block_rstripped = block.rstrip()
        if block_rstripped.endswith("```"):
            # 找到最后一个 ``` 的位置（在原始 block 上查找，但考虑空白）
            last_backticks = block.rfind("```")
            if last_backticks >= 0:
                block = block[:last_backticks].rstrip()
    
    return block.strip()


def loads(s: str) -> Any:
    """
    解析 JSON/Jsonnet 格式的字符串，返回 Python 对象
    
    使用 jsonnet 来解析，支持 JSON5 特性（注释、尾随逗号、|||分隔符多行字符串等）
    
    自动处理：
    - markdown 代码块标记：如果输入包含 ```json5、```json、``` 等代码块标记，
      会自动去除这些标记后再解析。
    - ||| 多行字符串缩进：自动为 ||| 多行字符串的第一行添加必要的缩进，
      避免 "text block's first line must start with whitespace" 错误。
    
    参数:
        s: 要解析的字符串（可能包含 markdown 代码块标记）
        
    返回:
        解析后的 Python 对象
        
    异常:
        ValueError: 如果解析失败
    """
    # 自动去除 markdown 代码块标记
    cleaned = _strip_markdown_code_blocks(s)
    
    # 自动修复 ||| 多行字符串的缩进问题
    cleaned, indent_info = _fix_jsonnet_multiline_strings(cleaned)
    
    # 使用 jsonnet 解析，支持 JSON5 和 Jsonnet 语法
    result_json = _jsonnet.evaluate_snippet("<input>", cleaned)
    # jsonnet 返回的是 JSON 字符串，需要再次解析
    result = json.loads(result_json)
    
    # 如果第一行原本有缩进，恢复第一行的缩进
    if indent_info:
        result = _restore_first_line_indent(result, indent_info)
    
    return result


def dumps(obj: Any, **kwargs) -> str:
    """
    将 Python 对象序列化为 JSON 字符串
    
    参数:
        obj: 要序列化的对象
        **kwargs: 传递给 json.dumps 的其他参数
        
    返回:
        JSON 字符串
    """
    return json.dumps(obj, **kwargs)

