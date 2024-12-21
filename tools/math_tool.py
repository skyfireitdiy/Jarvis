import math
import logging
from typing import Dict, Any
from .base import Tool, tool

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@tool(tool_id="math", name="Math Operations")
class MathTool(Tool):
    """Execute mathematical calculations."""
    
    def __init__(self, tool_id: str = "math"):
        examples = {
            "basic": 'expression: "2 + 2"'
        }
        
        super().__init__(
            tool_id=tool_id,
            name="Math Expression Evaluation",
            description=(
                "Evaluate direct mathematical expressions.\n"
                "\n"
                "Supports: +, -, *, /, **, sqrt, sin, cos, tan, log\n"
                "Constants: pi, e\n"
                "\n"
                "Rules:\n"
                "• Only direct calculations\n"
                "• No variables or assignments\n"
                "• Single line expressions only"
            ),
            parameters={
                "expression": "Math expression to evaluate (required)",
                "precision": "Decimal places (optional, default 4)"
            },
            examples=examples
        )
    
    def _validate_expression(self, expression: str) -> bool:
        """Validate math expression before execution"""
        # 定义合法字符集
        valid_chars = set('0123456789.+-*/()= \t\n' + 
                         'abcdefghijklmnopqrstuvwxyz' +  # 函数名如 sqrt, sin 等
                         'ABCDEFGHIJKLMNOPQRSTUVWXYZ_')  # 常量名如 pi, e 等
        
        # 检查是否只包含合法字符
        invalid_chars = set(expression) - valid_chars
        if invalid_chars:
            return False, f"Invalid characters in expression: {', '.join(invalid_chars)}"
        
        # 检查括号匹配
        if expression.count('(') != expression.count(')'):
            return False, "Unmatched parentheses in expression"
        
        # 检查基本语法
        try:
            compile(expression, '<string>', 'eval')
            return True, ""
        except SyntaxError:
            return False, "Invalid expression syntax"
    
    def execute(self, expression: str, precision: int = 4) -> Dict[str, Any]:
        """Execute math expression"""
        # 验证表达式
        is_valid, error_msg = self._validate_expression(expression)
        if not is_valid:
            return {
                "success": False,
                "error": error_msg,
                "result": {
                    "stderr": error_msg,
                    "returncode": -1,
                    "expression": expression,
                    "precision": precision
                }
            }
        
        try:
            # Validate expression
            if "=" in expression or ";" in expression or "\n" in expression:
                raise ValueError("Invalid expression: No assignments, semicolons, or multiple lines allowed")
            
            # Create safe math context
            math_context = {
                'sin': math.sin,
                'cos': math.cos,
                'tan': math.tan,
                'sqrt': math.sqrt,
                'log': math.log,
                'log10': math.log10,
                'pi': math.pi,
                'e': math.e,
                'abs': abs,
                'pow': pow
            }
            
            # Evaluate expression in restricted context
            result = eval(expression, {"__builtins__": {}}, math_context)
            
            # Round if numeric
            if isinstance(result, (int, float)):
                result = round(result, precision)
            
            return {
                "success": True,
                "result": {
                    "stdout": str(result),
                    "stderr": "",
                    "returncode": 0,
                    "expression": expression,
                    "precision": precision
                }
            }
            
        except Exception as e:
            error_msg = str(e)
            if "=" in expression:
                error_msg = "Variables and assignments are not allowed"
            elif ";" in expression or "\n" in expression:
                error_msg = "Only single-line direct calculations are allowed"
                
            return {
                "success": False,
                "error": error_msg,
                "result": {
                    "stdout": "",
                    "stderr": error_msg,
                    "returncode": -1,
                    "expression": expression,
                    "precision": precision
                }
            }
    