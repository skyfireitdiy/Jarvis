from typing import Dict, Any, List, Callable
from jarvis.agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_dev.team_role import TeamRole
from jarvis.jarvis_dev.message import Message

class TechLead(TeamRole):
    """Tech Lead role for technical solution design"""
    
    def __init__(self, message_handler: Callable[[Message], Dict[str, Any]]):
        """Initialize Tech Lead agent"""
        system_prompt = """You are an AI Tech Lead agent focused on:

1. Technical Direction
- Guide architecture
- Set code standards
- Review solutions
- Ensure quality

2. Task Support
- Help solve problems
- Review code changes
- Guide implementation
- Remove blockers

Remember:
- Focus on technical success
- Skip process overhead
- Direct problem solving
- Ask when unclear
"""
        super().__init__("TechLead", system_prompt, message_handler)
        
    def _get_platform(self):
        return PlatformRegistry().get_thinking_platform()
        
    def _get_tools(self):
        tools = ToolRegistry()
        tools.use_tools([
            # 基础工具
            "ask_user",
            "execute_shell",
            # 技术工具
            "read_code",
            "ask_codebase",
            "code_review",
            "lsp_get_document_symbols",
            "lsp_find_references",
            "lsp_find_definition",
            "file_operation"
        ])
        return tools
        