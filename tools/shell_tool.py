import subprocess
from typing import Dict, Any
from .base import Tool, tool

@tool(tool_id="shell", name="Shell Command Execution")
class ShellTool(Tool):
    """Execute shell commands with safety constraints.
    
    IMPORTANT RULES:
    1. Commands MUST NOT be long-running or take too long to execute
    2. Each command has a strict timeout limit (default 30 seconds)
    3. Commands should be simple and complete quickly
    4. For long-running tasks, break them into smaller steps
    5. Background processes and daemons are NOT allowed
    
    Examples of VALID commands:
    - "ls -la"           (List files)
    - "pwd"             (Show current directory) 
    - "cat file.txt"    (Read file content)
    - "echo 'test'"     (Print text)
    
    Examples of INVALID commands:
    - "while true; do echo 'loop'; done"  (Infinite loop)
    - "sleep 100"                         (Long delay)
    - "npm install"                       (Long package install)
    - "python train.py"                   (Long training job)
    - "mongod"                            (Background daemon)
    - "ping www.baidu.com"                (Long-running command)
    """
    
    def __init__(self, tool_id: str = "shell"):
        examples = {
            "List files": 'command: "ls -la"',
            "Show directory": 'command: "pwd"',
            "Read file": 'command: "cat file.txt"',
            "With timeout": 'command: "sleep 5", timeout: 10'
        }
        
        super().__init__(
            tool_id=tool_id,
            name="Shell Command Execution",
            description=(
                "Execute shell commands with built-in safety constraints and timeout protection. "
                "Commands MUST complete quickly (default 30s timeout). "
                "Long-running commands, background processes, and daemons are NOT allowed. "
                "Break long tasks into smaller steps."
            ),
            parameters={
                "command": "Shell command to execute (required)",
                "timeout": "Timeout in seconds (optional, default: 30)"
            },
            examples=examples
        )
    
    def execute(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute a shell command
        
        Args:
            command (str): Shell command to execute (REQUIRED)
            timeout (int, optional): Timeout in seconds. Defaults to 30.
            
        Returns:
            Dict[str, Any]: Result containing stdout, stderr, and return code
        """
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