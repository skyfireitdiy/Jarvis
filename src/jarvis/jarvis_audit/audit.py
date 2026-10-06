# -*- coding: utf-8 -*-
"""
审计日志模块（jarvis_audit.audit）

提供可配置、默认关闭的审计日志能力：记录 Agent 关键行为事件
（用户输入、工具调用、任务完成等）到按天分文件的 JSONL 审计日志，
供安全审查与行为追踪。

设计要点：
- 默认关闭：log_event 内部先检查 is_enable_audit()，关闭时零开销直接返回；
- 按天分文件：写入 ~/.jarvis/audit/YYYY-MM-DD.jsonl，JSON Lines 格式；
- 敏感脱敏：password/token/key/secret/auth/credential 等字段值打码；
- 进程安全：以追加模式写入，单条记录一次写入；
- 失败静默：写入异常仅 save_exception，绝不影响主流程。
"""

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.config import is_enable_audit
from jarvis.jarvis_utils.exception_utils import save_exception

# 敏感字段名（值将被打码）
_SENSITIVE_KEYS = {"password", "token", "key", "secret", "auth", "credential"}

# 全局单例与锁（进程安全）
_logger: "AuditLogger | None" = None
_lock = threading.Lock()


def _is_sensitive_key(key: str) -> bool:
    """判断键名是否含敏感词（子串匹配，覆盖 api_key/access_token 等复合键）。"""
    lowered = str(key).lower()
    return any(s in lowered for s in _SENSITIVE_KEYS)


def _redact(value: Any) -> Any:
    """递归脱敏：将敏感字段的值替换为 ***。"""
    if isinstance(value, dict):
        return {
            k: ("***" if _is_sensitive_key(k) else _redact(v)) for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


class AuditLogger:
    """审计日志写入器（按天分文件的 JSONL 追加写入）。"""

    def __init__(self, data_dir: str | None = None) -> None:
        self.data_dir = Path(data_dir or get_data_dir()) / "audit"

    def _get_file_path(self) -> Path:
        return self.data_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"

    def log(self, event_type: str, **data: Any) -> None:
        """写入一条审计事件记录。

        Args:
            event_type: 事件类型（如 user_input / tool_call / task_completed）
            data: 事件数据（写入前会做敏感字段脱敏）
        """
        record = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "data": _redact(data),
        }
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            file_path = self._get_file_path()
            with open(file_path, "a", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            save_exception(e, module="jarvis_audit.audit", function="AuditLogger.log")


def log_event(event_type: str, **data: Any) -> None:
    """记录一条审计事件（默认关闭时零开销直接返回）。

    该函数是审计系统的对外统一入口，供 Agent 各接入点调用。
    只有启用审计（enable_audit: true）时才真正写入日志。
    """
    if not is_enable_audit():
        return

    global _logger
    if _logger is None:
        with _lock:
            if _logger is None:
                _logger = AuditLogger()
    try:
        _logger.log(event_type, **data)
    except Exception as e:
        save_exception(e, module="jarvis_audit.audit", function="log_event")
