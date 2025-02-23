from typing import Dict, Any, List, Callable
from jarvis.agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_dev.team_role import TeamRole
from jarvis.jarvis_dev.message import Message

class SystemAnalyst(TeamRole):
    """System Analyst role for system design"""
    
    def __init__(self, message_handler: Callable[[Message], Dict[str, Any]]):
        """Initialize System Analyst agent"""
        system_prompt = """You are an AI System Analyst agent focused on:

1. System Design
- Design components
- Define interfaces
- Plan integration
- Ensure compatibility

2. Task Support
- Guide implementation
- Solve integration issues
- Help with technical details
- Support task completion

Remember:
- Focus on system success
- Skip documentation overhead
- Direct problem solving
- Ask when unclear
"""
        super().__init__("SystemAnalyst", system_prompt, message_handler)
        
    def _get_platform(self):
        """Get agent platform"""
        return PlatformRegistry().get_thinking_platform()
        
    def _get_tools(self):
        """Get agent tools"""
        tools = ToolRegistry()
        tools.use_tools([
            # 基础工具
            "ask_user",
            "execute_shell",
            # 系统工具
            "read_code",
            "ask_codebase",
            "lsp_get_document_symbols",
            "lsp_find_definition",
            "lsp_find_references",
            "code_review",
            "file_operation"
        ])
        return tools
     