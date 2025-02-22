from typing import Dict, Any, List
from jarvis.agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry

class TechLead:
    """Tech Lead role for technical solution design"""
    
    def __init__(self):
        """Initialize Tech Lead agent"""
        system_prompt = """You are an experienced Tech Lead responsible for:

1. Technical Design
- Architecture design
- Technology selection
- Design patterns
- Performance considerations

2. Code Standards
- Coding guidelines
- Best practices
- Code organization
- Testing strategy

3. Technical Planning
- Resource estimation
- Technical dependencies
- Risk assessment
- Implementation strategy

Please design technical solutions that are robust, maintainable and scalable."""

        summary_prompt = """Please format your design output in YAML between <DESIGN> and </DESIGN> tags:
<DESIGN>
architecture:
  components:
    - name: component_name
      type: service/library/database
      technology: tech_stack
      responsibility: description
      
  patterns:
    - name: pattern_name
      purpose: purpose_description
      components: [component_names]
      
  interfaces:
    - name: interface_name
      type: REST/GraphQL/RPC
      operations:
        - name: operation_name
          input: input_spec
          output: output_spec
          
implementation:
  guidelines:
    - category: code/test/deploy
      rules:
        - rule_description
        
  testing:
    - level: unit/integration/e2e
      approach: description
      tools: [tool_names]
      
  deployment:
    - environment: dev/staging/prod
      requirements:
        - requirement_description
</DESIGN>"""

        # Initialize agent with thinking capabilities
        self.agent = Agent(
            system_prompt=system_prompt,
            summary_prompt=summary_prompt,
            name="TechLead",
            platform=PlatformRegistry().get_thinking_platform(),
            tool_registry=ToolRegistry(),
            auto_complete=True,
            is_sub_agent=True
        )
        
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
