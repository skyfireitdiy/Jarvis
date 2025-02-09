from typing import Dict, Any

from jarvis.agent import Agent
from jarvis.utils import OutputType, PrettyOutput
from jarvis.jarvis_code_agent.main import system_prompt


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
            "codebase_dir": {
                "type": "string",
                "description": "Directory containing the codebase",
                "default": "."
            }
        },
        "required": ["subtask"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute code development subtask"""
        try:
            subtask = args["subtask"]
            codebase_dir = args.get("codebase_dir", ".")

            PrettyOutput.print(f"Creating code sub-agent for subtask: {subtask}", OutputType.INFO)

            # Create sub-agent
            sub_agent = Agent(
                system_prompt=system_prompt,
                name="CodeSubAgent",
                is_sub_agent=True
            )

            # Execute subtask
            result = sub_agent.run(subtask)

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
