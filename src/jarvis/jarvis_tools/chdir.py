from typing import Dict, Any
import os

class ChdirTool:
    name = "chdir"
    description = "更改当前工作目录"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要切换到的目录路径，支持相对路径和绝对路径"
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
                    "stderr": f"目录不存在: {path}"
                }
                
            # Ensure the path points to a directory, not a file
            if not os.path.isdir(path):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"路径不是目录: {path}"
                }
                
            # Capture current directory and attempt to change to new path
            old_path = os.getcwd()
            os.chdir(path)
            
            return {
                "success": True,
                "stdout": f"成功切换工作目录:\n原目录: {old_path}\n新目录: {path}",
                "stderr": ""
            }
            
        # Handle cases where user lacks directory access permissions
        except PermissionError:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"无权限访问目录: {path}"
            }
        # Catch-all for any other unexpected errors during directory change
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"切换目录失败: {str(e)}"
            }