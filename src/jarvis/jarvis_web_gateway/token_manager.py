# -*- coding: utf-8 -*-
"""Token 管理模块。

负责生成和验证 Gateway Token。
Token 在 Web Gateway 启动时生成一次，永久使用。
Token 同时写入文件，供子进程（Agent）跨进程共享。
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional


def generate_gateway_token() -> str:
    """生成 Gateway Token。

    生成一个随机的 UUID 字符串作为 Token。

    Returns:
        Token 字符串
    """
    return str(uuid.uuid4())


def _get_token_file_path() -> Path:
    """获取 Token 文件路径。

    Token 文件存放在 Jarvis 数据目录下，供所有进程共享。

    Returns:
        Token 文件路径
    """
    from jarvis.jarvis_utils.config import get_data_dir

    gateway_dir = Path(get_data_dir()) / "gateway"
    gateway_dir.mkdir(parents=True, exist_ok=True)
    return gateway_dir / ".token"


def save_token_to_file(token: str) -> None:
    """将 Token 写入文件（原子写入）。

    Args:
        token: 要保存的 Token
    """
    token_file = _get_token_file_path()
    try:
        token_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = token_file.with_suffix(".tmp")
        tmp_file.write_text(token)
        tmp_file.replace(token_file)
    except OSError:
        pass


def load_token_from_file() -> Optional[str]:
    """从文件读取 Token。

    Returns:
        Token 字符串，如果文件不存在或读取失败则返回 None
    """
    token_file = _get_token_file_path()
    try:
        if token_file.exists():
            return token_file.read_text().strip()
    except OSError:
        pass
    return None


def validate_gateway_token(token: Optional[str]) -> bool:
    """验证 Gateway Token。

    统一从文件读取 Token，确保所有进程（包括 agent 子进程）
    都能获取最新的 token，避免环境变量在子进程 fork 后不同步的问题。

    Args:
        token: 要验证的 Token

    Returns:
        Token 是否有效
    """
    if not token:
        return False

    # 统一从文件读取 Token（跨进程共享，避免环境变量不同步）
    expected_token = load_token_from_file()

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
