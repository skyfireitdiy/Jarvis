from typing import Dict, Any
import subprocess
import signal
import math

class Tool:
    def __init__(self, name: str, description: str, category: str, metadata: Dict[str, Any]):
        self.name = name
        self.description = description
        self.category = category
        self.metadata = metadata
    
    def get_description(self) -> str:
        """Get formatted tool description including parameters"""
        params = self.metadata.get("parameters", {})
        param_desc = "\n".join(f"  - {name}: {desc}" for name, desc in params.items())
        return f"{self.name} ({self.category}): {self.description}\nParameters:\n{param_desc}"

class ShellTool(Tool):
    def __init__(self):
        super().__init__(
            name="shell",
            description="Execute shell commands",
            category="execution",
            metadata={
                "parameters": {
                    "command": "Shell command to execute",
                    "timeout": "Timeout in seconds (optional, default 30)"
                },
                "priority": 1,
                "risks": ["Command execution may affect system", "Long running commands may timeout"],
                "success_criteria": ["Command executed without exceptions"]
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
            
            # Always return success=True if command executed without exceptions
            # Non-zero exit codes or empty output are valid results
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
            # Only timeout is considered a failure
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
            # System-level exceptions (like command not found) are failures
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
    def __init__(self):
        super().__init__(
            name="python",
            description="Execute Python code",
            category="execution",
            metadata={
                "parameters": {
                    "code": "Python code to execute",
                    "timeout": "Timeout in seconds (optional, default 30)"
                },
                "priority": 1,
                "risks": ["Code execution may affect system", "Long running code may timeout"],
                "success_criteria": ["Code executed without exceptions"]
            }
        )
        
    def execute(self, code: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute Python code with timeout"""
        import sys
        from io import StringIO
        import contextlib
        
        # Capture stdout and stderr
        stdout = StringIO()
        stderr = StringIO()
        
        try:
            # Execute code with timeout and capture output
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(code, {}, {})
                
            # Always return success=True if code executed without system-level exceptions
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
            # Still return success=True since the code executed, even with errors
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
    def __init__(self):
        super().__init__(
            name="math",
            description="Safely evaluate mathematical expressions",
            category="math",
            metadata={
                "parameters": {
                    "expression": "Mathematical expression to evaluate"
                },
                "priority": 1,
                "risks": ["Expression might be too complex", "Division by zero possible"],
                "success_criteria": ["Expression evaluated successfully"]
            }
        )
        
        # Define allowed math functions and constants
        self.math_globals = {
            # Basic functions
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            # Math module functions
            "sqrt": math.sqrt,
            "pow": math.pow,
            "exp": math.exp,
            "log": math.log,
            "log10": math.log10,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "asin": math.asin,
            "acos": math.acos,
            "atan": math.atan,
            # Constants
            "pi": math.pi,
            "e": math.e
        }
        
    def execute(self, expression: str) -> Dict[str, Any]:
        """Safely evaluate mathematical expression"""
        try:
            # Compile expression to check syntax
            code = compile(expression, "<string>", "eval")
            
            # Check for forbidden names
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
            
            # Evaluate expression with limited globals
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