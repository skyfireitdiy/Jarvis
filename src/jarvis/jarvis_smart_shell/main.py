#!/usr/bin/env python3
import argparse
import os
import sys
import readline
from typing import Optional

from yaspin import yaspin

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import get_shell_name
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import init_env

def execute_command(command: str) -> None:
    """Show command and allow user to edit, then execute, Ctrl+C to cancel"""
    try:
        print("生成的命令 (可以编辑, 按回车执行, Ctrl+C 取消):")
        # Pre-fill input line
        readline.set_startup_hook(lambda: readline.insert_text(command))
        try:
            edited_command = input("> ")
            if edited_command.strip():  # Ensure command is not empty
                os.system(edited_command)
        except KeyboardInterrupt:
            PrettyOutput.print("执行取消", OutputType.INFO)
        finally:
            readline.set_startup_hook()  # Clear pre-filled
    except Exception as e:
        PrettyOutput.print(f"执行命令失败: {str(e)}", OutputType.WARNING)


def process_request(request: str) -> Optional[str]:
    """Process user request and return corresponding shell command

    Args:
        request: User's natural language request

    Returns:
        Optional[str]: Corresponding shell command, return None if processing fails
    """
    try:
        # Get language model instance
        model = PlatformRegistry.get_global_platform_registry().get_normal_platform()

        shell = get_shell_name()
        current_path = os.getcwd()

        # Set system prompt
        system_message = """
# 🤖 Role Definition
You are a shell command generation expert who converts natural language requirements into precise shell commands.

# 🎯 Core Responsibilities
- Convert natural language to shell commands
- Generate accurate and efficient commands
- Follow strict output format rules
- Maintain command simplicity

# 📋 Output Requirements
## Format Rules
1. Return ONLY the command
2. NO markers (```, /*, //)
3. NO explanations
4. NO line breaks
5. NO extra spaces
6. Multiple commands: use &&

## Command Style
- Use standard shell syntax
- Keep commands concise
- Follow best practices
- Ensure proper quoting
- Handle spaces correctly

# 📝 Example Format
Input: "Find all Python files in the current directory"
Output: find . -name "*.py"

# ❗ Critical Rules
1. ONLY output the command
2. NO additional content
3. NO formatting markers
4. NO explanations
5. ONE line only

# 💡 Command Guidelines
- Use standard tools
- Prefer portable syntax
- Handle edge cases
- Escape special chars
- Quote when needed
"""
        model.set_system_message(system_message)

        prefix = f"Current path: {current_path}\n"
        prefix += f"Current shell: {shell}\n"

        with yaspin(text="正在生成命令...", color="cyan") as spinner:
            result = model.chat_until_success(prefix + request)
            spinner.ok("✅ 命令生成成功")

        # 提取命令
        if result and isinstance(result, str):
            command = result.strip()
            return command

        return None

    except Exception as e:
        PrettyOutput.print(f"处理请求失败: {str(e)}", OutputType.WARNING)
        return None

def main():
    # 创建参数解析器
    init_env()
    parser = argparse.ArgumentParser(
        description="将自然语言要求转换为shell命令",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  %(prog)s "Find all Python files in the current directory"
  %(prog)s "Compress all jpg images"
  %(prog)s "Find documents modified in the last week"
""")

    # 修改为可选参数，添加从stdin读取的支持
    parser.add_argument(
        "request",
        nargs='?',  # 设置为可选参数
        help="描述您想要执行的操作（用自然语言描述），如果未提供则从标准输入读取"
    )

    # 解析参数
    args = parser.parse_args()

    # 添加标准输入处理
    if not args.request:
        # 检查是否在交互式终端中运行
        args.request = get_multiline_input(tip="请输入您要执行的功能：")

    # 处理请求
    command = process_request(args.request)

    # 输出结果
    if command:
        execute_command(command)  # 显示并执行命令
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main())
