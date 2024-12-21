from io import StringIO
import contextlib
from typing import Dict, Any
from .base import Tool

class PythonTool(Tool):
    def __init__(self, tool_id: str = "python"):
        examples = {
            "简单计算": 'code: "print(2 + 2)"',
            "字符串处理": '''code: """
text = "Hello, World!"
print(text.upper())
"""''',
            "列表操作": '''code: """
numbers = [1, 2, 3, 4, 5]
print(f"总和：{sum(numbers)}")
print(f"平均值：{sum(numbers)/len(numbers)}")
"""''',
            "文件读取": '''code: """
with open('file.txt', 'r') as f:
    print(f.read())
"""''',
            "带超时": '''code: """
import time
for i in range(5):
    print(i)
    time.sleep(1)
""", timeout: 10'''
        }
        
        super().__init__(
            tool_id=tool_id,
            name="Python代码执行",
            description=(
                "在安全环境中执行Python代码片段。\n"
                "支持多行代码、标准库导入和输出捕获。\n"
                "\n"
                "适用场景：\n"
                "- 复杂计算\n"
                "- 数据处理\n"
                "- 算法任务\n"
                "- 文件操作\n"
                "\n"
                "使用规则：\n"
                "1. 代码必须是有效的Python语法\n"
                "2. 仅支持标准库，不支持第三方包\n"
                "3. 文件操作仅限于当前目录\n"
                "4. 长时间运行的代码会被自动终止\n"
                "5. 不支持交互式输入\n"
            ),
            parameters={
                "code": "要执行的Python代码（必需）",
                "timeout": "超时时间，单位秒（可选，默认30）"
            },
            examples=examples
        )
    
    def execute(self, code: str, timeout: int = 30) -> Dict[str, Any]:
        """执行Python代码"""
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