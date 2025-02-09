from typing import Dict, Any

from jarvis.agent import Agent
from jarvis.utils import OutputType, PrettyOutput
from jarvis.jarvis_coder.plan_generator import PlanGenerator


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
            "related_files": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "description": "List of related files",
                "default": []
            },
            "additional_info": {
                "type": "string",
                "description": "Additional information or context for the plan generation",
                "default": ""
            }
        },
        "required": ["task"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Create a detailed code modification plan using PlanGenerator"""
        try:
            task = args["task"]
            related_files = args.get("related_files", [])
            additional_info = args.get("additional_info", "")

            PrettyOutput.print("Creating code modification plan...", OutputType.INFO)

            # Create plan generator instance
            plan_generator = PlanGenerator()

            # Generate plan
            structured_plan = plan_generator.generate_plan(
                feature=task,
                related_files=related_files
            )

            if not structured_plan:
                return {
                    "success": False,
                    "error": "Failed to generate modification plan or plan was cancelled"
                }

            # Format the output
            output = "CODE MODIFICATION PLAN\n\n"
            output += "1. ANALYSIS\n"
            output += "Task Description:\n"
            output += f"{task}\n\n"

            output += "2. MODIFICATION DETAILS\n"
            
            for file_path, modification in structured_plan.items():
                output += f"- {file_path}\n"
                output += f"  {modification}\n"

            if additional_info:
                output += "\n3. ADDITIONAL CONTEXT\n"
                output += f"{additional_info}\n"

            output += "\n4. FILES TO BE MODIFIED\n"
            for file_path in structured_plan.keys():
                output += f"- {file_path}\n"

            return {
                "success": True,
                "stdout": output,
                "stderr": "",
                "plan": structured_plan  # Include structured plan for other tools to use
            }

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "error": f"Failed to create code modification plan: {str(e)}"
            }
