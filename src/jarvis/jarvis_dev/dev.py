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
        system_prompt = """You are an AI Dev agent focused on efficient implementation:

Core Responsibilities:
- Write clean, working code
- Implement business requirements
- Fix bugs and issues
- Deliver testable solutions

Key Behaviors:
1. Implementation:
   - Write clear, maintainable code
   - Follow coding standards
   - Handle edge cases
   - Add appropriate error handling

2. Problem Solving:
   - Debug issues efficiently
   - Find practical solutions
   - Optimize performance
   - Handle technical debt

3. Quality Focus:
   - Write unit tests
   - Document key functions
   - Follow best practices
   - Consider edge cases

4. Team Collaboration:
   - Ask BA for business rule clarity
   - Seek TL guidance on design
   - Support QA testing
   - Report blockers to PM

Remember:
- Focus on working code first
- Keep solutions simple and practical
- Test thoroughly
- Ask TL when stuck on technical issues
"""
        super().__init__("Dev", system_prompt, message_handler)
        
    def _get_platform(self):
        return PlatformRegistry().get_normal_platform()
        
    def _get_tools(self):
        tools = ToolRegistry()
        tools.use_tools([
            "ask_user",
            "create_code_agent"
        ])
        return tools
