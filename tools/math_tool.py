import math
import logging
from typing import Dict, Any
from .base import Tool, tool

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@tool(tool_id="math", name="Math Operations")
class MathTool(Tool):
    """数学表达式计算工具。
    
    重要规则：
    1. 仅支持直接的数值表达式，不支持变量
    2. 表达式必须遵循 Python 语法规则：
       - 使用 ** 表示幂运算（不是 ^）
       - 使用 * 表示乘法（不是 ×）
       - 使用 / 表示除法（不是 ÷）
       - 使用小括号 () 进行分组（不是 [] 或 {}）
       - 小数使用点号 . （不是逗号 ,）
    3. 所有数字必须是实际的数值
    """
    
    def __init__(self):
        super().__init__(
            tool_id="math",
            name="数学运算",
            description=(
                "执行数学计算和运算。\n"
                "支持基本运算、三角函数、对数等。\n"
                "\n"
                "适用场景：\n"
                "- 复杂计算\n"
                "- 三角函数计算\n"
                "- 对数计算\n"
                "- 数学常量运算\n"
                "- 数值比较\n"
                "\n"
                "使用规则：\n"
                "1. 代码必须是有效的Python数学表达式\n"
                "2. 仅支持数值运算，不支持变量\n"
                "3. 比较运算返回 True/False\n"
                "4. 支持所有比较运算符：>, <, >=, <=, ==, !=\n"
                "5. 可以使用括号组合多个比较\n"
                "\n"
                "有效表达式示例：\n"
                '- "2 + 2"              # 基本加法\n'
                '- "10 * 5 + 3"        # 乘法和加法\n'
                '- "2 ** 3"            # 幂运算（2³）\n'
                '- "(10 + 5) * 2"      # 使用括号分组\n'
                '- "3.14 * (10 ** 2)"  # 使用小数点\n'
                '- "abs(-42)"          # 函数调用\n'
                '- "sqrt(16) + 2"      # 数学函数\n'
                '- "sin(3.14159 / 2)"  # 三角函数\n'
                '- "log(100)"          # 对数运算\n'
                '- "pi * 2"            # 使用常量\n'
                '- "3**20 > 2**30"     # 数值比较\n'
                '- "100 <= 2**10"      # 比较运算\n'
                '- "sqrt(100) == 10"   # 相等性检查\n'
                "\n"
                "无效表达式示例：\n"
                '- "x + y"              （不允许使用变量）\n'
                '- "2 ^ 3"             （幂运算应使用 **，不是 ^）\n'
                '- "5 × 3"             （乘法应使用 *，不是 ×）\n'
                '- "10 ÷ 2"            （除法应使用 /，不是 ÷）\n'
                '- "3,14 * 2"          （小数应使用点号，不是逗号）\n'
                '- "[1 + 2] * 3"       （应使用小括号，不是方括号）\n'
                '- "distance * 2"       （必须使用实际数值）\n'
                '- "price + tax"        （不允许使用变量名）\n'
                '- "北京 - 上海"        （不允许使用文本）'
            ),
            parameters={
                "expression": "要计算的数学表达式（必需）",
                "precision": "结果小数位数（可选，默认：4）"
            },
            examples={
                "基本运算": 'expression: "2 + 2 * 3"',
                "三角函数": 'expression: "sin(45)"',
                "对数运算": 'expression: "log(100)"',
                "指定精度": 'expression: "pi", precision: 6',
                "数值比较": 'expression: "3**20 > 2**30"',
                "复合比较": 'expression: "(2**10 > 1000) and (3**5 < 300)"'
            }
        )
    
    def execute(self, expression: str, precision: int = 4) -> Dict[str, Any]:
        """执行数学计算"""
        try:
            # 创建安全的数学上下文
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
            
            # 在安全上下文中计算表达式
            result = eval(expression, {"__builtins__": {}}, math_context)
            
            # 如果结果是数值，进行精度控制
            if isinstance(result, (int, float)):
                result = round(result, precision)
            
            # 转换结果为字符串
            result_str = str(result)
            
            return {
                "success": True,
                "result": {
                    "stdout": result_str,
                    "stderr": "",
                    "returncode": 0,
                    "expression": expression,
                    "precision": precision
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
                    "expression": expression,
                    "precision": precision
                }
            }
    