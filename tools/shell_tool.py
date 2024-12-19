import subprocess
from typing import Dict, Any
from .base import Tool, tool

@tool(tool_id="shell", name="Shell Command Execution")
class ShellTool(Tool):
    tool_id = "shell"
    name = "Shell Command Execution"
    
    def __init__(self):
        examples = {
            "List files": 'command: "ls -la"',
            "Check IP address": 'command: "hostname -I"',
            "Check disk space": 'command: "df -h"',
            "Check memory usage": 'command: "free -h"',
            "Find files": 'command: "find /path -name \'*.txt\'"',
            "Process info": 'command: "ps aux | grep process_name"',
            "Network status": 'command: "netstat -tuln"',
            "With timeout": 'command: "long_running_command", timeout: 60'
        }
        
        super().__init__(
            tool_id=self.tool_id,
            name=self.name,
            description="Execute shell commands with support for standard Unix/Linux commands.",
            parameters={
                "command": "Shell command to execute (required)",
                "timeout": "Timeout in seconds (optional, default 30)"
            },
            examples=examples
        )
    
    def execute(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute shell command with timeout"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            return {
                "success": True,
                "result": {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                    "command": command
                }
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Command timed out after {timeout} seconds",
                "result": {
                    "stdout": "",
                    "stderr": f"Timeout after {timeout}s",
                    "returncode": -1,
                    "command": command
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "result": {
                    "stdout": "",
                    "stderr": str(e),
                    "returncode": -1,
                    "command": command
                }
            } 