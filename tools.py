from typing import Dict, Any, Callable
import subprocess
import signal
import math
from io import StringIO
import contextlib

class Tool:
    """Tool class for agent to use"""
    
    def __init__(self, tool_id: str, name: str, description: str, parameters: Dict[str, str]):
        """Initialize tool"""
        self.tool_id = tool_id
        self.name = name
        self.description = description
        self.parameters = parameters
    
    def get_description(self) -> str:
        """Get tool description"""
        params_desc = "\n  Parameters:\n    " + "\n    ".join(
            f"- {name}: {desc}" for name, desc in self.parameters.items()
        )
        return f"- {self.tool_id}: {self.description}\n{params_desc}"
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute tool with parameters"""
        raise NotImplementedError("Tool must implement execute method")

class ShellTool(Tool):
    def __init__(self, tool_id: str = "shell"):
        super().__init__(
            tool_id=tool_id,
            name="Shell Command Execution",
            description="Execute shell commands",
            parameters={
                "command": "Shell command to execute",
                "timeout": "Timeout in seconds (optional, default 30)"
            }
        )
    
    def execute(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute shell command with timeout"""
        try:
            # Run command with timeout
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

class PythonTool(Tool):
    def __init__(self, tool_id: str = "python"):
        super().__init__(
            tool_id=tool_id,
            name="Python Code Execution",
            description="Execute Python code",
            parameters={
                "code": "Python code to execute",
                "timeout": "Timeout in seconds (optional, default 30)"
            }
        )
    
    def execute(self, code: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute Python code with timeout"""
        stdout = StringIO()
        stderr = StringIO()
        
        try:
            # Execute code with timeout and capture output
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

class MathTool(Tool):
    def __init__(self, tool_id: str = "math"):
        super().__init__(
            tool_id=tool_id,
            name="Math Expression Evaluation",
            description="Safely evaluate mathematical expressions",
            parameters={
                "expression": "Mathematical expression to evaluate"
            }
        )
        
        # Define allowed math functions and constants
        self.math_globals = {
            "abs": abs, "round": round, "min": min, "max": max,
            "sqrt": math.sqrt, "pow": math.pow, "exp": math.exp,
            "log": math.log, "log10": math.log10,
            "sin": math.sin, "cos": math.cos, "tan": math.tan,
            "asin": math.asin, "acos": math.acos, "atan": math.atan,
            "pi": math.pi, "e": math.e
        }
    
    def execute(self, expression: str) -> Dict[str, Any]:
        """Safely evaluate mathematical expression"""
        try:
            code = compile(expression, "<string>", "eval")
            
            for name in code.co_names:
                if name not in self.math_globals:
                    return {
                        "success": False,
                        "error": f"Function '{name}' is not allowed",
                        "result": {
                            "stdout": "",
                            "stderr": f"Function '{name}' is not allowed. Allowed functions: {list(self.math_globals.keys())}",
                            "returncode": 1,
                            "expression": expression
                        }
                    }
            
            result = eval(code, {"__builtins__": {}}, self.math_globals)
            
            return {
                "success": True,
                "result": {
                    "stdout": str(result),
                    "stderr": "",
                    "returncode": 0,
                    "expression": expression,
                    "value": result,
                    "type": type(result).__name__
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "result": {
                    "stdout": "",
                    "stderr": str(e),
                    "returncode": 1,
                    "expression": expression,
                    "error_type": type(e).__name__
                }
            }

class ToolRegistry:
    """Tool registry to manage available tools"""
    
    def __init__(self):
        self.tools = {}
    
    def register(self, tool: Tool):
        """Register a tool"""
        self.tools[tool.tool_id] = tool
    
    def get_tool(self, name: str) -> Tool:
        """Get tool by name"""
        return self.tools.get(name)
    
    def get_tools_description(self) -> str:
        """Get description of all registered tools"""
        return "\n".join(tool.get_description() for tool in self.tools.values())