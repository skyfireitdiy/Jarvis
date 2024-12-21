from io import StringIO
import contextlib
from typing import Dict, Any
from .base import Tool, tool

@tool(tool_id="python", name="Python Code Execution")
class PythonTool(Tool):
    """Execute Python code in a secure environment."""
    
    def __init__(self, tool_id: str = "python"):
        examples = {
            "basic": 'code: "print(sum([1, 2, 3]))"'
        }
        
        super().__init__(
            tool_id=tool_id,
            name="Python Code Execution",
            description=(
                "Execute Python code in a secure environment.\n"
                "\n"
                "Features:\n"
                "• Standard library only\n"
                "• Basic data processing\n"
                "• Text manipulation\n"
                "• List/dict operations\n"
                "\n"
                "Limitations:\n"
                "• No external packages\n"
                "• No file operations\n"
                "• No system commands\n"
                "• No interactive input"
            ),
            parameters={
                "code": "Python code to execute (required)",
                "timeout": "Execution timeout in seconds (optional, default 30)"
            },
            examples=examples
        )
    
    def execute(self, code: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute Python code"""
        stdout = StringIO()
        stderr = StringIO()
        
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(code, {}, {})
                
            return {
                "success": True,
                "result": {
                    "stdout": stdout.getvalue(),
                    "stderr": stderr.getvalue(),
                    "returncode": 0,
                    "code": code
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "result": {
                    "stdout": stdout.getvalue(),
                    "stderr": str(e),
                    "returncode": 1,
                    "code": code
                }
            } 