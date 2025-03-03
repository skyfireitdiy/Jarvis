from typing import Dict, Any
import os
from jarvis.jarvis_utils import PrettyOutput, OutputType

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
        """Execute directory change operation with comprehensive error handling.
        
        Args:
            args: Dictionary containing 'path' key with target directory path
            
        Returns:
            Dictionary containing:
                - success: Boolean indicating operation status
                - stdout: Success message or empty string
                - stderr: Error message or empty string
                
        Raises:
            Handles and returns appropriate error messages for:
                - Non-existent paths
                - Non-directory paths
                - Permission errors
                - Generic exceptions
        """
        # Main execution block with comprehensive error handling
        try:
            # Normalize and expand the input path (handles ~ and relative paths)
            path = os.path.expanduser(args["path"].strip())
            path = os.path.abspath(path)
            
            # Validate that the target path exists
            if not os.path.exists(path):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Directory does not exist: {path}"
                }
                
            # Ensure the path points to a directory, not a file
            if not os.path.isdir(path):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"The path is not a directory: {path}"
                }
                
            # Capture current directory and attempt to change to new path
            old_path = os.getcwd()
            os.chdir(path)
            
            return {
                "success": True,
                "stdout": f"Changed working directory:\nFrom: {old_path}\nTo: {path}",
                "stderr": ""
            }
            
        # Handle cases where user lacks directory access permissions
        except PermissionError:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"No permission to access directory: {path}"
            }
        # Catch-all for any other unexpected errors during directory change
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to switch directory: {str(e)}"
            }
