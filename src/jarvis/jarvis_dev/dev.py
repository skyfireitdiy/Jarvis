from typing import Dict, Any, List, Callable
from jarvis.agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_dev.sa import SystemAnalyst
from jarvis.jarvis_dev.message import Message
from jarvis.jarvis_dev.team_role import TeamRole

class Developer(TeamRole):
    """Developer role for code implementation"""
    
    def __init__(self, message_handler: Callable[[Message], Dict[str, Any]]):
        """Initialize Developer agent"""
        system_prompt = """You are an AI Dev agent:
- Write code
- Fix bugs
- Add tests
- Get it working

Remember:
- Focus on working code
- Skip overhead
- Direct coding
- Ask when blocked
"""
        super().__init__("Developer", system_prompt, message_handler)
        
    def _get_platform(self):
        return PlatformRegistry().get_normal_platform()
        
    def _get_tools(self):
        tools = ToolRegistry()
        tools.use_tools([
            "ask_user",
            "create_code_agent"
        ])
        return tools
