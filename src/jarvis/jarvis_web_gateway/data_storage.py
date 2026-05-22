"""
数据存储模块

提供统一的 Key-Value 存储功能，支持 Agent 网关的数据持久化需求。
"""

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

from jarvis.jarvis_utils.config import get_data_dir


# Key 值正则表达式：仅允许字母、数字、下划线、短横线
KEY_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _get_storage_dir() -> Path:
    """
    获取数据存储目录路径。

    返回:
        Path: 存储目录路径
    """
    storage_dir = Path(get_data_dir()) / "data_store"
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


def _validate_key(key: str) -> tuple[bool, Optional[str]]:
    """
    验证 Key 值格式。

    参数:
        key: 要验证的 Key 值

    返回:
        tuple[bool, Optional[str]]: (是否有效, 错误信息)
    """
    if not key:
        return False, "Key cannot be empty"

    if not KEY_PATTERN.match(key):
        return (
            False,
            "Key contains invalid characters. Only alphanumeric, underscore, and hyphen are allowed.",
        )

    return True, None


def _get_file_path(key: str) -> Path:
    """
    获取 Key 对应的文件路径。

    参数:
        key: 数据 Key

    返回:
        Path: 文件路径
    """
    return _get_storage_dir() / f"{key}.json"


def save_data(key: str, value: Any) -> tuple[bool, Optional[str]]:
    """
    保存数据到存储。

    参数:
        key: 数据 Key
        value: 要存储的值（必须是 JSON 可序列化的）

    返回:
        tuple[bool, Optional[str]]: (是否成功, 错误信息)
    """
    # 验证 Key
    is_valid, error = _validate_key(key)
    if not is_valid:
        return False, error

    try:
        file_path = _get_file_path(key)

        # 使用原子写入：先写入临时文件，再重命名
        temp_fd, temp_path = tempfile.mkstemp(dir=file_path.parent, suffix=".tmp")
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(value, f, ensure_ascii=False, indent=2)

            # 原子重命名
            os.replace(temp_path, file_path)
            return True, None
        except Exception as e:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise e
    except Exception as e:
        return False, f"Failed to save data: {str(e)}"


def load_data(key: str) -> tuple[bool, Any, Optional[str]]:
    """
    从存储中读取数据。

    参数:
        key: 数据 Key

    返回:
        tuple[bool, Any, Optional[str]]: (是否成功, 数据值, 错误信息)
    """
    # 验证 Key
    is_valid, error = _validate_key(key)
    if not is_valid:
        return False, None, error

    try:
        file_path = _get_file_path(key)

        if not file_path.exists():
            return False, None, "Key not found"

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return True, data, None
    except json.JSONDecodeError as e:
        return False, None, f"Invalid JSON format: {str(e)}"
    except Exception as e:
        return False, None, f"Failed to load data: {str(e)}"


def delete_data(key: str) -> tuple[bool, Optional[str]]:
    """
    从存储中删除数据。

    参数:
        key: 数据 Key

    返回:
        tuple[bool, Optional[str]]: (是否成功, 错误信息)
    """
    # 验证 Key
    is_valid, error = _validate_key(key)
    if not is_valid:
        return False, error

    try:
        file_path = _get_file_path(key)

        if not file_path.exists():
            return False, "Key not found"

        file_path.unlink()
        return True, None
    except Exception as e:
        return False, f"Failed to delete data: {str(e)}"
