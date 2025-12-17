# -*- coding: utf-8 -*-
"""
工具函数（jarvis_agent.utils）

- join_prompts: 统一的提示拼接策略（仅拼接非空段落，使用双换行）
- is_auto_complete: 统一的自动完成标记检测
"""

from enum import Enum
from typing import Any
from typing import Iterable


from jarvis.jarvis_utils.tag import ot


def join_prompts(parts: Iterable[str]) -> str:
    """
    将多个提示片段按统一规则拼接：
    - 过滤掉空字符串
    - 使用两个换行分隔
    - 不进行额外 strip，保持调用方原样语义
    """
    try:
        non_empty: list[str] = [p for p in parts if isinstance(p, str) and p]
    except Exception:
        # 防御性处理：若 parts 不可迭代或出现异常，直接返回空字符串
        return ""
    return "\n\n".join(non_empty)


def is_auto_complete(response: str) -> bool:
    """
    检测是否包含自动完成标记。
    当前实现：包含 ot('!!!COMPLETE!!!') 即视为自动完成。
    """
    try:
        return ot("!!!COMPLETE!!!") in response
    except Exception:
        # 防御性处理：即使 ot 出现异常，也不阻塞主流程
        return "!!!COMPLETE!!!" in response


def normalize_next_action(next_action: Any) -> str:
    """
    规范化下一步动作为字符串:
    - 如果是 Enum, 返回其 value（若为字符串）
    - 如果是 str, 原样返回
    - 其他情况返回空字符串
    """
    try:
        if isinstance(next_action, Enum):
            value = getattr(next_action, "value", None)
            return value if isinstance(value, str) else ""
        if isinstance(next_action, str):
            return next_action
        return ""
    except Exception:
        return ""


__all__ = ["join_prompts", "is_auto_complete", "normalize_next_action"]
