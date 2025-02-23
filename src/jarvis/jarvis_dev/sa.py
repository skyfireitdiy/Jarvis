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

1. System Understanding
- Analyze existing codebase
- Map system components
- Understand data flows
- Document dependencies

2. Integration Design
- Plan component integration
- Ensure compatibility
- Handle data migrations
- Maintain consistency

3. Technical Specifications
- Detail interface changes
- Update data schemas
- Modify API contracts
- Adapt error handling

4. Team Coordination
- Share system knowledge
- Guide implementation
- Review integrations
- Support testing

When designing systems:
1. First analyze current system:
   - Read existing code
   - Map dependencies
   - Document flows
   - Note patterns
2. Plan integration:
   - Identify touch points
   - Design interfaces
   - Handle migrations
   - Ensure compatibility
3. Guide development:
   - Share system context
   - Explain flows
   - Review changes
   - Verify integration

You can communicate with team members:
- Discuss architecture with TL
- Explain system to Dev
- Share flows with QA
- Update PM on progress

Please ensure smooth system integration and maintainability.

Collaboration Guidelines:
As a System Analyst, you should:
1. For architecture decisions -> Consult TL
2. For business rules -> Verify with BA
3. For implementation details -> Guide Dev
4. For integration testing -> Work with QA
5. For design updates -> Report to PM

Always follow these steps:
1. Get architecture approval from TL
2. Verify business rules with BA
3. Provide detailed guidance to Dev
4. Plan integration tests with QA
5. Keep PM informed of design changes."""

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
        
    def design_system(self, tl_design: str) -> Dict[str, Any]:
        """Design system components and interfaces
        
        Args:
            tl_design: TL's technical design
            
        Returns:
            Dict containing system design
        """
        try:
            # Create design prompt
            prompt = f"""Please create detailed system design based on this technical design:

Technical Design:
{tl_design}

Please provide:
1. Component Design
- Detailed component specifications
- Interface definitions
- Data models
- Error handling

2. Integration Design
- API specifications
- Message formats
- Protocol details
- Security requirements

3. Implementation Details
- Class structures
- Method signatures
- Data structures
- Validation rules
"""

            # Get design result
            result = self.agent.run(prompt)
            
            # Extract YAML content between tags
            import re
            import yaml
            
            yaml_match = re.search(r'<DESIGN>\s*(.*?)\s*</DESIGN>', result, re.DOTALL)
            if yaml_match:
                yaml_content = yaml_match.group(1)
                try:
                    design = yaml.safe_load(yaml_content)
                    components = design.get("components", [])
                    implementation = design.get("implementation", {})
                except:
                    components, implementation = [], {}
            else:
                components, implementation = [], {}
            
            return {
                "success": True,
                "design": result,
                "components": components,
                "implementation": implementation
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"System design failed: {str(e)}"
            }
