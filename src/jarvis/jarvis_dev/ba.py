from typing import Dict, Any, List
from jarvis.agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry

class BusinessAnalyst:
    """Business Analyst role for business logic analysis"""
    
    def __init__(self):
        """Initialize Business Analyst agent"""
        system_prompt = """You are an experienced Business Analyst responsible for:

1. Business Analysis
- Analyze business requirements
- Identify business rules and workflows
- Define use cases and scenarios
- Document business processes

2. Requirements Specification
- Create detailed functional specifications
- Define data requirements
- Specify business rules
- Document edge cases

3. Process Modeling
- Create process flow diagrams
- Define data flow
- Identify integration points
- Document state transitions

Please analyze business requirements and create detailed specifications."""

        summary_prompt = """Please format your analysis output in YAML between <ANALYSIS> and </ANALYSIS> tags:
<ANALYSIS>
business_rules:
  - rule_id: rule_id
    description: rule_description
    type: validation/calculation/process
    
workflows:
  - name: workflow_name
    description: workflow_description
    steps:
      - step_id: step_id
        description: step_description
        actor: actor_name
        action: action_description
        
use_cases:
  - id: uc_id
    name: use_case_name
    actor: actor_name
    preconditions:
      - condition_1
    main_flow:
      - step_1
    alternative_flows:
      - condition: condition
        steps:
          - alt_step_1
    
data_requirements:
  - entity: entity_name
    attributes:
      - name: attr_name
        type: attr_type
        validation: validation_rule
    relationships:
      - entity: related_entity
        type: one_to_many/many_to_one
</ANALYSIS>"""

        # Initialize agent with thinking capabilities
        self.agent = Agent(
            system_prompt=system_prompt,
            summary_prompt=summary_prompt,
            name="BusinessAnalyst",
            platform=PlatformRegistry().get_thinking_platform(),
            tool_registry=ToolRegistry(),
            auto_complete=True,
            is_sub_agent=True
        )
        
    def analyze_business(self, pm_analysis: str) -> Dict[str, Any]:
        """Analyze business requirements
        
        Args:
            pm_analysis: PM's requirement analysis
            
        Returns:
            Dict containing business analysis results
        """
        try:
            # Create analysis prompt
            prompt = f"""Please analyze these business requirements:

PM Analysis:
{pm_analysis}

Please provide:
1. Business Analysis
- Business rules and constraints
- Workflows and processes
- Data requirements
- Integration requirements

2. Use Cases
- Actor definitions
- Main success scenarios
- Alternative flows
- Exception flows

3. Data Requirements
- Data entities
- Relationships
- Validation rules
- Business rules
"""

            # Get analysis result
            result = self.agent.run(prompt)
            
            # Extract YAML content between tags
            import re
            import yaml
            
            yaml_match = re.search(r'<ANALYSIS>\s*(.*?)\s*</ANALYSIS>', result, re.DOTALL)
            if yaml_match:
                yaml_content = yaml_match.group(1)
                try:
                    analysis = yaml.safe_load(yaml_content)
                    business_rules = analysis.get("business_rules", [])
                    workflows = analysis.get("workflows", [])
                    use_cases = analysis.get("use_cases", [])
                    data_requirements = analysis.get("data_requirements", [])
                except:
                    business_rules, workflows = [], []
                    use_cases, data_requirements = [], []
            else:
                business_rules, workflows = [], []
                use_cases, data_requirements = [], []
            
            return {
                "success": True,
                "analysis": result,
                "business_rules": business_rules,
                "workflows": workflows,
                "use_cases": use_cases,
                "data_requirements": data_requirements
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Business analysis failed: {str(e)}"
            }
