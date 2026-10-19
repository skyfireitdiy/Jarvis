# -*- coding: utf-8 -*-
"""secret-guard 插件：工具输出二次脱敏（Sanitizer）。

工具执行结果回填到会话历史之前，把其中再次出现的真实敏感值替换为
**已有占位符**（复用 ``agent.secret_guard_mapping`` 中的映射，不新建），
防止工具输出把敏感信息二次泄露给模型。

回调签名：``tool_output_sanitizer_cb(agent, output) -> str``
（由 ``_sanitize_tool_output`` 调用，回调异常时跳过该回调不阻断主流程）。
"""

import re
from typing import Any

from jarvis.jarvis_agent.share_secret_scanner import extract_secrets


def tool_output_sanitizer_cb(agent: Any, output: str) -> str:
    """工具输出二次脱敏：把真实敏感值替换为已有占位符。"""
    mapping = getattr(agent, "secret_guard_mapping", None)
    if not isinstance(mapping, dict) or not mapping or not output:
        return output
    for secret in extract_secrets(output):
        placeholder = _find_placeholder(mapping, secret)
        if placeholder is None:
            continue
        output = re.sub(re.escape(secret), placeholder, output)
    return output


def _find_placeholder(mapping: dict, secret: str) -> str | None:
    """在映射中查找真实值对应的占位符；不存在则返回 None。"""
    for placeholder, real in mapping.items():
        if real == secret:
            return placeholder
    return None
