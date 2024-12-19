import math
import logging
from typing import Dict, Any
from .base import Tool, tool

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@tool(tool_id="math", name="Math Tool")
class MathTool(Tool):
    """Math evaluation tool"""
    
    def __init__(self):
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
            tool_id="math",
            name="Math Tool",
            description=(
                "Safely evaluate mathematical expressions using Python's math module. "
                "Supports common mathematical functions and constants."
            ),
            parameters={
                "expression": "Mathematical expression to evaluate (required)"
            },
            examples=examples
        )
        
        # Define allowed math functions and constants
        self.math_globals = {
            # Basic functions
            'abs': abs, 'round': round, 'min': min, 'max': max,
            # Math module functions
            'sqrt': math.sqrt, 'pow': math.pow,
            'exp': math.exp, 'log': math.log, 'log10': math.log10,
            'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
            'asin': math.asin, 'acos': math.acos, 'atan': math.atan,
            'degrees': math.degrees, 'radians': math.radians,
            'floor': math.floor, 'ceil': math.ceil,
            # Constants
            'pi': math.pi, 'e': math.e, 'tau': math.tau,
            'inf': math.inf, 'nan': math.nan
        }
    
    def format_math_output(self, expression: str, result: Any, steps: list = None) -> str:
        """Format math calculation output"""
        output = []
        output.append(f"Expression: {expression}")
        
        if steps:
            output.append("\nSteps:")
            for step in steps:
                output.append(f"• {step}")
        
        output.append(f"\nResult: {result}")
        
        # Add type information for better understanding
        output.append(f"Type: {type(result).__name__}")
        
        return "\n".join(output)
    
    def execute(self, expression: str) -> Dict[str, Any]:
        """Execute math expression"""
        logger.info(f"Evaluating math expression: '{expression}'")
        
        if not expression.strip():
            error_msg = "Empty expression received"
            logger.warning(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "result": {
                    "stdout": "",
                    "stderr": error_msg,
                    "returncode": -1,
                    "command": f"math expression='{expression}'",
                    "math_data": {
                        "expression": expression,
                        "result": None,
                        "type": None
                    }
                }
            }
        
        try:
            # Evaluate the expression in a safe environment
            result = eval(expression, {"__builtins__": {}}, self.math_globals)
            
            # Prepare math data
            math_data = {
                "expression": expression,
                "result": result,
                "type": type(result).__name__,
                "available_functions": list(self.math_globals.keys())
            }
            
            # Format the output
            formatted_output = self.format_math_output(expression, result)
            
            return {
                "success": True,
                "result": {
                    "stdout": formatted_output,
                    "stderr": "",
                    "returncode": 0,
                    "command": f"math expression='{expression}'",
                    "math_data": math_data
                }
            }
            
        except Exception as e:
            error_msg = f"Error evaluating expression: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "result": {
                    "stdout": "",
                    "stderr": error_msg,
                    "returncode": -1,
                    "command": f"math expression='{expression}'",
                    "math_data": {
                        "expression": expression,
                        "result": None,
                        "type": None,
                        "error": str(e)
                    }
                }
            }
            
    def get_prompt_template(self) -> str:
        """Return the prompt template for result analysis"""
        return """
CRITICAL RULES for Analysis:
1. NEVER make assumptions about results that aren't explicitly shown in the output
2. If comparing values, you MUST use the actual values from the output
3. If the command failed (success=False), you CANNOT conclude
4. All conclusions MUST be based on explicit evidence in the output
5. If output is unclear or ambiguous, you MUST request retry
6. ALL RESPONSES MUST BE IN ENGLISH
7. NEVER set can_conclude=true if ANY required information is missing
8. For comparison tasks, ALL values being compared MUST be present
9. For multi-step tasks, ALL steps must be completed before concluding
10. If task requires multiple pieces of information, ALL must be present

Please analyze this result and determine:
1. Can we draw a definitive conclusion from this output?
2. What specific information did we get from the output?
3. Are there any errors or issues we need to address?
4. Do we need to retry with a different approach?

Format your response as JSON:
{
    "can_conclude": false,  # Must be false if ANY required information is missing
    "conclusion": "Clear statement about what we found, with exact values",
    "key_info": [
        "Each piece of information found, with exact values",
        "Any errors or issues found",
        "List of missing information if any"
    ],
    "has_valid_data": true/false,
    "needs_retry": true/false,
    "validation_errors": ["Any issues with the data"],
    "missing_info": ["List all missing information required for the task"]
}
""" 