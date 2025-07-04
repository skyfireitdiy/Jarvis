# -*- coding: utf-8 -*-
"""
HTTP 工具模块
提供永不超时的 HTTP 请求封装，所有请求方法均为永不超时
"""

import requests
from requests.adapters import HTTPAdapter
from typing import Any, Dict, Optional, Union


class NoTimeoutHTTPAdapter(HTTPAdapter):
    """
    永不超时的 HTTP 适配器
    """

    def send(self, request, **kwargs):
        """
        发送请求时强制设置超时为 None（永不超时）

        参数:
            request: 请求对象
            **kwargs: 其他参数

        返回:
            响应对象
        """
        # 强制设置超时为 None（永不超时）
        kwargs["timeout"] = None
        return super().send(request, **kwargs)


def get_no_timeout_session() -> requests.Session:
    """
    获取配置了永不超时适配器的 Session 对象

    返回:
        配置了永不超时的 requests.Session 对象
    """
    session = requests.Session()
    adapter = NoTimeoutHTTPAdapter()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


# 永不超时的 HTTP 请求方法
def post(
    url: str,
    data: Optional[Union[Dict[str, Any], str, bytes]] = None,
    json: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> requests.Response:
    """
    发送永不超时的 POST 请求

    参数:
        url: 请求的 URL
        data: (可选) 请求体数据 (表单数据或原始数据)
        json: (可选) JSON 数据，会自动设置 Content-Type
        **kwargs: 其他传递给 requests.post 的参数

    返回:
        requests.Response 对象

    注意:
        此方法使用永不超时设置，适用于需要长时间处理的POST操作
    """
    session = get_no_timeout_session()
    return session.post(url=url, data=data, json=json, **kwargs)


def put(
    url: str, data: Optional[Union[Dict[str, Any], str, bytes]] = None, **kwargs
) -> requests.Response:
    """
    发送永不超时的 PUT 请求

    参数:
        url: 请求的 URL
        data: (可选) 请求体数据 (表单数据或原始数据)
        **kwargs: 其他传递给 requests.put 的参数

    返回:
        requests.Response 对象

    注意:
        此方法使用永不超时设置，适用于需要长时间处理的PUT操作
    """
    session = get_no_timeout_session()
    return session.put(url=url, data=data, **kwargs)


def get(url: str, **kwargs) -> requests.Response:
    """
    发送永不超时的 GET 请求（读取数据）

    参数:
        url: 请求的 URL
        **kwargs: 其他传递给 requests.get 的参数

    返回:
        requests.Response 对象

    注意:
        此方法使用永不超时设置，适用于需要长时间等待的读取操作
    """
    session = get_no_timeout_session()
    return session.get(url=url, **kwargs)


def delete(url: str, **kwargs) -> requests.Response:
    """
    发送永不超时的 DELETE 请求

    参数:
        url: 请求的 URL
        **kwargs: 其他传递给 requests.delete 的参数

    返回:
        requests.Response 对象

    注意:
        此方法使用永不超时设置，适用于需要长时间处理的DELETE操作
    """
    session = get_no_timeout_session()
    return session.delete(url=url, **kwargs)
