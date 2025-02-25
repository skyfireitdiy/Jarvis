from typing import Dict, Any
import os
import tempfile
from pathlib import Path

from jarvis.jarvis_utils import OutputType, PrettyOutput


class ShellTool:
    name = "execute_shell"
    description = """Execute shell command and return result"""

    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute"
            }
        },
        "required": ["command"]
    }


    def _escape_command(self, cmd: str) -> str:
        """Escape special characters in command"""
        return cmd.replace("'", "'\"'\"'")

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute shell command"""
        try:
            command = args["command"].strip()
            
            # Generate temporary file name
            output_file = os.path.join(tempfile.gettempdir(), f"jarvis_shell_{os.getpid()}.log")
            
            # Escape special characters in command
            escaped_command = self._escape_command(command)
            
            # Modify command to use script
            tee_command = f"script -q -c '{escaped_command}' {output_file}"
            
            PrettyOutput.print(f"执行命令: {command}", OutputType.INFO)
            
            # Execute command
            return_code = os.system(tee_command)
            
            # Read output file
            try:
                with open(output_file, 'r', encoding='utf-8', errors='replace') as f:
                    output = f.read()
                    # Remove header and footer added by script
                    if output:
                        lines = output.splitlines()
                        if len(lines) > 2:
                            output = "\n".join(lines[1:-1])
            except Exception as e:
                output = f"读取输出文件失败: {str(e)}"
            finally:
                # Clean up temporary file
                Path(output_file).unlink(missing_ok=True)
            
            return {
                "success": True,
                "stdout": output,
                "stderr": "",
            }
                
        except Exception as e:
            # Ensure temporary file is cleaned up
            if 'output_file' in locals():
                Path(output_file).unlink(missing_ok=True)
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e)
            } 