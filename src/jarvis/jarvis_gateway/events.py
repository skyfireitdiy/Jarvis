# -*- coding: utf-8 -*-
"""Gateway 事件模型定义。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Dict
from typing import Optional


@dataclass(frozen=True)
class GatewayOutputEvent:
    """统一输出事件。"""

    text: str
    output_type: str
    timestamp: Optional[str] = None  # ISO格式时间字符串，如 '2026-07-30T15:08:52'
    lang: Optional[str] = None
    traceback: bool = False
    section: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class GatewayInputRequest:
    """统一输入请求。"""

    tip: str
    mode: Optional[str] = None  # 'single' or 'multi'
    preset: Optional[str] = None
    preset_cursor: Optional[int] = None
    is_password: bool = False
    metadata: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class GatewayInputResult:
    """统一输入结果。"""

    text: str
    metadata: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class GatewayConfirmRequest:
    """确认请求。"""

    message: str
    default: bool = True
    metadata: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class GatewayConfirmResult:
    """确认结果。"""

    confirmed: bool
    metadata: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class GatewayExecutionEvent:
    """统一执行事件。"""

    event_type: str
    payload: Dict[str, Any]
    timestamp: Optional[str] = None
