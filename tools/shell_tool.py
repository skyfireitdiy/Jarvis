import subprocess
from typing import Dict, Any
from .base import Tool, tool

@tool(tool_id="shell", name="Shell Command Execution")
class ShellTool(Tool):
    """执行Shell命令工具。
    
    重要规则：
    1. 命令不能长时间运行
    2. 每个命令都有严格的超时限制（默认30秒）
    3. 命令应该简单且能快速完成
    4. 对于长时间任务，需要拆分成更小的步骤
    5. 不允许后台进程和守护进程
    """
    
    def __init__(self, tool_id: str = "shell"):
        examples = {
            "列出文件": 'command: "ls -la"',
            "显示目录": 'command: "pwd"',
            "读取文件": 'command: "cat file.txt"',
            "带超时": 'command: "sleep 5", timeout: 10'
        }
        
        super().__init__(
            tool_id=tool_id,
            name="Shell命令执行",
            description=(
                "执行Shell命令，内置安全限制和超时保护。\n"
                "命令必须快速完成（默认30秒超时）。\n"
                "\n"
                "使用规则：\n"
                "1. 命令必须快速完成执行\n"
                "2. 不允许长时间运行的命令\n"
                "3. 不允许后台进程和守护进程\n"
                "4. 长任务需要拆分成小步骤\n"
                "\n"
                "有效命令示例：\n"
                '- "ls -la"           # 列出文件\n'
                '- "pwd"             # 显示当前目录\n'
                '- "cat file.txt"    # 读取文件内容\n'
                '- "echo \'test\'"     # 打印文本\n'
                "\n"
                "无效命令示例：\n"
                '- "while true; do echo \'loop\'; done"  # 无限循环\n'
                '- "sleep 100"                         # 长时间延迟\n'
                '- "npm install"                       # 长时间安装\n'
                '- "python train.py"                   # 长时间训练\n'
                '- "mongod"                            # 后台守护进程\n'
                '- "ping www.baidu.com"                # 持续运行命令'
            ),
            parameters={
                "command": "要执行的Shell命令（必需）",
                "timeout": "超时时间，单位秒（可选，默认30）"
            },
            examples=examples
        )
    
    def execute(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        """执行Shell命令
        
        参数：
            command (str): 要执行的Shell命令（必需）
            timeout (int, optional): 超时时间（秒）。默认30秒。
            
        返回：
            Dict[str, Any]: 包含标准输出、标准错误和返回码的结果
        """
        try:
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
                "error": f"命令在 {timeout} 秒后超时",
                "result": {
                    "stdout": "",
                    "stderr": f"{timeout}秒后超时",
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