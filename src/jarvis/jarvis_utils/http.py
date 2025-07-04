# -*- coding: utf-8 -*-
"""
HTTP 工具模块
提供永不超时的 HTTP 请求封装，所有请求方法均为永不超时

功能特性:
1. 基础永不超时方法: post(), get(), put(), delete()
2. 增强版方法: post_enhanced(), get_enhanced(), put_enhanced(), delete_enhanced()
   - 包含自动重试机制
   - TCP Keep-Alive 优化
   - 解决 "Response ended prematurely" 等连接问题

使用建议:
- 对于稳定的网络环境，使用基础方法即可
- 对于不稳定的网络或遇到连接中断问题，使用增强版方法
"""

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError, ChunkedEncodingError, ReadTimeout
from typing import Any, Dict, Optional, Union
import time
import socket


class EnhancedNoTimeoutHTTPAdapter(HTTPAdapter):
    """
    增强的永不超时 HTTP 适配器，解决连接中断问题
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        """初始化连接池管理器，优化连接设置"""
        # 完全重写以避免参数冲突
        # 首先调用父类方法获取基础配置
        super().init_poolmanager(*args, **kwargs)

        # 然后尝试优化连接池设置
        try:
            if hasattr(self.poolmanager, "connection_pool_kw"):
                # 直接设置连接池参数
                pool_kw = getattr(self.poolmanager, "connection_pool_kw", {})
                pool_kw.update(
                    {
                        "maxsize": 100,
                        "block": False,
                    }
                )

                # 尝试添加socket选项
                try:
                    socket_options = [
                        (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
                    ]
                    # 在Linux系统上添加更多keep-alive参数
                    if hasattr(socket, "TCP_KEEPIDLE"):
                        socket_options.extend(
                            [
                                (socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60),
                                (socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10),
                                (socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 6),
                            ]
                        )
                    pool_kw["socket_options"] = socket_options
                except (AttributeError, OSError):
                    pass
        except (AttributeError, TypeError):
            # 如果无法设置，则忽略
            pass

    def send(self, request, **kwargs):
        """
        发送请求时强制设置超时为 None（永不超时）并增加重试机制

        参数:
            request: 请求对象
            **kwargs: 其他参数

        返回:
            响应对象
        """
        # 强制设置超时为 None（永不超时）
        kwargs["timeout"] = None

        max_attempts = 3  # 最大尝试次数
        last_exception = None

        for attempt in range(max_attempts):
            try:
                return super().send(request, **kwargs)
            except (ConnectionError, ChunkedEncodingError, ReadTimeout) as e:
                last_exception = e
                if attempt < max_attempts - 1:
                    # 指数退避重试
                    wait_time = (2**attempt) * 1
                    print(
                        f"⚠️ 请求失败，{wait_time}秒后重试... (尝试 {attempt + 1}/{max_attempts}): {str(e)}"
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    # 最后一次尝试失败，抛出异常
                    raise e
            except Exception as e:
                # 对于其他类型的异常，直接抛出
                raise e

        # 如果所有尝试都失败了，抛出最后一个异常
        if last_exception:
            raise last_exception


def get_enhanced_no_timeout_session() -> requests.Session:
    """
    获取配置了增强永不超时适配器的 Session 对象
    该版本包含重试机制和连接优化，可以解决"Response ended prematurely"等问题

    返回:
        配置了增强永不超时适配器的 requests.Session 对象
    """
    session = requests.Session()
    adapter = EnhancedNoTimeoutHTTPAdapter()
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # 设置默认请求头以优化连接
    session.headers.update(
        {"Connection": "keep-alive", "User-Agent": "Enhanced-HTTP-Client/1.0"}
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
    session = get_enhanced_no_timeout_session()
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
    session = get_enhanced_no_timeout_session()
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
    session = get_enhanced_no_timeout_session()
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
    session = get_enhanced_no_timeout_session()
    return session.delete(url=url, **kwargs)
