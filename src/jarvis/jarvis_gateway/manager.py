# -*- coding: utf-8 -*-
"""Gateway 管理器，用于获取/设置当前网关实现。"""

from __future__ import annotations

from threading import RLock
from typing import Optional

from .gateway import IGateway


_current_gateway: Optional[IGateway] = None
_gateway_lock = RLock()


def set_current_gateway(gateway: Optional[IGateway]) -> None:
    """设置当前网关实现（可为 None 表示未启用）。"""
    global _current_gateway
    with _gateway_lock:
        _current_gateway = gateway


def get_current_gateway() -> Optional[IGateway]:
    """获取当前网关实现；若未设置则返回 None。"""
    with _gateway_lock:
        return _current_gateway
