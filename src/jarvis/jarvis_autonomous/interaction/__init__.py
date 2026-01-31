"""增强交互模块

提供增强对话能力和主动交互功能：
- DialogueManager: 多轮对话管理器
- AmbiguityResolver: 歧义消解器
- ProactiveAssistant: 主动交互助手
"""

from .dialogue_manager import (
    DialogueManager,
    DialogueContext,
    DialogueTurn,
    DialogueState,
    ContextType,
)
from .ambiguity_resolver import (
    AmbiguityResolver,
    AmbiguityType,
    AmbiguityResult,
    ClarificationQuestion,
)
from .proactive_assistant import (
    ProactiveAssistant,
    ProactiveAction,
    ActionType,
    ActionPriority,
    SuggestionResult,
)

__all__ = [
    # 对话管理
    "DialogueManager",
    "DialogueContext",
    "DialogueTurn",
    "DialogueState",
    "ContextType",
    # 歧义消解
    "AmbiguityResolver",
    "AmbiguityType",
    "AmbiguityResult",
    "ClarificationQuestion",
    # 主动交互
    "ProactiveAssistant",
    "ProactiveAction",
    "ActionType",
    "ActionPriority",
    "SuggestionResult",
]
