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

# 全局变量：保存最后一条消息
last_message: str = ""
from typing import Any, Set

import colorama
from rich.console import Console
from rich.theme import Theme

# 初始化colorama以支持跨平台的彩色文本
colorama.init()
# 禁用tokenizers并行以避免多进程问题
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# 全局代理管理
global_agents: Set[str] = set()
current_agent_name: str = ""
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


def set_agent(agent_name: str, agent: Any) -> None:
    """
    设置当前代理并将其添加到全局代理集合中。

    参数：
        agent_name: 代理名称
        agent: 代理对象
    """
    global_agents.add(agent_name)
    global current_agent_name
    current_agent_name = agent_name


def get_agent_list() -> str:
    """
    获取表示当前代理状态的格式化字符串。

    返回：
        str: 包含代理数量和当前代理名称的格式化字符串
    """
    return (
        "[" + str(len(global_agents)) + "]" + current_agent_name
        if global_agents
        else ""
    )


def delete_agent(agent_name: str) -> None:
    """
    从全局代理集合中删除一个代理。

    参数：
        agent_name: 要删除的代理名称
    """
    if agent_name in global_agents:
        global_agents.remove(agent_name)
        global current_agent_name
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
    设置最后一条消息。

    参数:
        message: 要保存的消息
    """
    global last_message
    last_message = message


def get_last_message() -> str:
    """
    获取最后一条消息。

    返回:
        str: 最后一条消息
    """
    return last_message
    """
    获取当前中断信号状态。

    返回:
        int: 当前中断计数
    """
    return g_interrupt
