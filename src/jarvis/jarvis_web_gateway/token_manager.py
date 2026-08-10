# -*- coding: utf-8 -*-
"""Token 管理模块。

负责生成和验证 Gateway Token。
Token 在 Web Gateway 启动时生成一次，永久使用。
支持JWT Token验证，回退旧UUID Token。
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, Optional


def generate_gateway_token() -> str:
    """生成 Gateway Token。

    生成一个随机的 UUID 字符串作为 Token。

    Returns:
        Token 字符串
    """
    return str(uuid.uuid4())


def validate_gateway_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """验证 Gateway Token，优先JWT验证，回退环境变量比对。

    Args:
        token: 要验证的 Token

    Returns:
        验证成功返回用户信息dict，失败返回None
    """
    if not token:
        return None

    # 优先JWT验证
    try:
        from .jwt_utils import validate_jwt_token

        payload = validate_jwt_token(token)
        if payload:
            return payload
    except ImportError:
        pass

    # 回退：环境变量比对（CLI Gateway用）
    expected_token = os.environ.get("JARVIS_AUTH_TOKEN")
    if expected_token and token == expected_token:
        return {"user_id": "system", "username": "gateway", "is_admin": True}

    return None


def validate_token_with_user(token: str) -> Optional[Dict[str, Any]]:
    """验证Token并返回用户信息，用于HTTP API认证。

    Args:
        token: 要验证的 Token

    Returns:
        验证成功返回用户信息dict，失败返回None
    """
    # 优先JWT验证
    try:
        from .jwt_utils import validate_jwt_token

        payload = validate_jwt_token(token)
        if payload:
            return payload
    except ImportError:
        pass

    # 回退旧Token
    env_token = os.environ.get("JARVIS_AUTH_TOKEN")
    if env_token and token == env_token:
        return {"user_id": "system", "username": "gateway", "is_admin": True}

    return None


def extract_token_from_authorization_header(
    authorization: Optional[str],
) -> Optional[str]:
    """从 Authorization Header 提取 Token。

    Args:
        authorization: Authorization Header 值，格式为 "Bearer <token>"

    Returns:
        Token 字符串，如果格式不正确则返回 None
    """
    if not authorization:
        return None

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return parts[1]
