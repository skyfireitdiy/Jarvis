from typing import Dict, Any, List
from jarvis.agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry

class ProductManager:
    """Product Manager role for requirement analysis"""
    
    def __init__(self):
        """Initialize Product Manager agent"""
        system_prompt = """You are an experienced Product Manager responsible for:

1. Requirement Analysis
- Understand and clarify requirements
- Identify key features and priorities
- Break down requirements into manageable tasks
- Define acceptance criteria

2. Task Management
- Create clear task descriptions
- Set task priorities
- Define task dependencies
- Estimate task complexity

3. Communication
- Clarify ambiguous requirements
- Document decisions and rationale
- Provide clear task context

Please analyze requirements and break them down into well-defined tasks."""

        summary_prompt = """Please format your analysis output in YAML between <ANALYSIS> and </ANALYSIS> tags:
<ANALYSIS>
features:
  - name: feature_name
    description: feature_description
    priority: High/Medium/Low
    
tasks:
  - id: task_id
    name: task_name
    description: task_description
    priority: High/Medium/Low
    dependencies: [task_ids]
    acceptance_criteria:
      - criterion_1
      - criterion_2
    complexity: High/Medium/Low
</ANALYSIS>"""

        # Initialize agent with thinking capabilities
        self.agent = Agent(
            system_prompt=system_prompt,
            summary_prompt=summary_prompt,
            name="ProductManager",
            platform=PlatformRegistry().get_thinking_platform(),
            tool_registry=ToolRegistry(),
            auto_complete=True,
            is_sub_agent=True
        )
        
    def analyze_requirement(self, requirement: str) -> Dict[str, Any]:
        """Analyze development requirement"""
        try:
            # Create analysis prompt
            prompt = f"""Please analyze this development requirement:

{requirement}

Please provide:
1. Requirement Analysis
- Key features and functionalities
- Business value and priorities
- Constraints and limitations
- Assumptions and dependencies

2. Task Breakdown
- List of specific tasks
- Task priorities and dependencies
- Acceptance criteria for each task
- Complexity estimates
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
                    tasks = analysis.get("tasks", [])
                except:
                    tasks = []
            else:
                tasks = []
            
            return {
                "success": True,
                "analysis": result,
                "tasks": tasks  # Add tasks field for BA consumption
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Requirement analysis failed: {str(e)}"
            }
