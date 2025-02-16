#!/usr/bin/env python3
import argparse
import os
import sys
import readline
from typing import Optional
from yaspin import yaspin # type: ignore
from yaspin.spinners import Spinners # type: ignore

from jarvis.models.registry import PlatformRegistry
from jarvis.utils import PrettyOutput, OutputType, get_shell_name, init_env

def execute_command(command: str) -> None:
    """Show command and allow user to edit, then execute, Ctrl+C to cancel"""
    try:
        print("Generated command (can be edited, press Enter to execute, Ctrl+C to cancel):")
        # Pre-fill input line
        readline.set_startup_hook(lambda: readline.insert_text(command))
        try:
            edited_command = input("> ")
            if edited_command.strip():  # Ensure command is not empty
                os.system(edited_command)
        except KeyboardInterrupt:
            print("Execution cancelled")
        finally:
            readline.set_startup_hook()  # Clear pre-filled
    except Exception as e:
        PrettyOutput.print(f"Failed to execute command: {str(e)}", OutputType.ERROR)


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
        model.set_suppress_output(True)

        shell = get_shell_name()
        current_path = os.getcwd()
        
        # Set system prompt
        system_message = f"""You are a shell command generation assistant.

Your only task is to convert user's natural language requirements into corresponding shell commands.

Strict requirements:
1. Only return the shell command itself
2. Do not add any markers (like ```, /**/, // etc.)
3. Do not add any explanations or descriptions
4. Do not add any line breaks or extra spaces
5. If multiple commands are needed, connect them with &&

Example input:
"Find all Python files in the current directory"

Example output:
find . -name "*.py"

Remember: Only return the command itself, without any additional content.
"""
        model.set_system_message(system_message)

        prefix = f"Current path: {current_path}\n"
        prefix += f"Current shell: {shell}\n"
        
        # 使用yaspin显示Thinking状态
        with yaspin(Spinners.dots, text="Thinking", color="yellow") as spinner:
            # 处理请求
            result = model.chat_until_success(prefix + request)
            
            # 提取命令
            if result and isinstance(result, str):
                command = result.strip()
                spinner.ok("✓")
                return command
            
            spinner.fail("✗")
            return None
        
    except Exception as e:
        PrettyOutput.print(f"Failed to process request: {str(e)}", OutputType.ERROR)
        return None

def main():
    # 创建参数解析器
    init_env()
    parser = argparse.ArgumentParser(
        description="Convert natural language requirements to shell commands",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  %(prog)s "Find all Python files in the current directory"
  %(prog)s "Compress all jpg images"
  %(prog)s "Find documents modified in the last week"
""")
    
    # 添加参数
    parser.add_argument(
        "request",
        help="Describe the operation you want to perform in natural language"
    )
    
    # 解析参数
    args = parser.parse_args()
    
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
