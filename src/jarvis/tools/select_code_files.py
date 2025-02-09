from typing import Dict, Any, List

from jarvis.utils import OutputType, PrettyOutput
from jarvis.jarvis_coder.file_select import select_files


class CodeFileSelecterTool:
    name = "select_code_files"
    description = "Select and manage code files for modification with interactive file selection"
    parameters = {
        "type": "object",
        "properties": {
            "related_files": {
                "type": "array",
                "items": {
                    "type": "string",
                },
                "description": "List of initially related files",
                "default": []
            },
            "root_dir": {
                "type": "string",
                "description": "Root directory of the codebase",
                "default": "."
            }
        },
        "required": ["related_files"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute interactive file selection"""
        try:
            related_files = args["related_files"]
            root_dir = args.get("root_dir", ".")

            PrettyOutput.print("Starting interactive file selection...", OutputType.INFO)

            # Use file_select module to handle file selection
            selected_files = select_files(
                related_files=related_files,
                root_dir=root_dir
            )

            # Format output for display
            output = "Selected files:\n"
            for file in selected_files:
                output += f"- {file}\n"

            return {
                "success": True,
                "stdout": output,
                "stderr": "",
                "selected_files": selected_files  # Return the selected files for other tools to use
            }

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "error": f"Failed to select files: {str(e)}",
                "stdout": "",
                "stderr": str(e),
                "selected_files": []  # Return empty list on error
            }
