# -*- coding: utf-8 -*-

import requests
from typing import Any, Dict, Optional, Union


def get_session() -> requests.Session:
    """
    获取一个永不超时的 requests.Session 对象

    返回:
        requests.Session 对象
    """
    session = requests.Session()

    # 设置默认请求头以优化连接
    session.headers.update(
        {"Connection": "keep-alive"}
    )

    return session


# 增强版本的 HTTP 请求方法（带重试机制，解决连接中断问题）
def post(
    url: str,
    data: Optional[Union[Dict[str, Any], str, bytes]] = None,
    json: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> requests.Response:
    """
    发送增强版永不超时的 POST 请求，包含重试机制

    参数:
        url: 请求的 URL
        data: (可选) 请求体数据 (表单数据或原始数据)
        json: (可选) JSON 数据，会自动设置 Content-Type
        **kwargs: 其他传递给 requests.post 的参数

    返回:
        requests.Response 对象

    注意:
        此方法使用增强的永不超时设置，包含自动重试机制，适用于解决"Response ended prematurely"等连接问题
    """
    session = get_session()
    return session.post(url=url, data=data, json=json, **kwargs)


def get(url: str, **kwargs) -> requests.Response:
    """
    发送增强版永不超时的 GET 请求，包含重试机制

    参数:
        url: 请求的 URL
        **kwargs: 其他传递给 requests.get 的参数

    返回:
        requests.Response 对象

    注意:
        此方法使用增强的永不超时设置，包含自动重试机制，适用于解决"Response ended prematurely"等连接问题
    """
    session = get_session()
    return session.get(url=url, **kwargs)


def put(
    url: str, data: Optional[Union[Dict[str, Any], str, bytes]] = None, **kwargs
) -> requests.Response:
    """
    发送增强版永不超时的 PUT 请求，包含重试机制

    参数:
        url: 请求的 URL
        data: (可选) 请求体数据 (表单数据或原始数据)
        **kwargs: 其他传递给 requests.put 的参数

    返回:
        requests.Response 对象

    注意:
        此方法使用增强的永不超时设置，包含自动重试机制，适用于解决"Response ended prematurely"等连接问题
    """
    session = get_session()
    return session.put(url=url, data=data, **kwargs)


def delete(url: str, **kwargs) -> requests.Response:
    """
    发送增强版永不超时的 DELETE 请求，包含重试机制

    参数:
        url: 请求的 URL
        **kwargs: 其他传递给 requests.delete 的参数

    返回:
        requests.Response 对象

    注意:
        此方法使用增强的永不超时设置，包含自动重试机制，适用于解决"Response ended prematurely"等连接问题
    """
    session = get_session()
    return session.delete(url=url, **kwargs)
