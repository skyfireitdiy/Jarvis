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
    description = "执行Shell命令并返回结果。与virtual_tty不同，此工具每次执行都是独立的命令，不会保持终端状态。适用于执行单个命令并获取结果的场景，如运行简单的系统命令。"
    labels = ['system', 'shell']
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
        try:
            # Get and clean command input
            command = args["command"].strip()

            # Generate temporary file name using process ID for uniqueness
            script_file = os.path.join(tempfile.gettempdir(), f"jarvis_shell_{os.getpid()}.sh")
            output_file = os.path.join(tempfile.gettempdir(), f"jarvis_shell_{os.getpid()}.log")

            # Write command to script file
            with open(script_file, 'w', encoding='utf-8') as f:
                f.write(f"#!/bin/bash\n{command}")

            # Use script command to capture both stdout and stderr
            tee_command = f"script -q -c 'bash {script_file}' {output_file}"

            # Execute command and capture return code
            os.system(tee_command)

            # Read and process output file
            try:
                with open(output_file, 'r', encoding='utf-8', errors='ignore') as f:
                    output = f.read()
                    # Remove header and footer added by script command (if any)
                    if output:
                        lines = output.splitlines()
                        if len(lines) > 2:
                            output = "\n".join(lines[1:-1])
            except Exception as e:
                output = f"读取输出文件失败: {str(e)}"
            finally:
                # Clean up temporary files
                Path(script_file).unlink(missing_ok=True)
                Path(output_file).unlink(missing_ok=True)

            # Return successful result
            return {
                "success": True,
                "stdout": output,
                "stderr": "",
            }

        except Exception as e:
            # Ensure temporary files are cleaned up even if error occurs
            if 'script_file' in locals():
                Path(script_file).unlink(missing_ok=True)
            if 'output_file' in locals():
                Path(output_file).unlink(missing_ok=True)
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e)
            }

