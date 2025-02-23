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
        system_prompt = """You are an experienced QA Engineer responsible for:

1. Test Strategy
- Use create_code_agent for test generation
- Plan test coverage
- Define test data
- Track quality metrics

2. Team Collaboration
- Review BA's requirements
- Follow TL's standards
- Test SA's components
- Guide Dev testing

When testing:
1. First understand scope:
   - Check BA's requirements
   - Review TL's standards
   - Study SA's design
2. Then create tests:
   - Use create_code_agent
   - Write test cases
   - Prepare test data
3. Finally verify:
   - Execute tests
   - Report issues
   - Track fixes

Remember:
- Verify requirements with BA
- Follow TL's quality standards
- Test SA's integrations
- Guide Dev on testing
"""
        super().__init__("QualityAssurance", system_prompt, message_handler)
        
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
        