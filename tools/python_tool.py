from io import StringIO
import contextlib
from typing import Dict, Any
from .base import Tool

class PythonTool(Tool):
    def __init__(self, tool_id: str = "python"):
        examples = {
            "Simple calculation": 'code: "print(2 + 2)"',
            "String manipulation": '''code: """
text = "Hello, World!"
print(text.upper())
"""''',
            "List operations": '''code: """
numbers = [1, 2, 3, 4, 5]
print(f"Sum: {sum(numbers)}")
print(f"Average: {sum(numbers)/len(numbers)}")
"""''',
            "File reading": '''code: """
with open('file.txt', 'r') as f:
    print(f.read())
"""''',
            "With timeout": '''code: """
import time
for i in range(5):
    print(i)
    time.sleep(1)
""", timeout: 10'''
        }
        
        super().__init__(
            tool_id=tool_id,
            name="Python Code Execution",
            description=(
                "Execute Python code snippets in a safe environment. "
                "Supports multi-line code, standard library imports, and output capture. "
                "Use this for complex calculations, data processing, and algorithmic tasks."
            ),
            parameters={
                "code": "Python code to execute (required)",
                "timeout": "Timeout in seconds (optional, default 30)"
            },
            examples=examples
        )
    
    def execute(self, code: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute Python code with timeout"""
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
                "success": True,
                "result": {
                    "stdout": stdout.getvalue(),
                    "stderr": str(e),
                    "returncode": 1,
                    "code": code
                }
            } 