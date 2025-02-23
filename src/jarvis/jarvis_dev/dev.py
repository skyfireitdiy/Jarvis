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
        system_prompt = """You are an experienced Developer responsible for:

1. Code Implementation
- Use create_code_agent for code generation
- Follow system design specifications
- Ensure code quality
- Write tests

2. Team Collaboration
- Get business rules from BA
- Follow TL's guidance
- Implement SA's design
- Work with QA on testing

When implementing:
1. First understand the task:
   - Check requirements with BA
   - Get guidance from TL
   - Review SA's design
2. Then implement:
   - Use create_code_agent
   - Follow coding standards
   - Add tests
3. Finally verify:
   - Test functionality
   - Check quality
   - Submit for review

Remember:
- Ask BA for business logic
- Get TL's approval on approach
- Follow SA's design strictly
- Coordinate with QA on testing
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
