# -*- coding: utf-8 -*-
"""
全局变量和配置模块
该模块管理Jarvis系统的全局状态和配置。
包含：
- 全局代理管理
- 带有自定义主题的控制台配置
- 环境初始化
"""

import os

# 全局变量：保存消息历史
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

message_history: List[str] = []

# 全局模型组
_global_model_group: Optional[str] = None
MAX_HISTORY_SIZE = 50

# 短期记忆存储
short_term_memories: List[Dict[str, Any]] = []
MAX_SHORT_TERM_MEMORIES = 100

import colorama  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.theme import Theme  # noqa: E402

# 初始化colorama以支持跨平台的彩色文本
colorama.init()
# 禁用tokenizers并行以避免多进程问题
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# 全局代理管理
global_agents: Dict[str, Any] = {}
# 使用栈结构跟踪嵌套的agent运行状态，支持agent调用其他agent的场景
running_agent_stack: List[str] = []  # 正在运行的agent栈（最顶层是当前正在运行的agent）
# 表示与大模型交互的深度(>0表示正在交互)
g_in_chat: int = 0
# 表示是否接收到中断信号
g_interrupt: int = 0
# 使用自定义主题配置rich控制台
custom_theme = Theme(
    {
        "INFO": "yellow",
        "WARNING": "yellow",
        "ERROR": "red",
        "SUCCESS": "green",
        "SYSTEM": "cyan",
        "CODE": "green",
        "RESULT": "blue",
        "PLANNING": "magenta",
        "PROGRESS": "white",
        "DEBUG": "blue",
        "USER": "green",
        "TOOL": "yellow",
    }
)
console = Console(theme=custom_theme)


def make_agent_name(agent_name: str) -> str:
    """
    基于现有 global_agents 生成唯一的代理名称。

    约定：
    - 如果该名称尚未被占用，直接返回原始名称；
    - 如果已存在同名 Agent，则按 `name_1`、`name_2`... 的形式依次查找可用名称；
    - 已存在的带后缀名称会被一并考虑，例如 `name`、`name_1`、`name_3` 已存在时，返回 `name_2`。

    参数：
        agent_name: 基础代理名称

    返回：
        str: 唯一的代理名称
    """
    # 如果名称未被占用，直接返回原始名称
    if agent_name not in global_agents:
        return agent_name

    # 已存在同名 Agent，按 name_1、name_2... 形式查找第一个未被占用的名称
    index = 1
    while True:
        candidate = f"{agent_name}_{index}"
        if candidate not in global_agents:
            return candidate
        index += 1


def get_agent(agent_name: str) -> Any:
    """
    获取指定名称的代理实例。

    参数：
        agent_name: 代理名称

    返回：
        Any: 代理实例，如果不存在则返回None
    """
    return global_agents.get(agent_name)


def get_current_agent() -> Any:
    """
    获取当前正在运行的代理实例。

    重要：只返回正在运行的agent，确保不会返回已完成的agent。
    这保证返回的agent一定是正在运行中的，可以安全地修改其内部状态。

    如果没有正在运行的agent，返回None（可以为空，但一定不能错）。

    返回：
        Any: 正在运行的代理实例，如果没有正在运行的agent则返回None
    """
    # 只返回正在运行的agent，确保不会返回已完成的agent
    global running_agent_stack
    if running_agent_stack:
        current_agent_name = running_agent_stack[-1]
        if current_agent_name in global_agents:
            return global_agents.get(current_agent_name)
    return None


def get_current_agent_name() -> str:
    """
    获取当前代理名称（最后开始运行的agent，可能已完成）。
    注意：这返回的是"最后开始运行的agent"，可能已经完成运行。

    返回：
        str: 当前代理名称，如果不存在则返回空字符串
    """
    agent = get_current_agent()
    if agent:
        name = getattr(agent, "name", None)
        if isinstance(name, str):
            return name
    return ""


def set_current_agent(agent_name: str, agent: Any) -> None:
    """
    设置当前正在运行的代理名称（推入栈）。
    应该在agent开始运行时调用。
    支持嵌套调用：当agent调用其他agent时，状态会被正确保存。

    注意：同一个agent可以多次运行（非嵌套），每次运行都会独立推入栈。

    参数：
        agent_name: 代理名称
    """
    global running_agent_stack, global_agents
    global_agents[agent_name] = agent
    running_agent_stack.append(agent_name)


def clear_current_agent() -> None:
    """
    清除正在运行的代理名称（从栈中弹出）。
    应该在agent运行结束时调用。
    支持嵌套调用：当子agent结束时，会恢复父agent的运行状态。

    重要：只从栈顶移除agent，确保嵌套调用的正确性。
    如果agent不在栈顶，说明状态不一致（可能是重复调用或异常），
    会记录警告但不会修改栈，避免破坏嵌套结构。

    参数：
        agent_name: 要清除的代理名称（用于验证，确保清除的是正确的agent）
    """
    global running_agent_stack
    if not running_agent_stack:
        # 栈为空，可能是重复调用clear或状态不一致
        return
    current_agent_name = running_agent_stack.pop()
    if current_agent_name in global_agents:
        del global_agents[current_agent_name]


def get_agent_list() -> str:
    """
    获取表示当前代理状态的格式化字符串。

    返回：
        str: 包含代理数量和当前代理名称的格式化字符串
    """
    global global_agents
    if not global_agents:
        return ""
    return "[" + str(len(global_agents)) + "]" + ", ".join(global_agents.keys())


def set_in_chat(status: bool) -> None:
    """
    设置与大模型交互的状态。

    参数:
        status: True表示增加交互深度，False表示减少
    """
    global g_in_chat
    if status:
        g_in_chat += 1
    else:
        g_in_chat = max(0, g_in_chat - 1)


def get_in_chat() -> bool:
    """
    获取当前是否正在与大模型交互的状态。

    返回:
        bool: 当前交互状态(>0表示正在交互)
    """
    return g_in_chat > 0


def set_interrupt(status: bool) -> None:
    """
    设置中断信号状态。

    参数:
        status: 中断状态
    """
    global g_interrupt
    if status:
        g_interrupt += 1
    else:
        g_interrupt = 0


def get_interrupt() -> int:
    """
    获取当前中断信号状态。

    返回:
        int: 当前中断计数
    """
    return g_interrupt


def set_last_message(message: str) -> None:
    """
    将消息添加到历史记录中。

    参数:
        message: 要保存的消息
    """
    global message_history
    if message:
        # 避免重复添加
        if not message_history or message_history[-1] != message:
            message_history.append(message)
            if len(message_history) > MAX_HISTORY_SIZE:
                message_history.pop(0)


def get_last_message() -> str:
    """
    获取最后一条消息。

    返回:
        str: 最后一条消息，如果历史记录为空则返回空字符串
    """
    global message_history
    if message_history:
        return message_history[-1]
    return ""


def get_message_history() -> List[str]:
    """
    获取完整的消息历史记录。

    返回:
        List[str]: 消息历史列表
    """
    global message_history
    return message_history


def add_short_term_memory(memory_data: Dict[str, Any]) -> None:
    """
    添加短期记忆到全局存储。

    参数:
        memory_data: 包含记忆信息的字典
    """
    global short_term_memories
    short_term_memories.append(memory_data)
    # 如果超过最大数量，删除最旧的记忆
    if len(short_term_memories) > MAX_SHORT_TERM_MEMORIES:
        short_term_memories.pop(0)


def get_short_term_memories(tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    获取短期记忆，可选择按标签过滤。

    参数:
        tags: 用于过滤的标签列表（可选）

    返回:
        List[Dict[str, Any]]: 符合条件的短期记忆列表，按创建时间降序排列
    """
    global short_term_memories

    # 获取记忆副本
    memories_copy = short_term_memories.copy()

    # 按标签过滤（如果提供了标签）
    if tags:
        filtered_memories = []
        for memory in memories_copy:
            memory_tags = memory.get("tags", [])
            if any(tag in memory_tags for tag in tags):
                filtered_memories.append(memory)
        memories_copy = filtered_memories

    # 按创建时间排序（最新的在前）
    memories_copy.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    return memories_copy


def clear_short_term_memories() -> None:
    """
    清空所有短期记忆。
    """
    global short_term_memories
    short_term_memories.clear()


def set_global_model_group(model_group: Optional[str]) -> None:
    """设置全局模型组

    参数:
        model_group: 模型组名称
    """
    global _global_model_group
    _global_model_group = model_group


def get_global_model_group() -> Optional[str]:
    """获取全局模型组

    返回:
        Optional[str]: 全局模型组名称，如果未设置则返回None
    """
    return _global_model_group


def get_all_memory_tags() -> Dict[str, List[str]]:
    """
    获取所有记忆类型中的标签集合。
    每个类型最多返回200个标签，超过时随机提取。

    返回:
        Dict[str, List[str]]: 按记忆类型分组的标签列表
    """
    import json
    import random
    from pathlib import Path

    from jarvis.jarvis_utils.config import get_data_dir

    tags_by_type: Dict[str, List[str]] = {
        "short_term": [],
        "project_long_term": [],
        "global_long_term": [],
    }

    MAX_TAGS_PER_TYPE = 200

    # 获取短期记忆标签
    short_term_tags = set()
    for memory in short_term_memories:
        short_term_tags.update(memory.get("tags", []))
    short_term_tags_list = sorted(list(short_term_tags))
    if len(short_term_tags_list) > MAX_TAGS_PER_TYPE:
        tags_by_type["short_term"] = sorted(
            random.sample(short_term_tags_list, MAX_TAGS_PER_TYPE)
        )
    else:
        tags_by_type["short_term"] = short_term_tags_list

    # 获取项目长期记忆标签
    project_memory_dir = Path(".jarvis/memory")
    if project_memory_dir.exists():
        project_tags = set()
        for memory_file in project_memory_dir.glob("*.json"):
            try:
                with open(memory_file, "r", encoding="utf-8") as f:
                    memory_data = json.load(f)
                    project_tags.update(memory_data.get("tags", []))
            except Exception:
                pass
        project_tags_list = sorted(list(project_tags))
        if len(project_tags_list) > MAX_TAGS_PER_TYPE:
            tags_by_type["project_long_term"] = sorted(
                random.sample(project_tags_list, MAX_TAGS_PER_TYPE)
            )
        else:
            tags_by_type["project_long_term"] = project_tags_list

    # 获取全局长期记忆标签
    global_memory_dir = Path(get_data_dir()) / "memory" / "global_long_term"
    if global_memory_dir.exists():
        global_tags = set()
        for memory_file in global_memory_dir.glob("*.json"):
            try:
                with open(memory_file, "r", encoding="utf-8") as f:
                    memory_data = json.load(f)
                    global_tags.update(memory_data.get("tags", []))
            except Exception:
                pass
        global_tags_list = sorted(list(global_tags))
        if len(global_tags_list) > MAX_TAGS_PER_TYPE:
            tags_by_type["global_long_term"] = sorted(
                random.sample(global_tags_list, MAX_TAGS_PER_TYPE)
            )
        else:
            tags_by_type["global_long_term"] = global_tags_list

    return tags_by_type
