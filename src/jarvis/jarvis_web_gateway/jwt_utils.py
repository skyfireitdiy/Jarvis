# -*- coding: utf-8 -*-
"""JWT Token 管理模块。

负责 JWT Token 的签发、验证和黑名单管理。
支持多用户认证体系，替代原有的单 Token 模式。
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Optional

import jwt

# JWT 签名密钥：优先从环境变量读取，未设置则随机生成（重启失效）
_jwt_secret: str = os.environ.get("JARVIS_JWT_SECRET", "")

if not _jwt_secret:
    _jwt_secret = uuid.uuid4().hex + uuid.uuid4().hex

# Token 有效期（小时）
_jwt_expire_hours: int = int(os.environ.get("JARVIS_JWT_EXPIRE_HOURS", "24"))

# Token 黑名单：{jti: exp_timestamp}
_revoked_tokens: dict[str, float] = {}


def generate_jwt_token(user_id: str, username: str, is_admin: bool) -> str:
    """生成 JWT Token。

    Args:
        user_id: 用户唯一标识
        username: 用户名
        is_admin: 是否管理员

    Returns:
        JWT Token 字符串
    """
    now = time.time()
    payload = {
        "user_id": user_id,
        "username": username,
        "is_admin": is_admin,
        "iat": int(now),
        "exp": int(now) + _jwt_expire_hours * 3600,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _jwt_secret, algorithm="HS256")


def validate_jwt_token(token: str) -> Optional[dict]:
    """验证 JWT Token。

    验证签名和有效期，并检查 Token 是否在黑名单中。

    Args:
        token: JWT Token 字符串

    Returns:
        验证成功返回 payload 字典，失败返回 None
    """
    try:
        payload = jwt.decode(token, _jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

    # 检查黑名单
    jti = payload.get("jti", "")
    if jti and jti in _revoked_tokens:
        return None

    return payload


def revoke_token(token: str) -> None:
    """将 Token 加入黑名单。

    将 Token 的 jti 加入黑名单，过期后由 cleanup_revoked_tokens 清理。

    Args:
        token: JWT Token 字符串
    """
    try:
        # 不验证过期时间，仅解码获取 jti 和 exp
        payload = jwt.decode(
            token, _jwt_secret, algorithms=["HS256"], options={"verify_exp": False}
        )
        jti = payload.get("jti", "")
        exp = payload.get("exp", 0)
        if jti:
            _revoked_tokens[jti] = float(exp)
    except jwt.InvalidTokenError:
        pass


def cleanup_revoked_tokens() -> None:
    """清理黑名单中已过期的条目。"""
    now = time.time()
    expired_jtis = [jti for jti, exp in _revoked_tokens.items() if exp < now]
    for jti in expired_jtis:
        del _revoked_tokens[jti]
