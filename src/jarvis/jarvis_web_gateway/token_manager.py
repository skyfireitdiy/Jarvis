# -*- coding: utf-8 -*-
"""Token 管理模块。

负责生成和验证 Gateway Token。
Token 在 Web Gateway 启动时生成一次，永久使用。
"""

from __future__ import annotations

import os
import uuid
from typing import Optional


def generate_gateway_token() -> str:
    """生成 Gateway Token。

    生成一个随机的 UUID 字符串作为 Token。

    Returns:
        Token 字符串
    """
    return str(uuid.uuid4())


def validate_gateway_token(token: Optional[str]) -> bool:
    """验证 Gateway Token。

    Args:
        token: 要验证的 Token

    Returns:
        Token 是否有效
    """
    if not token:
        return False

    # 统一从环境变量读取 Token（Web Gateway 和 Agent Gateway 共用）
    expected_token = os.environ.get("JARVIS_AUTH_TOKEN")

    if not expected_token:
        return False

    return token == expected_token


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
