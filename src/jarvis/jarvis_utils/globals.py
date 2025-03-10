from typing import Any
import colorama
import os
from rich.console import Console
from rich.theme import Theme
# Initialize colorama
colorama.init()
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# Global agents set
global_agents = set()
current_agent_name = ""
# Create console with custom theme
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
def make_agent_name(agent_name: str):
    if agent_name in global_agents:
        i = 1
        while f"{agent_name}_{i}" in global_agents:
            i += 1
        return f"{agent_name}_{i}"
    else:
        return agent_name
def set_agent(agent_name: str, agent: Any):
    global_agents.add(agent_name)
    global current_agent_name
    current_agent_name = agent_name
def get_agent_list():
    return "[" + str(len(global_agents)) + "]" + current_agent_name if global_agents else ""
def delete_agent(agent_name: str):
    if agent_name in global_agents:
        global_agents.remove(agent_name)
        global current_agent_name
        current_agent_name = ""