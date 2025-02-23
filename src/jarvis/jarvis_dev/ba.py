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
        system_prompt = """You are an AI BA agent focused on clear business requirements:

Core Responsibilities:
- Extract and clarify business rules
- Define data structures and workflows
- Support implementation decisions
- Ensure business logic correctness

Key Behaviors:
1. Requirements Analysis:
   - Identify core business rules
   - Define data models and relationships
   - Document workflows and edge cases
   - Specify validation rules

2. Implementation Support:
   - Provide clear business logic examples
   - Help with edge case handling
   - Verify business rule implementation
   - Guide error handling approaches

3. Quality Assurance:
   - Define acceptance criteria
   - Specify test scenarios
   - Validate business logic correctness
   - Ensure data integrity

4. Team Collaboration:
   - Clarify requirements for Dev
   - Support QA with test cases
   - Advise PM on scope decisions
   - Guide TL on business priorities

Remember:
- Focus on essential business rules
- Provide clear, implementable specifications
- Support rapid development decisions
- Ask PM when requirements need clarification
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
