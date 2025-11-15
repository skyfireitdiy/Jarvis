# -*- coding: utf-8 -*-
"""Jsonnet 兼容层 - 提供类似 json5.loads() 的接口"""

import json
from typing import Any

import _jsonnet


def loads(s: str) -> Any:
    """
    解析 JSON/Jsonnet 格式的字符串，返回 Python 对象
    
    使用 jsonnet 来解析，支持 JSON5 特性（注释、尾随逗号、|||分隔符多行字符串等）
    
    参数:
        s: 要解析的字符串
        
    返回:
        解析后的 Python 对象
        
    异常:
        ValueError: 如果解析失败
    """
    # 使用 jsonnet 解析，支持 JSON5 和 Jsonnet 语法
    result_json = _jsonnet.evaluate_snippet("<input>", s)
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

