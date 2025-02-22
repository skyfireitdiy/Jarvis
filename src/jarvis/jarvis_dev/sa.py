from typing import Dict, Any, List
from jarvis.agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry

class SystemAnalyst:
    """System Analyst role for system design"""
    
    def __init__(self):
        """Initialize System Analyst agent"""
        system_prompt = """You are an experienced System Analyst responsible for:

1. System Design
- Component design
- Interface design
- Data model design
- Integration design

2. Technical Specifications
- API specifications
- Data schemas
- Interface contracts
- Error handling

3. System Documentation
- Architecture diagrams
- Sequence diagrams
- Data flow diagrams
- Component interactions

Please create detailed system designs and specifications."""

        summary_prompt = """Please format your design output in YAML between <DESIGN> and </DESIGN> tags:
<DESIGN>
components:
  - name: component_name
    type: class/module/service
    responsibilities:
      - responsibility_description
    dependencies:
      - component: component_name
        type: uses/implements/extends
    
    interfaces:
      - name: interface_name
        methods:
          - name: method_name
            parameters:
              - name: param_name
                type: param_type
                validation: validation_rule
            returns:
              type: return_type
              description: return_description
            exceptions:
              - type: exception_type
                condition: error_condition
    
    data_models:
      - name: model_name
        attributes:
          - name: attr_name
            type: attr_type
            constraints:
              - constraint_description
        relationships:
          - model: related_model
            type: one_to_many/many_to_one
            
implementation:
  classes:
    - name: class_name
      methods:
        - signature: method_signature
          logic:
            - logic_step_description
      attributes:
        - name: attr_name
          type: attr_type
          purpose: attr_purpose
</DESIGN>"""

        # Initialize agent with thinking capabilities
        self.agent = Agent(
            system_prompt=system_prompt,
            summary_prompt=summary_prompt,
            name="SystemAnalyst",
            platform=PlatformRegistry().get_thinking_platform(),
            tool_registry=ToolRegistry(),
            auto_complete=True,
            is_sub_agent=True
        )
        
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
