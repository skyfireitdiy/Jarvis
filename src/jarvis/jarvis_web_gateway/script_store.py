"""浏览器扩展脚本的文件存取。

用途：让 Agent 把扩展里的用户脚本导出到网关数据目录，或从该目录读取脚本内容
再安装回扩展，避免在对话中传输大段脚本原文。

目录约定：``{get_data_dir()}/browser_scripts/{name}.js``

安全约定：脚本名只允许安全字符，最终路径必须落在 ``browser_scripts`` 目录内，
防止目录穿越（``../``、绝对路径等）。
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

# 脚本名允许的字符集：字母、数字、下划线、中划线、点
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

# 脚本文件扩展名
_SCRIPT_EXT = ".js"

# browser_scripts 子目录名
_SCRIPTS_DIR_NAME = "browser_scripts"


class ScriptStoreError(Exception):
    """脚本存取相关的错误（名称非法、路径越界、文件不存在等）。"""


def _get_scripts_dir() -> str:
    """返回脚本存放目录（绝对路径），不存在时自动创建。"""
    # 延迟导入，避免模块级循环依赖
    from jarvis.jarvis_utils.config import get_data_dir

    scripts_dir = os.path.join(get_data_dir(), _SCRIPTS_DIR_NAME)
    os.makedirs(scripts_dir, exist_ok=True)
    return os.path.realpath(scripts_dir)


def sanitize_script_name(name: Any) -> str:
    """校验并规范化脚本名，返回不含扩展名的安全名称。

    规则：
    - 必须是非空字符串；
    - 只允许 ``[A-Za-z0-9_.-]``；
    - 拒绝 ``.``、``..``、以 ``.`` 开头的隐藏名；
    - 拒绝含路径分隔符或 ``..`` 子串的名称；
    - 末尾的 ``.js`` 会被去掉，避免出现 ``a.js.js``。

    Args:
        name: 原始脚本名（可带 ``.js`` 后缀）

    Returns:
        str: 规范化后的安全名称（不含扩展名）

    Raises:
        ScriptStoreError: 名称非法时抛出
    """
    if not isinstance(name, str):
        raise ScriptStoreError("name must be a string")
    raw = name.strip()
    if not raw:
        raise ScriptStoreError("name is required")
    # 去掉一次尾部 .js（大小写不敏感），避免 a.js.js
    if raw.lower().endswith(_SCRIPT_EXT):
        raw = raw[: -len(_SCRIPT_EXT)].strip()
    if not raw:
        raise ScriptStoreError("name is required")
    if raw in (".", ".."):
        raise ScriptStoreError(f"invalid script name: {name}")
    if "/" in raw or "\\" in raw:
        raise ScriptStoreError(f"invalid script name: {name}")
    if ".." in raw:
        raise ScriptStoreError(f"invalid script name: {name}")
    if raw.startswith("."):
        raise ScriptStoreError(f"invalid script name: {name}")
    if not _SAFE_NAME_RE.match(raw):
        raise ScriptStoreError(f"invalid script name: {name}")
    return raw


def resolve_script_path(name: Any) -> str:
    """把脚本名解析为绝对文件路径，并校验其位于脚本目录内。

    Args:
        name: 脚本名（可带 ``.js`` 后缀）

    Returns:
        str: 脚本文件的绝对路径

    Raises:
        ScriptStoreError: 名称非法或路径越界时抛出
    """
    safe_name = sanitize_script_name(name)
    scripts_dir = _get_scripts_dir()
    candidate = os.path.realpath(os.path.join(scripts_dir, safe_name + _SCRIPT_EXT))
    # 二次确认：解析后的路径必须仍在脚本目录内
    if os.path.dirname(candidate) != scripts_dir:
        raise ScriptStoreError(f"path escapes scripts dir: {name}")
    if not candidate.startswith(scripts_dir + os.sep):
        raise ScriptStoreError(f"path escapes scripts dir: {name}")
    return candidate


def save_script(name: Any, content: Any) -> Dict[str, Any]:
    """把脚本内容写入脚本目录（同名覆盖）。

    Args:
        name: 脚本名
        content: 脚本源码

    Returns:
        Dict[str, Any]: ``{"name": str, "path": str, "size": int}``

    Raises:
        ScriptStoreError: 名称非法或内容非字符串时抛出
    """
    if not isinstance(content, str):
        raise ScriptStoreError("content must be a string")
    if not content.strip():
        raise ScriptStoreError("content is required")
    path = resolve_script_path(name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return {
        "name": sanitize_script_name(name),
        "path": path,
        "size": len(content.encode("utf-8")),
    }


def load_script(name: Any) -> Dict[str, Any]:
    """读取脚本内容。

    Args:
        name: 脚本名

    Returns:
        Dict[str, Any]: ``{"name": str, "content": str, "size": int}``

    Raises:
        ScriptStoreError: 名称非法或文件不存在时抛出
    """
    path = resolve_script_path(name)
    if not os.path.isfile(path):
        raise ScriptStoreError(f"script not found: {sanitize_script_name(name)}")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return {
        "name": sanitize_script_name(name),
        "content": content,
        "size": len(content.encode("utf-8")),
    }


def list_scripts() -> List[Dict[str, Any]]:
    """列出脚本目录下所有脚本，按修改时间倒序。

    Returns:
        List[Dict[str, Any]]: 每项为 ``{"name", "size", "updated_at"}``
    """
    scripts_dir = _get_scripts_dir()
    items: List[Dict[str, Any]] = []
    try:
        entries = os.listdir(scripts_dir)
    except OSError:
        return items
    for entry in entries:
        if not entry.lower().endswith(_SCRIPT_EXT):
            continue
        full = os.path.join(scripts_dir, entry)
        if not os.path.isfile(full):
            continue
        try:
            stat = os.stat(full)
        except OSError:
            continue
        items.append(
            {
                "name": entry[: -len(_SCRIPT_EXT)],
                "size": stat.st_size,
                "updated_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        )
    items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return items
