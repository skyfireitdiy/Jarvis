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
from typing import Any, Dict, List, Optional

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
current_agent_name: str = ""  # 最后开始运行的agent（可能已完成）
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
    通过附加后缀生成唯一的代理名称（如果必要）。

    参数：
        agent_name: 基础代理名称

    返回：
        str: 唯一的代理名称
    """
    if agent_name in global_agents:
        i = 1
        while f"{agent_name}_{i}" in global_agents:
            i += 1
        return f"{agent_name}_{i}"
    return agent_name


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
    return get_running_agent()


def get_current_agent_name() -> str:
    """
    获取当前代理名称（最后开始运行的agent，可能已完成）。
    注意：这返回的是"最后开始运行的agent"，可能已经完成运行。
    如果需要获取正在运行的agent名称，请使用 get_running_agent_name()。

    返回：
        str: 当前代理名称，如果不存在则返回空字符串
    """
    global current_agent_name
    # 如果current_agent_name指向的agent不存在，修复它
    if current_agent_name and current_agent_name not in global_agents:
        if global_agents:
            current_agent_name = next(iter(global_agents.keys()))
        else:
            current_agent_name = ""
    return current_agent_name


def set_running_agent(agent_name: str) -> None:
    """
    设置当前正在运行的代理名称（推入栈）。
    应该在agent开始运行时调用。
    支持嵌套调用：当agent调用其他agent时，状态会被正确保存。

    注意：同一个agent可以多次运行（非嵌套），每次运行都会独立推入栈。

    参数：
        agent_name: 代理名称
    """
    global running_agent_stack
    if agent_name in global_agents:
        running_agent_stack.append(agent_name)
    # 如果agent不存在，不推入栈（避免无效状态）


def clear_running_agent(agent_name: str) -> None:
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
    # 只从栈顶移除，确保嵌套调用的正确性
    if running_agent_stack[-1] == agent_name:
        running_agent_stack.pop()
    elif agent_name in running_agent_stack:
        # 如果不在栈顶，说明状态不一致（可能是重复调用clear_running_agent）
        # 这种情况下，我们不应该修改栈，因为可能会破坏嵌套结构
        # 例如：栈是 ["a", "b", "a"]，如果清除中间的 "a"，会破坏结构
        # 这种情况通常不应该发生，但如果发生了，我们只记录警告，不修改栈
        import warnings

        warnings.warn(
            f"尝试清除不在栈顶的agent '{agent_name}'。"
            f"当前栈: {running_agent_stack}。"
            f"这可能是重复调用clear_running_agent或状态不一致导致的。",
            RuntimeWarning,
            stacklevel=2,
        )


def get_running_agent() -> Any:
    """
    获取当前正在运行的代理实例（栈顶的agent）。
    这保证返回的agent一定正在运行中。
    支持嵌套调用：返回最顶层的（当前正在执行的）agent。

    返回：
        Any: 正在运行的代理实例，如果没有正在运行的agent则返回None
    """
    global running_agent_stack
    if running_agent_stack:
        top_agent_name = running_agent_stack[-1]
        if top_agent_name in global_agents:
            return global_agents.get(top_agent_name)
    return None


def get_running_agent_name() -> str:
    """
    获取当前正在运行的代理名称（栈顶的agent名称）。

    返回：
        str: 正在运行的代理名称，如果没有正在运行的agent则返回空字符串
    """
    global running_agent_stack
    if running_agent_stack:
        return running_agent_stack[-1]
    return ""


def is_agent_running(agent_name: str) -> bool:
    """
    检查指定的agent是否正在运行（在栈中）。

    参数：
        agent_name: 代理名称

    返回：
        bool: 如果agent正在运行则返回True
    """
    global running_agent_stack
    return agent_name in running_agent_stack and agent_name in global_agents


def get_running_agent_stack() -> List[str]:
    """
    获取当前正在运行的agent栈（用于调试）。
    栈底是第一个开始运行的agent，栈顶是当前正在执行的agent。

    返回：
        List[str]: agent名称列表，从栈底到栈顶
    """
    global running_agent_stack
    return running_agent_stack.copy()


def set_agent(agent_name: str, agent: Any) -> None:
    """
    设置当前代理并将其添加到全局代理集合中。

    参数：
        agent_name: 代理名称
        agent: 代理对象
    """
    global_agents[agent_name] = agent
    global current_agent_name
    current_agent_name = agent_name


def get_agent_list() -> str:
    """
    获取表示当前代理状态的格式化字符串。

    返回：
        str: 包含代理数量和当前代理名称的格式化字符串
    """
    if not global_agents:
        return ""
    # 使用函数获取current_agent_name，确保有效性
    current_name = get_current_agent_name()
    if current_name and current_name in global_agents:
        return "[" + str(len(global_agents)) + "]" + current_name
    # 如果current_agent_name无效，只返回数量
    return "[" + str(len(global_agents)) + "]"


def delete_agent(agent_name: str) -> None:
    """
    从全局代理集合中删除一个代理。

    参数：
        agent_name: 要删除的代理名称
    """
    if agent_name in global_agents:
        del global_agents[agent_name]
        global current_agent_name, running_agent_stack
        # 从运行栈中移除被删除的agent（如果存在）
        if agent_name in running_agent_stack:
            running_agent_stack = [
                name for name in running_agent_stack if name != agent_name
            ]
        # 使用函数获取current_agent_name，然后更新
        current_name = get_current_agent_name()
        # 只有当删除的是当前agent时，才需要更新current_agent_name
        if current_name == agent_name:
            # 如果还有其他agent，设置为第一个，否则清空
            if global_agents:
                # 设置为剩余的第一个agent
                current_agent_name = next(iter(global_agents.keys()))
            else:
                current_agent_name = ""
        # 如果current_agent_name指向的agent不在global_agents中（异常情况），修复它
        elif current_name and current_name not in global_agents:
            if global_agents:
                current_agent_name = next(iter(global_agents.keys()))
            else:
                current_agent_name = ""


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
    from pathlib import Path
    import json
    import random
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
