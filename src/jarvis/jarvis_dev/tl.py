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
        system_prompt = """You are an experienced Tech Lead responsible for:

1. Technical Leadership
- Guide technical decisions
- Ensure architectural quality
- Manage technical risks
- Drive technical excellence

2. Code Understanding
- Review existing codebase
- Analyze code structure
- Identify design patterns
- Understand dependencies

3. Architecture Design
- Design system architecture
- Ensure code compatibility
- Plan integrations
- Consider existing patterns

4. Team Coordination
- Guide team on codebase
- Review code changes
- Ensure integration quality
- Maintain consistency

When designing solutions:
1. First analyze existing code:
   - Review project structure
   - Understand patterns used
   - Check dependencies
   - Note coding standards
2. Plan integration approach:
   - Identify affected modules
   - Consider dependencies
   - Maintain consistency
   - Minimize disruption
3. Guide implementation:
   - Share code insights
   - Explain patterns
   - Review changes
   - Ensure quality

You can communicate with team members:
- Ask SA to review code
- Guide Dev on integration
- Discuss patterns with team
- Verify compatibility
- Report to PM

Please ensure technical excellence and code consistency."""

        super().__init__("TechLead", system_prompt, message_handler)
        
    def _get_platform(self):
        return PlatformRegistry().get_thinking_platform()
        
    def _get_tools(self):
        tools = ToolRegistry()
        tools.use_tools([
            # 基础工具
            "ask_user",
            "methodology",
            "execute_shell",
            # 技术工具
            "read_code",
            "ask_codebase",
            "code_review",
            "lsp_get_document_symbols",
            "lsp_find_references",
            "lsp_find_definition"
        ])
        return tools
        
    def design_solution(self, ba_analysis: str) -> Dict[str, Any]:
        """Design technical solution
        
        Args:
            ba_analysis: BA's business analysis
            
        Returns:
            Dict containing technical design
        """
        try:
            # Create design prompt
            prompt = f"""Please design a technical solution based on this business analysis:

Business Analysis:
{ba_analysis}

Please provide:
1. Technical Architecture
- System components
- Technology stack
- Integration patterns
- Data storage

2. Design Patterns
- Applicable patterns
- Component interactions
- Error handling
- Performance optimizations

3. Implementation Guidelines
- Code organization
- Testing strategy
- Deployment considerations
- Monitoring approach
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
                    architecture = design.get("architecture", {})
                    implementation = design.get("implementation", {})
                except:
                    architecture, implementation = {}, {}
            else:
                architecture, implementation = {}, {}
            
            return {
                "success": True,
                "design": result,
                "architecture": architecture,
                "implementation": implementation
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Technical design failed: {str(e)}"
            }
