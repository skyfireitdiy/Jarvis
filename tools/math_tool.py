import math
import logging
from typing import Dict, Any
from .base import Tool, tool

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@tool(tool_id="math", name="Math Expression Evaluation")
class MathTool(Tool):
    """Evaluate mathematical expressions.
    
    IMPORTANT RULES:
    1. Only supports direct numerical expressions. Variables are NOT supported.
    2. Expression MUST follow Python syntax rules:
       - Use ** for power (not ^)
       - Use * for multiplication (not ×)
       - Use / for division (not ÷)
       - Use parentheses () for grouping (not [] or {})
       - Decimal numbers use . (not ,)
    3. All numbers must be actual numeric values
    
    Supported operations:
    - Basic: +, -, *, /, %, **
    - Functions: abs(), round(), min(), max(), sum()
    - Math module functions: sqrt(), sin(), cos(), tan(), etc.
    
    Examples of VALID expressions:
    - "2 + 2"              # Basic addition
    - "10 * 5 + 3"        # Multiplication and addition
    - "2 ** 3"            # Power (2³)
    - "(10 + 5) * 2"      # Grouping with parentheses
    - "3.14 * (10 ** 2)"  # Decimal numbers with dot
    - "abs(-42)"          # Function call
    - "sqrt(16) + 2"      # Math function
    - "min(10, 5, 8)"     # Multiple arguments
    - "sin(3.14159 / 2)"  # Trigonometry
    
    Examples of INVALID expressions:
    - "x + y"              (No variables allowed)
    - "2 ^ 3"             (Use ** for power, not ^)
    - "5 × 3"             (Use * for multiplication)
    - "10 ÷ 2"            (Use / for division)
    - "3,14 * 2"          (Use . for decimals, not ,)
    - "[1 + 2] * 3"       (Use () for grouping, not [])
    - "distance * 2"       (Must use actual numbers)
    - "price + tax"        (No variable names)
    - "beijing - shanghai" (Text is not allowed)
    
    Parameters:
        expression (str): Mathematical expression to evaluate (REQUIRED)
                         Must be a valid Python mathematical expression
                         containing only numbers and supported operations
    """
    
    def execute(self, expression: str) -> Dict[str, Any]:
        """Execute the math expression
        
        Args:
            expression (str): Mathematical expression to evaluate.
                            MUST contain only numbers and supported operations.
                            Variables are NOT supported.
        
        Returns:
            Dict[str, Any]: Result containing the evaluated value
        """
        try:
            # 添加数学函数到环境中
            math_env = {
                'abs': abs,
                'min': min,
                'max': max,
                'sum': sum,
                'round': round,
                **{name: getattr(math, name) for name in dir(math) if not name.startswith('_')}
            }
            
            # 执行表达式
            result = eval(expression, {"__builtins__": {}}, math_env)
            
            return {
                "success": True,
                "result": {
                    "stdout": str(result),
                    "stderr": "",
                    "returncode": 0
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error evaluating expression: {str(e)}",
                "result": {
                    "stdout": "",
                    "stderr": f"Error evaluating expression: {str(e)}",
                    "returncode": -1
                }
            }
    