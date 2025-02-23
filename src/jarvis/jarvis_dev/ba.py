from typing import Dict, Any, List, Optional, Callable, Union
from jarvis.agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_dev.team_role import TeamRole
from jarvis.jarvis_dev.message import Message

class BusinessAnalyst(TeamRole):
    """Business Analyst role for business logic analysis"""
    
    def __init__(self, message_handler: Callable[[Message], Dict[str, Any]]):
        """Initialize Business Analyst agent"""
        system_prompt = """You are an AI Business Analyst agent focused on:

1. Requirement Analysis
- Extract business logic
- Define data rules
- Specify workflows
- Document constraints

2. Task Support
- Share business rules
- Clarify requirements
- Define success criteria
- Help complete tasks

Remember:
- Focus on business logic
- Skip stakeholder management
- Direct communication
- Ask when unclear
"""
        super().__init__("BusinessAnalyst", system_prompt, message_handler)
        
    def _get_platform(self):
        return PlatformRegistry().get_thinking_platform()
        
    def _get_tools(self):
        tools = ToolRegistry()
        tools.use_tools([
            # 基础工具
            "ask_user",
            "execute_shell",
            # 业务工具
            "read_code",
            "ask_codebase",
            "search",
            "read_webpage",
            "file_operation",
            "rag",
            "lsp_get_document_symbols"
        ])
        return tools
