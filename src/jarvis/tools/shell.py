from typing import Dict, Any
import subprocess
from ..utils import PrettyOutput, OutputType

class ShellTool:
    name = "execute_shell"
    description = """Execute shell commands and return the results.
    Guidelines for output optimization:
    1. Use grep/awk/sed to filter output when possible
    2. Avoid listing all files/dirs unless specifically needed
    3. Prefer -q/--quiet flags when status is all that's needed
    4. Use head/tail to limit long outputs
    5. Redirect stderr to /dev/null for noisy commands
    
    Examples of optimized commands:
    - 'ls -l file.txt' instead of 'ls -l'
    - 'grep -c pattern file' instead of 'grep pattern file'
    - 'ps aux | grep process | head -n 5' instead of 'ps aux'
    - 'command 2>/dev/null' to suppress error messages
    - 'df -h . ' instead of 'df -h'
    """
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute (use filters/limits for large outputs)"
            },
            "timeout": {
                "type": "integer",
                "description": "Command execution timeout in seconds",
                "default": 30
            }
        },
        "required": ["command"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """执行shell命令"""
        try:
            # 获取参数
            command = args["command"]
            timeout = args.get("timeout", 30)
            
            # 执行命令
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            # 构建输出
            output = []
            
            # 添加命令信息
            PrettyOutput.print(f"执行命令: {command}", OutputType.INFO)
            output.append(f"命令: {command}")
            output.append("")
            
            # 添加输出
            if result.stdout:
                output.append(result.stdout)
            
            return {
                "success": True,
                "stdout": "\n".join(output),
                "stderr": result.stderr,
                "return_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"命令执行超时 (>{timeout}秒)"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            } 