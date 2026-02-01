"""增强交互模块

提供增强对话能力：
- DialogueManager: 多轮对话管理器
"""

from .dialogue_manager import (
    DialogueManager,
    DialogueContext,
    DialogueTurn,
    DialogueState,
    ContextType,
)

__all__ = [
    # 对话管理
    "DialogueManager",
    "DialogueContext",
    "DialogueTurn",
    "DialogueState",
    "ContextType",
]
