from typing import Dict, Any

from jarvis.agent import Agent
from jarvis.utils import OutputType, PrettyOutput


class CodeSubAgentTool:
    name = "create_code_sub_agent"
    description = "Create a sub-agent to handle specific code development subtasks"
    parameters = {
        "type": "object",
        "properties": {
            "subtask": {
                "type": "string",
                "description": "The specific code development subtask to complete"
            },
            "parent_task": {
                "type": "string",
                "description": "The parent task context",
                "default": ""
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of files related to the subtask",
                "default": []
            },
            "dependencies": {
                "type": "string",
                "description": "Dependencies and relationships with other parts of the code",
                "default": ""
            },
            "constraints": {
                "type": "string",
                "description": "Specific constraints or requirements for the subtask",
                "default": ""
            }
        },
        "required": ["subtask"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute code development subtask"""
        try:
            subtask = args["subtask"]
            parent_task = args.get("parent_task", "")
            files = args.get("files", [])
            dependencies = args.get("dependencies", "")
            constraints = args.get("constraints", "")

            PrettyOutput.print("Creating code sub-agent for subtask...", OutputType.INFO)

            # Customize system message for subtask handling
            system_message = """You are a Code Development Sub-Agent specialized in handling specific code subtasks within a larger development effort.

Your task is to:
1. Focus on the assigned subtask
2. Maintain consistency with parent task
3. Follow code development best practices
4. Coordinate with other components
5. Ensure quality and compatibility

Subtask Execution Process:
1. ANALYSIS
   - Understand subtask requirements
   - Review related code
   - Identify dependencies
   - Plan implementation

2. IMPLEMENTATION
   - Follow parent task guidelines
   - Make focused changes
   - Maintain consistency
   - Document changes
   - Consider dependencies

3. COORDINATION
   - Align with parent task
   - Check interface compatibility
   - Verify integration points
   - Handle dependencies

4. QUALITY CONTROL
   - Test changes thoroughly
   - Verify requirements
   - Check edge cases
   - Document thoroughly

Version Control:
- Create focused commits
- Reference parent task
- Document relationships
- Maintain traceability

Guidelines:
- Stay within subtask scope
- Maintain code standards
- Consider parent context
- Handle edge cases
- Document clearly

Output Format:
1. SUBTASK SUMMARY
   - Implementation status
   - Changes made
   - Integration points

2. VERIFICATION
   - Test results
   - Quality checks
   - Integration status

3. NEXT STEPS
   - Required actions
   - Dependencies
   - Integration notes"""

            # Create sub-agent
            sub_agent = Agent(
                system_prompt=system_message,
                name="CodeSubAgent",
                is_sub_agent=True
            )

            # Build comprehensive subtask description
            task_description = f"""CODE DEVELOPMENT SUBTASK

SUBTASK:
{subtask}

"""
            if parent_task:
                task_description += f"""
PARENT TASK CONTEXT:
{parent_task}

"""
            if files:
                task_description += f"""
RELATED FILES:
{', '.join(files)}

"""
            if dependencies:
                task_description += f"""
DEPENDENCIES:
{dependencies}

"""
            if constraints:
                task_description += f"""
CONSTRAINTS:
{constraints}
"""

            # Execute subtask
            result = sub_agent.run(task_description)

            return {
                "success": True,
                "stdout": f"Code Development Subtask Results:\n\n{result}",
                "stderr": ""
            }

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "error": f"Failed to execute code development subtask: {str(e)}"
            }
