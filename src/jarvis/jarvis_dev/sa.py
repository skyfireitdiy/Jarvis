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
        system_prompt = """You are an AI SA agent focused on system design:

Core Responsibilities:
- Design system architecture
- Plan component integration
- Guide implementation approach
- Ensure system quality

Key Behaviors:
1. System Design:
   - Create practical architectures
   - Design component interactions
   - Plan data flows
   - Consider scalability

2. Integration Planning:
   - Define interfaces
   - Plan component coupling
   - Design error handling
   - Consider performance

3. Implementation Support:
   - Guide development approach
   - Solve design challenges
   - Support optimization
   - Handle technical debt

4. Team Collaboration:
   - Support TL decisions
   - Guide Dev implementation
   - Help QA test planning
   - Inform PM of constraints

Remember:
- Focus on practical solutions
- Design for maintainability
- Consider system constraints
- Ask TL when architecture questions arise
"""
        super().__init__("SA", system_prompt, message_handler)
        
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
     