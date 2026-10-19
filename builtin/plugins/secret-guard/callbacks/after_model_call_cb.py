# -*- coding: utf-8 -*-
"""secret-guard 插件：模型调用后占位符还原（Modifier）。

把模型响应中的占位符 ``⟦SECRET_<hex>⟧`` 还原为真实敏感值（从
``agent.secret_guard_mapping`` 查表）。占位符不在映射中时原样保留
（可能是模型幻觉生成的，无法安全还原）。

还原发生在写入会话历史/打印给用户之前，保证模型看到的占位符、
用户看到的是真实值。
"""

import re
from typing import Any

# 占位符格式：⟦SECRET_<hex>⟧
_PLACEHOLDER_RE = re.compile(r"⟦SECRET_[0-9a-f]{6}⟧")


def _restore_text(mapping: Any, text: str) -> str:
    """把文本中的占位符还原为真实值。"""
    if not text:
        return text

    def _repl(match: "re.Match[str]") -> str:
        placeholder = match.group(0)
        if isinstance(mapping, dict) and placeholder in mapping:
            return mapping[placeholder]
        return placeholder

    return _PLACEHOLDER_RE.sub(_repl, text)


def after_model_call_cb(agent: Any, response: str) -> str:
    """模型调用后还原：把响应中的占位符替换回真实敏感值。"""
    mapping = getattr(agent, "secret_guard_mapping", None)
    return _restore_text(mapping, response)
