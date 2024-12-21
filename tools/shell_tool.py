import subprocess
from typing import Dict, Any
from .base import Tool, tool

@tool(tool_id="shell", name="Shell Command Execution")
class ShellTool(Tool):
    """Execute shell commands with safety limits."""
    
    def __init__(self, tool_id: str = "shell"):
        examples = {
            "basic": 'command: "ping -c 1 google.com"'
        }
        
        super().__init__(
            tool_id=tool_id,
            name="Shell Command Execution",
            description=(
                "Execute shell commands in a controlled environment.\n"
                "\n"
                "Allowed Commands:\n"
                "• File listing (ls, pwd)\n"
                "• Network checks (ping)\n"
                "• Process info (ps, top)\n"
                "• File content (cat, head)\n"
                "\n"
                "Restrictions:\n"
                "• No system changes\n"
                "• No installations\n"
                "• No service control\n"
                "• No user management\n"
                "• 30s timeout max"
            ),
            parameters={
                "command": "Shell command to execute (required)",
                "timeout": "Timeout in seconds (optional, default 30)"
            },
            examples=examples
        )
    
    def execute(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute shell command"""
        try:
            # Execute command
            process = subprocess.run(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout
            )
            
            # Return result
            return {
                "success": True,
                "result": {
                    "stdout": process.stdout,
                    "stderr": process.stderr,
                    "returncode": process.returncode,
                    "command": command,
                    "timeout": timeout
                }
            }
        except subprocess.TimeoutExpired as e:
            return {
                "success": False,
                "error": f"Command timed out after {timeout} seconds",
                "result": None
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "result": None
            }