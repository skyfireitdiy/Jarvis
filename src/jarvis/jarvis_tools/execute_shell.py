# Shell command execution module
# 
# Provides functionality to execute shell commands safely with:
# - Command escaping
# - Output capturing
# - Temporary file management
# - Error handling
from typing import Dict, Any
import os
import tempfile
from pathlib import Path
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
class ShellTool:
    """Shell command execution tool
    
    Attributes:
        name: Tool identifier used in API
        description: Tool description for API documentation
        parameters: JSON schema for command parameters
    """
    name = "execute_shell"
    description = "执行Shell命令并返回结果"
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的Shell命令"
            }
        },
        "required": ["command"]
    }
    def _escape_command(self, cmd: str) -> str:
        """Escape special characters in command to prevent shell injection
        
        Args:
            cmd: Raw command string
            
        Returns:
            Escaped command string with single quotes properly handled
        """
        return cmd.replace("'", "'\"'\"'")
    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute shell command and capture output
        
        Steps:
        1. Validate and clean input command
        2. Create temporary file for output capture
        3. Execute command with output redirection
        4. Read and process output file
        5. Clean up temporary resources
        6. Return structured results
        
        Args:
            args: Dictionary containing 'command' parameter
            
        Returns:
            Dictionary with:
            - success: Boolean indicating command execution status
            - stdout: Command output
            - stderr: Error message if execution failed
        """
        try:
            # Get and clean command input
            command = args["command"].strip()
            
            # Generate temporary file name using process ID for uniqueness
            output_file = os.path.join(tempfile.gettempdir(), f"jarvis_shell_{os.getpid()}.log")
            
            # Escape special characters in command to prevent injection
            escaped_command = self._escape_command(command)
            
            # Use script command to capture both stdout and stderr
            tee_command = f"script -q -c '{escaped_command}' {output_file}"
            
            # Log command execution
            PrettyOutput.print(f"执行命令: {command}", OutputType.INFO)
            
            # Execute command and capture return code
            return_code = os.system(tee_command)
            
            # Read and process output file
            try:
                with open(output_file, 'r', encoding='utf-8', errors='replace') as f:
                    output = f.read()
                    # Remove header and footer added by script command
                    if output:
                        lines = output.splitlines()
                        if len(lines) > 2:
                            output = "\n".join(lines[1:-1])
            except Exception as e:
                output = f"读取输出文件失败: {str(e)}"
            finally:
                # Clean up temporary file
                Path(output_file).unlink(missing_ok=True)
            
            # Return successful result
            return {
                "success": True,
                "stdout": output,
                "stderr": "",
            }
                
        except Exception as e:
            # Ensure temporary file is cleaned up even if error occurs
            if 'output_file' in locals():
                Path(output_file).unlink(missing_ok=True)
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e)
            }