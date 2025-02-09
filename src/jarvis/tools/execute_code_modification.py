from typing import Dict, Any

from jarvis.agent import Agent
from jarvis.utils import OutputType, PrettyOutput
from jarvis.jarvis_coder.patch_handler import PatchHandler


class CodeModifyTool:
    name = "execute_code_modification"
    description = "Execute code modifications according to the provided plan"
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The code modification task description"
            },
            "structured_plan": {
                "type": "object",
                "description": "Dictionary mapping file paths to their modification plans. Example: {'path/to/file.py': 'Add function foo() to handle...'}", 
                "additionalProperties": {
                    "type": "string",
                    "description": "Modification plan for a specific file"
                },
                "examples": [{
                    "src/file1.py": "Add error handling to process_data()",
                    "src/file2.py": "Update API endpoint URL in get_data()"
                }]
            }
        },
        "required": ["task", "raw_plan", "structured_plan"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute code modifications using PatchHandler"""
        try:
            task = args["task"]
            structured_plan = args["structured_plan"]

            PrettyOutput.print("Executing code modifications...", OutputType.INFO)

            # Create patch handler instance
            patch_handler = PatchHandler()

            # Apply patches and handle the process
            success, additional_info = patch_handler.handle_patch_application(
                feature=task,
                structed_plan=structured_plan
            )

            if not success:
                return {
                    "success": False,
                    "stdout": "Changes have been rolled back",
                    "stderr": additional_info
                }

            return {
                "success": True,
                "stdout": "Code modifications have been successfully applied and committed",
                "stderr": additional_info
            }

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to execute code modifications: {str(e)}"
            }
