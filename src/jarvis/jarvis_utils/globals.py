"""
全局变量和配置模块
该模块管理Jarvis系统的全局状态和配置。
包含：
- 全局代理管理
- 带有自定义主题的控制台配置
- 环境初始化
"""
from typing import Any, Set, Dict
import colorama
import os
from rich.console import Console
from rich.theme import Theme
# 初始化colorama以支持跨平台的彩色文本
colorama.init()
# 禁用tokenizers并行以避免多进程问题
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# 全局代理管理
global_agents: Set[str] = set()
global_read_files: Dict[str, Set[str]] = {}
current_agent_name: str = ""
# 使用自定义主题配置rich控制台
custom_theme = Theme({
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
})
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
    return "[" + str(len(global_agents)) + "]" + current_agent_name if global_agents else ""
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

def add_read_file_record(file_path: str):
    if current_agent_name not in global_read_files:
        global_read_files[current_agent_name] = set()
    global_read_files[current_agent_name].add(file_path)

def has_read_file(file_path: str) -> bool:
    return not os.path.exists(file_path) or (current_agent_name in global_read_files and file_path in global_read_files[current_agent_name])

def clear_read_file_record():
    global_read_files.pop(current_agent_name, None)
