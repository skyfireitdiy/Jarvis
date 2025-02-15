from typing import Dict, Any
import os
from jarvis.utils import PrettyOutput, OutputType

class ChdirTool:
    name = "chdir"
    description = "Change current working directory"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to switch to, supports both relative and absolute paths"
            }
        },
        "required": ["path"]
    }
    
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            path = os.path.expanduser(args["path"].strip())
            path = os.path.abspath(path)
            
            if not os.path.exists(path):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Directory does not exist: {path}"
                }
                
            if not os.path.isdir(path):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"The path is not a directory: {path}"
                }
                
            old_path = os.getcwd()
            os.chdir(path)
            
            return {
                "success": True,
                "stdout": f"Changed working directory:\nFrom: {old_path}\nTo: {path}",
                "stderr": ""
            }
            
        except PermissionError:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"No permission to access directory: {path}"
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to switch directory: {str(e)}"
            }
