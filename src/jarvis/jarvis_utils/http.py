# -*- coding: utf-8 -*-
"""
HTTP 工具模块
提供统一的 HTTP 请求封装，统一管理超时设置
"""

import httpx
from typing import Any, Dict, Optional, Union


# 默认超时设置：(连接超时, 读取超时)
DEFAULT_TIMEOUT = (600, 600)


def post(
    url: str,
    data: Optional[Union[Dict[str, Any], str, bytes]] = None,
    json: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> httpx.Response:
    """
    发送 POST 请求，统一管理超时设置

    参数:
        url: 请求的 URL
        data: (可选) 请求体数据 (表单数据或原始数据)
        json: (可选) JSON 数据，会自动设置 Content-Type
        **kwargs: 其他传递给 httpx.post 的参数

    返回:
        httpx.Response 对象
    """
    # 如果没有提供 timeout，使用默认值
    if "timeout" not in kwargs:
        kwargs["timeout"] = DEFAULT_TIMEOUT

    # 移除 httpx 不支持的 stream 参数（httpx 默认支持流式读取）
    kwargs.pop("stream", None)

    return httpx.post(url=url, data=data, json=json, **kwargs)  # type: ignore


def put(
    url: str, data: Optional[Union[Dict[str, Any], str, bytes]] = None, **kwargs
) -> httpx.Response:
    """
    发送 PUT 请求，统一管理超时设置

    参数:
        url: 请求的 URL
        data: (可选) 请求体数据 (表单数据或原始数据)
        **kwargs: 其他传递给 httpx.put 的参数

    返回:
        httpx.Response 对象
    """
    # 如果没有提供 timeout，使用默认值
    if "timeout" not in kwargs:
        kwargs["timeout"] = DEFAULT_TIMEOUT

    return httpx.put(url=url, data=data, **kwargs)  # type: ignore


def delete(url: str, **kwargs) -> httpx.Response:
    """
    发送 DELETE 请求，统一管理超时设置

    参数:
        url: 请求的 URL
        **kwargs: 其他传递给 httpx.delete 的参数

    返回:
        httpx.Response 对象
    """
    # 如果没有提供 timeout，使用默认值
    if "timeout" not in kwargs:
        kwargs["timeout"] = DEFAULT_TIMEOUT

    return httpx.delete(url=url, **kwargs)  # type: ignore
