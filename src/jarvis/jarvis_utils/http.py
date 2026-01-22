# -*- coding: utf-8 -*-

from typing import Any
from typing import Dict
from typing import Generator
from typing import Optional

import requests


def get_requests_session() -> requests.Session:
    """
    获取一个配置好的 requests.Session 对象

    返回:
        requests.Session 对象
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        }
    )
    return session


# 增强版本的 HTTP 请求方法（使用 requests 实现）
def post(
    url: str,
    data: Optional[Any] = None,
    json: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> requests.Response:
    """
    发送增强版永不超时的 POST 请求，使用 requests 实现

    参数:
        url: 请求的 URL
        data: (可选) 请求体数据 (表单数据或原始数据)
        json: (可选) JSON 数据，会自动设置 Content-Type
        **kwargs: 其他传递给 requests.post 的参数

    返回:
        requests.Response 对象

    注意:
        此方法使用 requests 实现。要实现重试，请考虑使用 Session 和 HTTPAdapter。
        永不超时通过 timeout=None 设置。
    """
    kwargs.setdefault("timeout", None)
    with get_requests_session() as session:
        response = session.post(url=url, data=data, json=json, **kwargs)
        response.raise_for_status()
        return response


def get(url: str, **kwargs: Any) -> requests.Response:
    """
    发送增强版永不超时的 GET 请求，使用 requests 实现

    参数:
        url: 请求的 URL
        **kwargs: 其他传递给 requests.get 的参数

    返回:
        requests.Response 对象

    注意:
        此方法使用 requests 实现。
        永不超时通过 timeout=None 设置。
    """
    kwargs.setdefault("timeout", None)
    with get_requests_session() as session:
        response = session.get(url=url, **kwargs)
        response.raise_for_status()
        return response


def put(url: str, data: Optional[Any] = None, **kwargs: Any) -> requests.Response:
    """
    发送增强版永不超时的 PUT 请求，使用 requests 实现

    参数:
        url: 请求的 URL
        data: (可选) 请求体数据 (表单数据或原始数据)
        **kwargs: 其他传递给 requests.put 的参数

    返回:
        requests.Response 对象

    注意:
        此方法使用 requests 实现。
        永不超时通过 timeout=None 设置。
    """
    kwargs.setdefault("timeout", None)
    with get_requests_session() as session:
        response = session.put(url=url, data=data, **kwargs)
        response.raise_for_status()
        return response


def delete(url: str, **kwargs: Any) -> requests.Response:
    """
    发送增强版永不超时的 DELETE 请求，使用 requests 实现

    参数:
        url: 请求的 URL
        **kwargs: 其他传递给 requests.delete 的参数

    返回:
        requests.Response 对象

    注意:
        此方法使用 requests 实现。
        永不超时通过 timeout=None 设置。
    """
    kwargs.setdefault("timeout", None)
    with get_requests_session() as session:
        response = session.delete(url=url, **kwargs)
        response.raise_for_status()
        return response


# 同步流式POST请求方法
def stream_post(
    url: str,
    data: Optional[Any] = None,
    json: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Generator[str, None, None]:
    """
    发送流式 POST 请求，使用 requests 实现，返回解码后的字符串行生成器

    参数:
        url: 请求的 URL
        data: (可选) 请求体数据 (表单数据或原始数据)
        json: (可选) JSON 数据，会自动设置 Content-Type
        **kwargs: 其他传递给 requests.post 的参数

    返回:
        Generator[str, None, None]: 字符串行生成器

    注意:
        此方法使用 requests 实现流式请求，适用于处理大文件下载或流式响应
    """
    kwargs.setdefault("timeout", None)
    with get_requests_session() as session:
        with session.post(url, data=data, json=json, stream=True, **kwargs) as response:
            response.raise_for_status()
            for line in response.iter_lines(chunk_size=1):
                if line:
                    yield line.decode("utf-8", errors="ignore")
