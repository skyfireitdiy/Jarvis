# -*- coding: utf-8 -*-
"""Jsonnet 兼容层 - 提供类似 json5.loads() 的接口"""

import json
from typing import Any

import _jsonnet


def _fix_jsonnet_multiline_strings(s: str) -> str:
    """
    修复 jsonnet ||| 多行字符串的缩进问题。
    
    jsonnet 要求 ||| 之后的第一行内容必须有缩进（至少一个空格），
    否则会报错 "text block's first line must start with whitespace"。
    
    此函数会自动检测并修复这个问题。
    
    参数:
        s: 输入字符串
        
    返回:
        修复后的字符串
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
        
        # 如果内容为空，直接返回
        if not content.strip():
            return match.group(0)
        
        # 按行分割内容
        lines = content.split('\n')
        
        # 确定缩进级别：
        # 1. 如果第一行有缩进，使用第一行的缩进级别
        # 2. 如果第一行没有缩进，使用默认的一个空格
        # 3. 如果所有行都为空，使用默认的一个空格
        indent_level = 1  # 默认缩进级别
        if lines:
            first_line = lines[0]
            if first_line.strip() and first_line.startswith((' ', '\t')):
                # 第一行已有缩进，使用其缩进级别
                indent_level = len(first_line) - len(first_line.lstrip())
                # 确保至少有一个空格
                if indent_level == 0:
                    indent_level = 1
        
        # 对每一行都统一缩进级别：使用第一行的缩进级别
        # jsonnet 要求所有行都有相同的缩进级别
        for i in range(len(lines)):
            line = lines[i]
            if line.strip():  # 只处理非空行
                # 统一使用第一行的缩进级别
                # 去除原有的前导空白，然后添加统一的缩进
                line_content = line.lstrip()
                lines[i] = ' ' * indent_level + line_content
        
        # 重新组合内容
        fixed_content = '\n'.join(lines)
        
        return start_marker + whitespace_after + fixed_content + end_marker
    
    # 使用 DOTALL 标志，使 . 匹配换行符
    fixed = re.sub(pattern, fix_match, s, flags=re.DOTALL)
    
    return fixed


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
    cleaned = _fix_jsonnet_multiline_strings(cleaned)
    
    # 使用 jsonnet 解析，支持 JSON5 和 Jsonnet 语法
    result_json = _jsonnet.evaluate_snippet("<input>", cleaned)
    # jsonnet 返回的是 JSON 字符串，需要再次解析
    return json.loads(result_json)


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

