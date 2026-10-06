# -*- coding: utf-8 -*-
"""
Jarvis 审计系统模块（jarvis_audit）

提供可配置、默认关闭的审计日志能力，记录 Agent 关键行为事件
（用户输入、工具调用、任务完成等）到 JSONL 审计日志。
"""

from .audit import AuditLogger
from .audit import log_event

__all__ = ["AuditLogger", "log_event"]
__version__ = "1.0.0"
