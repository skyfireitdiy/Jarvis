"""
Global Variables and Configuration Module
This module manages global state and configurations for the Jarvis system.
It includes:
- Global agent management
- Console configuration with custom theme
- Environment initialization
"""
from typing import Any, Set
import colorama
import os
from rich.console import Console
from rich.theme import Theme
# Initialize colorama for cross-platform colored text
colorama.init()
# Disable tokenizers parallelism to avoid issues with multiprocessing
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# Global agent management
global_agents: Set[str] = set()
current_agent_name: str = ""
# Configure rich console with custom theme
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
    Generate a unique agent name by appending a suffix if necessary.
    
    Args:
        agent_name: The base agent name
        
    Returns:
        str: Unique agent name
    """
    if agent_name in global_agents:
        i = 1
        while f"{agent_name}_{i}" in global_agents:
            i += 1
        return f"{agent_name}_{i}"
    return agent_name
def set_agent(agent_name: str, agent: Any) -> None:
    """
    Set the current agent and add it to the global agents set.
    
    Args:
        agent_name: The name of the agent
        agent: The agent object
    """
    global_agents.add(agent_name)
    global current_agent_name
    current_agent_name = agent_name
def get_agent_list() -> str:
    """
    Get a formatted string representing the current agent status.
    
    Returns:
        str: Formatted string with agent count and current agent name
    """
    return "[" + str(len(global_agents)) + "]" + current_agent_name if global_agents else ""
def delete_agent(agent_name: str) -> None:
    """
    Delete an agent from the global agents set.
    
    Args:
        agent_name: The name of the agent to delete
    """
    if agent_name in global_agents:
        global_agents.remove(agent_name)
        global current_agent_name
        current_agent_name = ""