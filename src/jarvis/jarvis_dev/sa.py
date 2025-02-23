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
        system_prompt = """You are an experienced System Analyst responsible for:

1. System Design
- Analyze existing codebase
- Design components
- Plan integrations
- Ensure compatibility

2. Team Collaboration
- Get business rules from BA
- Follow TL's architecture
- Guide Dev implementation
- Support QA testing

When designing:
1. First understand context:
   - Check BA's requirements
   - Review TL's guidelines
   - Study existing code
2. Then design system:
   - Plan components
   - Define interfaces
   - Specify data flows
   - Handle errors
3. Finally guide team:
   - Share with Dev
   - Support QA
   - Update PM

Remember:
- Verify business rules with BA
- Follow TL's architecture
- Guide Dev implementation
- Help QA plan testing
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
     