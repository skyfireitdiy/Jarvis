"""LSP 语言服务器注册表（从全局配置读取）。

本模块把 ``~/.jarvis/config.yaml`` 的 ``lsp.languages`` 配置转换为 Web 网关
所需的 spec 结构，供 ``app.py``（``GET /api/lsp/servers``、``WS /api/lsp/{id}``）
与 ``lsp_bridge.py``（进程池）使用。

配置来源唯一：``jarvis.jarvis_lsp.config.LSPConfigReader``（与 jarvis-lsp 共用）。
新增语言只需在 ``~/.jarvis/config.yaml`` 的 ``lsp.languages`` 下增加一项，
无需修改任何代码。

spec 字段（由 LanguageConfig 转换而来）：

    id                      str        语言名，如 "python"（即 config 的 key）
    monacoLanguage          str        对应 Monaco 语言 id
    command                 list[str]  ``[command] + args``，供 create_subprocess_exec
    extensions              list[str]  文件扩展名
    args                    list[str]  启动参数
    rootMarkers             list[str]  workspace 根标记文件
    initializationOptions   dict       传给 initialize 的选项
    installHint             str        未安装时的提示文案
    _source                 str        固定为 "config"，标记来源
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _to_spec(language: str, cfg: Any) -> Dict[str, Any]:
    """把 LanguageConfig 转换为 Web 网关使用的 spec 字典。"""
    args = list(cfg.args or [])
    command = [cfg.command] + args
    return {
        "id": language,
        "monacoLanguage": cfg.monaco_language or language,
        "command": command,
        "args": args,
        "extensions": list(cfg.file_extensions or []),
        "rootMarkers": list(cfg.root_markers or []),
        "initializationOptions": dict(cfg.initialization_options or {}),
        "installHint": cfg.install_hint or "",
        "_source": "config",
    }


def load_lsp_server_specs() -> Dict[str, Dict[str, Any]]:
    """加载全部 LSP 语言服务器配置。

    Returns:
        ``{server_id: spec}``；配置读取失败时返回空 dict（不抛异常）。
    """
    try:
        from jarvis.jarvis_lsp.config import LSPConfigReader

        config = LSPConfigReader().load_config()
    except Exception as e:  # pragma: no cover - 环境异常兜底
        logger.warning("[lsp_registry] 读取 LSP 配置失败，返回空配置: %s", e)
        return {}

    specs: Dict[str, Dict[str, Any]] = {}
    for language, cfg in config.languages.items():
        if not cfg.command:
            logger.warning("[lsp_registry] 语言 %s 缺少 command，已跳过", language)
            continue
        specs[language] = _to_spec(language, cfg)
    return specs


def get_lsp_server_spec(server_id: str) -> Optional[Dict[str, Any]]:
    """按 id 获取单个语言服务器配置。

    Args:
        server_id: 语言名，如 "python"。

    Returns:
        spec 字典；不存在返回 None。
    """
    if not isinstance(server_id, str) or not server_id.strip():
        return None
    return load_lsp_server_specs().get(server_id.strip())


def list_lsp_server_ids() -> List[str]:
    """返回全部已注册的 server id（排序后）。"""
    return sorted(load_lsp_server_specs().keys())
