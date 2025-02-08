from typing import Dict, Any

from jarvis.agent import Agent
from jarvis.utils import OutputType, PrettyOutput


class CodePlanAgentTool:
    name = "create_code_plan"
    description = "Create a detailed plan for code modifications based on requirements"
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The code modification task to plan"
            },
            "code_context": {
                "type": "string",
                "description": "Current code context and structure",
                "default": ""
            },
            "requirements": {
                "type": "string",
                "description": "Specific requirements for the code changes",
                "default": ""
            },
            "constraints": {
                "type": "string",
                "description": "Any constraints or limitations to consider",
                "default": ""
            }
        },
        "required": ["task"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Create a detailed code modification plan"""
        try:
            task = args["task"]
            code_context = args.get("code_context", "")
            requirements = args.get("requirements", "")
            constraints = args.get("constraints", "")

            PrettyOutput.print("Creating code modification plan...", OutputType.INFO)

            
            # Customize system message for planning
            system_message = """You are a Code Planning Agent specialized in analyzing requirements and creating detailed code modification plans.

Your task is to:
1. Analyze the requirements thoroughly
2. Identify affected code components
3. Create a detailed, step-by-step modification plan
4. Consider potential impacts and risks
5. Suggest verification steps

Your plan should include:
- Files to be modified
- Specific changes needed
- Dependencies to consider
- Testing requirements
- Potential risks and mitigations
- Verification steps

Focus on:
- Breaking down complex changes
- Maintaining code quality
- Minimizing side effects
- Ensuring testability
- Following best practices

Output Format:
1. ANALYSIS
   - Requirements breakdown
   - Affected components
   - Technical considerations

2. MODIFICATION PLAN
   - Step-by-step changes
   - File modifications
   - Code structure updates

3. VERIFICATION PLAN
   - Test cases
   - Review points
   - Acceptance criteria

4. RISK ASSESSMENT
   - Potential issues
   - Mitigation strategies
   - Rollback plan"""

            # Create planning agent with specialized system message
            planning_agent = Agent(
                system_prompt=system_message,
                name="CodePlanningAgent",
                is_sub_agent=True
            )


            # Build comprehensive task description
            task_description = f"""CODE MODIFICATION PLANNING TASK

TASK DESCRIPTION:
{task}

"""
            if code_context:
                task_description += f"""
CODE CONTEXT:
{code_context}

"""
            if requirements:
                task_description += f"""
REQUIREMENTS:
{requirements}

"""
            if constraints:
                task_description += f"""
CONSTRAINTS:
{constraints}
"""

            # Generate plan
            plan = planning_agent.run(task_description)

            return {
                "success": True,
                "stdout": f"Code Modification Plan:\n\n{plan}",
                "stderr": ""
            }

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "error": f"Failed to create code modification plan: {str(e)}"
            }
