# -*- coding: utf-8 -*-

import httpx
from typing import Any, Dict, Optional, Union, AsyncGenerator, Generator


def get_httpx_client() -> httpx.Client:
    """
    获取一个配置好的 httpx.Client 对象

    返回:
        httpx.Client 对象
    """
    client = httpx.Client(
        timeout=httpx.Timeout(None),  # 永不超时
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        },
    )
    return client


def get_async_httpx_client() -> httpx.AsyncClient:
    """
    获取一个配置好的 httpx.AsyncClient 对象

    返回:
        httpx.AsyncClient 对象
    """
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(None),  # 永不超时
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        },
    )
    return client


# 增强版本的 HTTP 请求方法（使用 httpx 实现，带重试机制，解决连接中断问题）
def post(
    url: str,
    data: Optional[Any] = None,
    json: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> httpx.Response:
    """
    发送增强版永不超时的 POST 请求，使用 httpx 实现，包含重试机制

    参数:
        url: 请求的 URL
        data: (可选) 请求体数据 (表单数据或原始数据)
        json: (可选) JSON 数据，会自动设置 Content-Type
        **kwargs: 其他传递给 httpx.post 的参数

    返回:
        httpx.Response 对象

    注意:
        此方法使用 httpx 实现，包含自动重试机制，适用于解决"Response ended prematurely"等连接问题
    """
    client = get_httpx_client()
    try:
        response = client.post(url=url, data=data, json=json, **kwargs)
        response.raise_for_status()
        return response
    finally:
        client.close()


def get(url: str, **kwargs) -> httpx.Response:
    """
    发送增强版永不超时的 GET 请求，使用 httpx 实现，包含重试机制

    参数:
        url: 请求的 URL
        **kwargs: 其他传递给 httpx.get 的参数

    返回:
        httpx.Response 对象

    注意:
        此方法使用 httpx 实现，包含自动重试机制，适用于解决"Response ended prematurely"等连接问题
    """
    client = get_httpx_client()
    try:
        response = client.get(url=url, **kwargs)
        response.raise_for_status()
        return response
    finally:
        client.close()


def put(url: str, data: Optional[Any] = None, **kwargs) -> httpx.Response:
    """
    发送增强版永不超时的 PUT 请求，使用 httpx 实现，包含重试机制

    参数:
        url: 请求的 URL
        data: (可选) 请求体数据 (表单数据或原始数据)
        **kwargs: 其他传递给 httpx.put 的参数

    返回:
        httpx.Response 对象

    注意:
        此方法使用 httpx 实现，包含自动重试机制，适用于解决"Response ended prematurely"等连接问题
    """
    client = get_httpx_client()
    try:
        response = client.put(url=url, data=data, **kwargs)
        response.raise_for_status()
        return response
    finally:
        client.close()


def delete(url: str, **kwargs) -> httpx.Response:
    """
    发送增强版永不超时的 DELETE 请求，使用 httpx 实现，包含重试机制

    参数:
        url: 请求的 URL
        **kwargs: 其他传递给 httpx.delete 的参数

    返回:
        httpx.Response 对象

    注意:
        此方法使用 httpx 实现，包含自动重试机制，适用于解决"Response ended prematurely"等连接问题
    """
    client = get_httpx_client()
    try:
        response = client.delete(url=url, **kwargs)
        response.raise_for_status()
        return response
    finally:
        client.close()


# 同步流式POST请求方法
def stream_post(
    url: str,
    data: Optional[Any] = None,
    json: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Generator[bytes, None, None]:
    """
    发送流式 POST 请求，使用 httpx 实现，返回标准 Generator

    参数:
        url: 请求的 URL
        data: (可选) 请求体数据 (表单数据或原始数据)
        json: (可选) JSON 数据，会自动设置 Content-Type
        **kwargs: 其他传递给 httpx.post 的参数

    返回:
        Generator[bytes, None, None]: 字节流生成器

    注意:
        此方法使用 httpx 实现流式请求，适用于处理大文件下载或流式响应
    """
    client = get_httpx_client()
    try:
        with client.stream("POST", url, data=data, json=json, **kwargs) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                yield chunk
    finally:
        client.close()
