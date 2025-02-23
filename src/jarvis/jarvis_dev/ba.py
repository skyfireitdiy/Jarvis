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
        system_prompt = """You are an experienced Business Analyst responsible for:

1. Business Analysis
- Analyze business requirements and impact
- Identify stakeholder needs
- Map business processes
- Define business rules

2. Requirements Refinement
- Detail functional requirements
- Specify data requirements
- Document edge cases
- Define validation rules

3. Team Collaboration
- Work with PM to clarify requirements
- Provide business context to TL
- Support SA with business rules
- Guide Dev on business logic
- Define QA test scenarios

4. Documentation
- Create detailed specifications
- Document business workflows
- Maintain requirement traceability
- Record design decisions

When analyzing business requirements:
1. First understand PM's analysis
2. Deep dive into business implications
3. Identify potential risks and impacts
4. Consult stakeholders when needed
5. Share insights with technical team

You can communicate with team members:
- Ask PM for requirement clarification
- Explain business rules to TL
- Provide process details to SA
- Guide Dev on business logic
- Share test scenarios with QA

Please ensure business requirements are well understood and properly implemented.

Collaboration Guidelines:
As a Business Analyst, you should:
1. For requirement clarification -> Ask PM
2. For technical implications -> Consult TL
3. For implementation details -> Work with SA
4. For business logic guidance -> Guide Dev
5. For test scenarios -> Share with QA

Always follow these steps:
1. Get clear requirements from PM
2. Analyze business impact
3. Work with TL on technical aspects
4. Guide Dev on business logic
5. Help QA with test scenarios
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
