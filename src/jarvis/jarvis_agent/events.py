# -*- coding: utf-8 -*-
"""
事件主题与负载类型定义（jarvis_agent.events）

目的：
- 统一事件名称，避免在代码各处硬编码字符串导致的漂移
- 提供事件负载的类型提示，便于静态检查与后续文档化
- 本文件仅提供常量与类型定义，不改变现有行为
"""

from typing import Any
from typing import List
from typing import TypedDict

# 事件主题常量
BEFORE_TOOL_CALL = "before_tool_call"
AFTER_TOOL_CALL = "after_tool_call"

# 会话与任务生命周期相关
TASK_STARTED = "task_started"
TASK_COMPLETED = "task_completed"

# 总结阶段
BEFORE_SUMMARY = "before_summary"
AFTER_SUMMARY = "after_summary"

# 附加提示
BEFORE_ADDON_PROMPT = "before_addon_prompt"
AFTER_ADDON_PROMPT = "after_addon_prompt"

# 历史清理
BEFORE_HISTORY_CLEAR = "before_history_clear"
AFTER_HISTORY_CLEAR = "after_history_clear"

# 模型调用
BEFORE_MODEL_CALL = "before_model_call"
AFTER_MODEL_CALL = "after_model_call"

# 其他
INTERRUPT_TRIGGERED = "interrupt_triggered"
BEFORE_TOOL_FILTER = "before_tool_filter"
TOOL_FILTERED = "tool_filtered"


# 事件负载类型（仅用于类型提示）
class BeforeToolCallEvent(TypedDict, total=False):
    agent: Any
    current_response: str


class AfterToolCallEvent(TypedDict, total=False):
    agent: Any
    current_response: str
    need_return: bool
    tool_prompt: str


# 任务生命周期
class TaskStartedEvent(TypedDict, total=False):
    agent: Any
    name: str
    description: str
    user_input: str


class TaskCompletedEvent(TypedDict, total=False):
    agent: Any
    auto_completed: bool
    need_summary: bool


# 总结阶段
class BeforeSummaryEvent(TypedDict, total=False):
    agent: Any
    prompt: str
    auto_completed: bool
    need_summary: bool


class AfterSummaryEvent(TypedDict, total=False):
    agent: Any
    summary: str


# 附加提示
class BeforeAddonPromptEvent(TypedDict, total=False):
    agent: Any
    need_complete: bool
    current_message: str
    has_session_addon: bool


class AfterAddonPromptEvent(TypedDict, total=False):
    agent: Any
    need_complete: bool
    addon_text: str
    final_message: str


# 历史清理
class BeforeHistoryClearEvent(TypedDict, total=False):
    agent: Any


class AfterHistoryClearEvent(TypedDict, total=False):
    agent: Any


# 模型调用
class BeforeModelCallEvent(TypedDict, total=False):
    agent: Any
    message: str


class AfterModelCallEvent(TypedDict, total=False):
    agent: Any
    message: str
    response: str


# 中断
class InterruptTriggeredEvent(TypedDict, total=False):
    agent: Any
    current_response: str
    user_input: str


# 工具筛选
class BeforeToolFilterEvent(TypedDict, total=False):
    agent: Any
    task: str
    total_tools: int
    threshold: int


class ToolFilteredEvent(TypedDict, total=False):
    agent: Any
    task: str
    selected_tools: List[str]
    total_tools: int
    threshold: int


__all__ = [
    "BEFORE_TOOL_CALL",
    "AFTER_TOOL_CALL",
    "TASK_STARTED",
    "TASK_COMPLETED",
    "BEFORE_SUMMARY",
    "AFTER_SUMMARY",
    "BEFORE_ADDON_PROMPT",
    "AFTER_ADDON_PROMPT",
    "BEFORE_HISTORY_CLEAR",
    "AFTER_HISTORY_CLEAR",
    "BEFORE_MODEL_CALL",
    "AFTER_MODEL_CALL",
    "INTERRUPT_TRIGGERED",
    "BEFORE_TOOL_FILTER",
    "TOOL_FILTERED",
    "BeforeToolCallEvent",
    "AfterToolCallEvent",
    "TaskStartedEvent",
    "TaskCompletedEvent",
    "BeforeSummaryEvent",
    "AfterSummaryEvent",
    "BeforeAddonPromptEvent",
    "AfterAddonPromptEvent",
    "BeforeHistoryClearEvent",
    "AfterHistoryClearEvent",
    "BeforeModelCallEvent",
    "AfterModelCallEvent",
    "InterruptTriggeredEvent",
    "BeforeToolFilterEvent",
    "ToolFilteredEvent",
]
