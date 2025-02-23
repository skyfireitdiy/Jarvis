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
        system_prompt = (
            "You are an experienced Developer responsible for:\n\n"
            "1. Code Implementation\n"
            "- Use create_code_agent for code generation\n"
            "- Follow system design specifications\n"
            "- Ensure code quality and standards\n"
            "- Write comprehensive tests\n\n"
            "2. Code Understanding\n"
            "- Study existing codebase\n"
            "- Analyze code patterns\n"
            "- Review dependencies\n\n"
            "3. Team Collaboration\n"
            "- Follow SA's design\n"
            "- Get TL's guidance\n"
            "- Address QA feedback\n"
            "- Report progress\n\n"
            "When implementing:\n"
            "1. First understand requirements:\n"
            "   - Review SA's design\n"
            "   - Check existing code\n"
            "   - Note coding standards\n"
            "2. Use create_code_agent:\n"
            "   - Generate implementation\n"
            "   - Add tests and docs\n"
            "   - Handle errors\n"
            "3. Review and refine:\n"
            "   - Verify functionality\n"
            "   - Check code quality\n"
            "   - Submit for review\n\n"
            "Collaboration Guidelines:\n"
            "1. For business logic -> Ask BA\n"
            "2. For technical guidance -> Consult TL\n"
            "3. For system design -> Work with SA\n"
            "4. For code review -> Submit to TL\n"
            "5. For testing -> Coordinate with QA\n"
        )
        super().__init__("Developer", system_prompt, message_handler)
        
    def _get_platform(self):
        return PlatformRegistry().get_normal_platform()
        
    def _get_tools(self):
        tools = ToolRegistry()
        tools.use_tools([
            # 基础工具
            "ask_user",
            "execute_shell",
            # 开发工具
            "read_code",
            "ask_codebase",
            "lsp_validate_edit",
            "lsp_get_document_symbols",
            "code_review",
            "file_operation",
            "create_code_agent"
        ])
        return tools

    def implement(self, sa_design: str) -> Dict[str, Any]:
        """Implement system design
        
        Args:
            sa_design: SA's system design
            
        Returns:
            Dict containing implementation results
        """
        try:
            # Create code agent to implement the design
            result = self.agent.run(f"""Please implement the system design:

System Design:
{sa_design}

Use create_code_agent tool to generate the implementation.
Make sure to:
1. Follow the system design specifications
2. Implement all required components
3. Add proper tests and documentation
4. Handle error cases
5. Maintain code quality standards
""")
            
            return {
                "success": True,
                "implementation": result
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Implementation failed: {str(e)}"
            }
