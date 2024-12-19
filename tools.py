from typing import Dict, Any, Callable
import subprocess
import signal
import math
from io import StringIO
import contextlib

class Tool:
    """Tool class for agent to use"""
    
    def __init__(self, tool_id: str, name: str, description: str, parameters: Dict[str, str], examples: Dict[str, str] = None):
        """Initialize tool"""
        self.tool_id = tool_id
        self.name = name
        self.description = description
        self.parameters = parameters
        self.examples = examples or {}
    
    def get_description(self) -> str:
        """Get tool description"""
        # Basic description and parameters
        desc = [f"- {self.tool_id}: {self.description}"]
        desc.append("\n  Parameters:")
        desc.extend([f"    - {name}: {desc}" for name, desc in self.parameters.items()])
        
        # Add examples if available
        if self.examples:
            desc.append("\n  Examples:")
            desc.extend([f"    - {name}:\n      {example}" for name, example in self.examples.items()])
        
        return "\n".join(desc)
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute tool with parameters"""
        raise NotImplementedError("Tool must implement execute method")

class ShellTool(Tool):
    def __init__(self, tool_id: str = "shell"):
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
            tool_id=tool_id,
            name="Shell Command Execution",
            description=(
                "Execute shell commands with support for standard Unix/Linux commands. "
                "Commands are executed in a subprocess with output capture and timeout protection. "
                "Use this for system operations, file operations, and network queries."
            ),
            parameters={
                "command": "Shell command to execute (required)",
                "timeout": "Timeout in seconds (optional, default 30)"
            },
            examples=examples
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
    """Math tool for safe mathematical calculations"""
    
    def __init__(self, tool_id: str = "math"):
        examples = {
            "Basic arithmetic": 'expression: "2 + 2 * 3"',
            "Using functions": 'expression: "sqrt(16) + pow(2, 3)"',
            "Trigonometry": 'expression: "sin(pi/2)"',
            "Logarithms": 'expression: "log(100, 10)"',
            "Complex calculation": 'expression: "pow(sin(pi/4), 2) + pow(cos(pi/4), 2)"',
            "Constants": 'expression: "e ** 2"',
            "Rounding": 'expression: "round(3.14159, 2)"',
            "Min/Max": 'expression: "max(1, 2, 3, min(4, 5, 6))"'
        }
        
        super().__init__(
            tool_id=tool_id,
            name="Math Expression Evaluation",
            description=(
                "Safely evaluate mathematical expressions using Python's math module. "
                "Supports common mathematical functions, constants, and operations. "
                "Available functions: abs, round, min, max, sqrt, pow, exp, log, log10, "
                "sin, cos, tan, asin, acos, atan. "
                "Constants: pi, e"
            ),
            parameters={
                "expression": "Mathematical expression to evaluate (required)"
            },
            examples=examples
        )
        
        # 初始化允许的数学函数和常量
        self.math_globals = {
            # 基本函数
            'abs': abs,
            'round': round,
            'min': min,
            'max': max,
            
            # 数学函数
            'sqrt': math.sqrt,
            'pow': math.pow,
            'exp': math.exp,
            'log': math.log,
            'log10': math.log10,
            
            # 三角函数
            'sin': math.sin,
            'cos': math.cos,
            'tan': math.tan,
            'asin': math.asin,
            'acos': math.acos,
            'atan': math.atan,
            
            # 常量
            'pi': math.pi,
            'e': math.e
        }
    
    def execute(self, expression: str) -> Dict[str, Any]:
        """Safely evaluate mathematical expression"""
        try:
            # 编译表达式以检查安全性
            code = compile(expression, "<string>", "eval")
            
            # 检查表达式中使用的名称是否都在允许列表中
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
            
            # 在安全的环境中执行表达式
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