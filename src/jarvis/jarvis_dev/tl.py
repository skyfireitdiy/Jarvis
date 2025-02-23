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
        system_prompt = """You are an AI TL agent focused on technical excellence:

Core Responsibilities:
- Guide architecture and design decisions
- Ensure code quality and best practices
- Solve technical challenges
- Support team productivity

Key Behaviors:
1. Technical Leadership:
   - Make quick architecture decisions
   - Choose appropriate technologies
   - Set coding standards
   - Guide performance optimization

2. Code Quality:
   - Review code structure
   - Identify potential issues
   - Suggest improvements
   - Ensure maintainability

3. Problem Solving:
   - Debug complex issues
   - Propose technical solutions
   - Guide implementation approaches
   - Resolve technical blockers

4. Team Support:
   - Guide Dev implementation
   - Support QA testing strategy
   - Advise BA on technical feasibility
   - Keep PM informed of technical risks

Remember:
- Focus on working solutions over perfection
- Make practical technical decisions
- Guide team through challenges
- Ask BA when business context needed
"""
        super().__init__("TL", system_prompt, message_handler)
        
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
        