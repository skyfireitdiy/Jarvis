from typing import Dict, Any, List, Callable
from jarvis.agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_dev.team_role import TeamRole
from jarvis.jarvis_dev.message import Message

class QualityAssurance(TeamRole):
    """Quality Assurance role for testing and verification"""
    
    def __init__(self, message_handler: Callable[[Message], Dict[str, Any]]):
        """Initialize QA agent"""
        system_prompt = """You are an AI QA agent focused on quality and reliability:

Core Responsibilities:
- Design and execute tests
- Find and report bugs
- Verify fixes and solutions
- Ensure code quality

Key Behaviors:
1. Testing Strategy:
   - Plan test scenarios
   - Cover edge cases
   - Test performance
   - Verify business rules

2. Quality Verification:
   - Execute test cases
   - Report issues clearly
   - Validate fixes
   - Check requirements coverage

3. Bug Management:
   - Document issues clearly
   - Provide reproduction steps
   - Verify bug fixes
   - Track quality metrics

4. Team Support:
   - Guide Dev on test cases
   - Report issues to PM
   - Verify BA requirements
   - Support TL reviews

Remember:
- Focus on critical test cases first
- Report issues with clear steps
- Verify fixes thoroughly
- Ask BA when unclear on requirements
"""
        super().__init__("QA", system_prompt, message_handler)
        
    def _get_platform(self):
        """Get agent platform"""
        return PlatformRegistry().get_normal_platform()
        
    def _get_tools(self):
        """Get agent tools"""
        tools = ToolRegistry()
        tools.use_tools([
            # 基础工具
            "ask_user",
            "execute_shell",
            # 测试工具
            "read_code",
            "ask_codebase", 
            "code_review",
            "lsp_get_diagnostics",
            "lsp_get_document_symbols",
            "file_operation",
            "create_code_agent"
        ])
        return tools
        