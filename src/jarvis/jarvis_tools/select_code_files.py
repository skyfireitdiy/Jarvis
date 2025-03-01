from typing import Dict, Any

from jarvis.jarvis_utils import OutputType, PrettyOutput
from jarvis.jarvis_code_agent.file_select import select_files


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
            related_files = args.get("related_files", [])
            root_dir = args.get("root_dir", ".").strip()

            PrettyOutput.print("开始交互式文件选择...", OutputType.INFO)

            
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
                "stderr": ""
            }

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e)
            }
