# -*- coding: utf-8 -*-
"""Jsonnet 兼容层 - 提供类似 json5.loads() 的接口"""

import json
from typing import Any

import _jsonnet


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
    
    block = s.strip()
    
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
    if block.rstrip().endswith("```"):
        # 找到最后一个 ``` 的位置
        last_backticks = block.rfind("```")
        if last_backticks >= 0:
            block = block[:last_backticks].rstrip()
    
    return block.strip()


def loads(s: str) -> Any:
    """
    解析 JSON/Jsonnet 格式的字符串，返回 Python 对象
    
    使用 jsonnet 来解析，支持 JSON5 特性（注释、尾随逗号、|||分隔符多行字符串等）
    
    自动处理 markdown 代码块标记：如果输入包含 ```json5、```json、``` 等代码块标记，
    会自动去除这些标记后再解析。
    
    参数:
        s: 要解析的字符串（可能包含 markdown 代码块标记）
        
    返回:
        解析后的 Python 对象
        
    异常:
        ValueError: 如果解析失败
    """
    # 自动去除 markdown 代码块标记
    cleaned = _strip_markdown_code_blocks(s)
    
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

