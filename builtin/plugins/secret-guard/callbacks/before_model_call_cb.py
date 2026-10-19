# -*- coding: utf-8 -*-
"""secret-guard 插件：模型调用前敏感信息脱敏（Modifier）。

在消息发送给模型之前，把其中命中的敏感凭据替换为占位符
``⟦SECRET_<hex>⟧``，占位符→真实值的映射保存在 ``agent.secret_guard_mapping``
（进程内 dict，随会话保存/恢复）。

支持两种消息形态：
- ``str``：直接扫描替换；
- ``List[ContentBlock]``（多模态）：只处理 ``type == "text"`` 的文本块。

同一敏感值复用同一占位符；映射中已存在的敏感值直接复用其占位符。
"""

import re
import secrets
from typing import Any
from typing import Dict
from typing import List
from typing import Union
from typing import cast

from jarvis.jarvis_agent.share_secret_scanner import extract_secrets
from jarvis.jarvis_platform.content_types import ContentBlock

# 占位符格式：⟦SECRET_<hex>⟧
_PLACEHOLDER_RE = re.compile(r"⟦SECRET_[0-9a-f]{6}⟧")


def _ensure_mapping(agent: Any) -> Dict[str, str]:
    """确保 agent.secret_guard_mapping 存在并返回。"""
    if not hasattr(agent, "secret_guard_mapping") or not isinstance(
        agent.secret_guard_mapping, dict
    ):
        agent.secret_guard_mapping = {}
    return agent.secret_guard_mapping


def _placeholder_for(mapping: Dict[str, str], secret: str) -> str:
    """为敏感值生成（或复用）占位符。"""
    # 复用：遍历映射找真实值对应的占位符
    for placeholder, real in mapping.items():
        if real == secret:
            return placeholder
    # 新建：生成不冲突的占位符
    while True:
        placeholder = f"⟦SECRET_{secrets.token_hex(3)}⟧"
        if placeholder not in mapping:
            break
    mapping[placeholder] = secret
    return placeholder


def _sanitize_text(mapping: Dict[str, str], text: str) -> str:
    """扫描并替换文本中的敏感值。"""
    for secret in extract_secrets(text):
        placeholder = _placeholder_for(mapping, secret)
        # 用正则替换（secret 可能含换行等特殊字符）
        text = re.sub(re.escape(secret), placeholder, text)
    return text


def before_model_call_cb(agent: Any, message: Union[str, List[ContentBlock]]) -> Any:
    """模型调用前脱敏：替换 message 中的敏感凭据为占位符。"""
    mapping = _ensure_mapping(agent)
    if isinstance(message, str):
        return _sanitize_text(mapping, message)
    if isinstance(message, list):
        # 多模态：只处理文本块，其余块原样保留
        result: List[ContentBlock] = []
        for block in message:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    block = cast(
                        ContentBlock,
                        {"type": "text", "text": _sanitize_text(mapping, text)},
                    )
            result.append(block)
        return result
    return message
