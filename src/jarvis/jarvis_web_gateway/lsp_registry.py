"""LSP 语言服务器清单注册表。

本模块实现"丢清单即扩展"的 LSP 语言支持机制：新增一种语言只需在清单目录里
放入一个 JSON 文件，无需修改任何核心代码。

清单扫描目录（后者覆盖前者，按 ``id`` 去重）：
    1. 内置目录：``<本文件所在目录>/lsp_servers/``（随代码分发，开箱即用）
    2. 用户目录：``{get_data_dir()}/lsp_servers/``（用户自行扩展，同名 id 覆盖内置）

清单 schema（JSON 字段）：
    id                   str        唯一标识，如 "python"（必填）
    monacoLanguage       str        对应 Monaco 语言 id，如 "python"（必填）
    extensions           list[str]  文件扩展名，如 [".py", ".pyi"]
    command              list[str]  启动命令，如 ["pylsp"]（必填，必须是列表，
                                    禁止字符串以避免 shell 解析）
    args                 list[str]  附加参数，可选
    rootMarkers          list[str]  用于确定 workspace root 的标记文件，可选
    initializationOptions dict      传给 initialize 的初始化选项，可选
    installHint          str        服务器未安装时的提示文案，可选

加载后的 spec 会额外带一个 ``_source`` 字段，取值为 ``"builtin"`` 或 ``"user"``，
用于区分清单来源（便于前端展示与调试）。

容错策略：任何非法 JSON、缺必填字段、字段类型错误的清单都会被跳过并记录
``logging.warning``，绝不抛出异常中断整体加载。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 内置清单目录：与本模块同级的 lsp_servers/
_BUILTIN_DIR = Path(__file__).resolve().parent / "lsp_servers"

# 清单必填字段及其期望类型
_REQUIRED_STR_FIELDS = ("id", "monacoLanguage")
_REQUIRED_LIST_FIELDS = ("command",)
_OPTIONAL_LIST_FIELDS = ("extensions", "args", "rootMarkers")


def _get_user_dir() -> Optional[Path]:
    """获取用户清单目录 ``{get_data_dir()}/lsp_servers``。

    数据目录获取失败时返回 None（不抛异常），调用方需容忍。
    """
    try:
        from jarvis.jarvis_utils.config import get_data_dir

        return Path(str(get_data_dir())) / "lsp_servers"
    except Exception as e:  # pragma: no cover - 环境异常兜底
        logger.warning("[lsp_registry] 无法获取数据目录，跳过用户清单目录: %s", e)
        return None


def _validate_and_normalize(
    raw: Any, source: str, origin: Path
) -> Optional[Dict[str, Any]]:
    """校验并规范化单条清单。

    Args:
        raw: JSON 解析后的原始对象
        source: "builtin" 或 "user"
        origin: 清单文件路径（用于日志）

    Returns:
        规范化后的 spec；校验失败返回 None
    """
    if not isinstance(raw, dict):
        logger.warning("[lsp_registry] 清单不是 JSON 对象，已跳过: %s", origin)
        return None

    spec: Dict[str, Any] = dict(raw)

    # 必填字符串字段
    for field in _REQUIRED_STR_FIELDS:
        value = spec.get(field)
        if not isinstance(value, str) or not value.strip():
            logger.warning(
                "[lsp_registry] 清单缺少必填字段 %s（或类型错误），已跳过: %s",
                field,
                origin,
            )
            return None
        spec[field] = value.strip()

    # 必填列表字段（command 必须是列表，禁止字符串）
    for field in _REQUIRED_LIST_FIELDS:
        value = spec.get(field)
        if not isinstance(value, list) or not value:
            logger.warning(
                "[lsp_registry] 清单字段 %s 必须是非空列表，已跳过: %s", field, origin
            )
            return None
        if not all(isinstance(item, str) for item in value):
            logger.warning(
                "[lsp_registry] 清单字段 %s 的元素必须都是字符串，已跳过: %s",
                field,
                origin,
            )
            return None
        spec[field] = list(value)

    # 可选列表字段：类型不对则丢弃该字段（不整条跳过）
    for field in _OPTIONAL_LIST_FIELDS:
        if field in spec:
            value = spec[field]
            if isinstance(value, list) and all(isinstance(i, str) for i in value):
                spec[field] = list(value)
            else:
                logger.warning(
                    "[lsp_registry] 清单可选字段 %s 类型不合法，已忽略该字段: %s",
                    field,
                    origin,
                )
                spec.pop(field, None)

    # 可选字段默认值
    spec.setdefault("extensions", [])
    spec.setdefault("args", [])
    spec.setdefault("rootMarkers", [])
    if not isinstance(spec.get("initializationOptions"), dict):
        spec["initializationOptions"] = {}
    if not isinstance(spec.get("installHint"), str):
        spec["installHint"] = ""

    spec["_source"] = source
    return spec


def _scan_dir(directory: Optional[Path], source: str) -> Dict[str, Dict[str, Any]]:
    """扫描单个目录下的全部 *.json 清单。

    目录不存在或不可读时返回空 dict，不抛异常。
    """
    result: Dict[str, Dict[str, Any]] = {}
    if directory is None or not directory.is_dir():
        return result

    for path in sorted(directory.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except json.JSONDecodeError as e:
            logger.warning("[lsp_registry] 清单 JSON 解析失败，已跳过 %s: %s", path, e)
            continue
        except OSError as e:
            logger.warning("[lsp_registry] 清单文件读取失败，已跳过 %s: %s", path, e)
            continue

        spec = _validate_and_normalize(raw, source, path)
        if spec is None:
            continue

        server_id = spec["id"]
        if server_id in result:
            logger.warning(
                "[lsp_registry] 同一目录内 id 重复 (%s)，后者覆盖前者: %s",
                server_id,
                path,
            )
        result[server_id] = spec

    return result


def load_lsp_server_specs() -> Dict[str, Dict[str, Any]]:
    """加载全部 LSP 语言服务器清单。

    先加载内置目录，再用用户目录覆盖（按 ``id`` 去重，用户优先）。

    Returns:
        ``{server_id: spec}``；无任何清单时返回空 dict（不报错）。
        每个 spec 含 ``_source`` 字段标记来源。
    """
    specs = _scan_dir(_BUILTIN_DIR, "builtin")
    user_specs = _scan_dir(_get_user_dir(), "user")

    for server_id, spec in user_specs.items():
        if server_id in specs:
            logger.info("[lsp_registry] 用户清单覆盖内置清单: %s", server_id)
        specs[server_id] = spec

    return specs


def get_lsp_server_spec(server_id: str) -> Optional[Dict[str, Any]]:
    """按 id 获取单个清单。

    Args:
        server_id: 清单 id，如 "python"

    Returns:
        spec 字典；不存在返回 None。
    """
    if not isinstance(server_id, str):
        return None
    return load_lsp_server_specs().get(server_id)


def list_lsp_server_ids() -> List[str]:
    """返回全部已注册的 server id（排序后）。"""
    return sorted(load_lsp_server_specs().keys())
