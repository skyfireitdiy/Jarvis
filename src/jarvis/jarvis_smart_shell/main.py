#!/usr/bin/env python3
import argparse
import os
import sys
import readline
from typing import Optional
from yaspin import yaspin
from yaspin.spinners import Spinners

from jarvis.models.registry import PlatformRegistry
from jarvis.utils import PrettyOutput, OutputType, load_env_from_file

def execute_command(command: str) -> None:
    """显示命令并允许用户编辑，回车执行，Ctrl+C取消"""
    try:
        print("\n生成的命令 (可以编辑，回车执行，Ctrl+C取消):")
        # 预填充输入行
        readline.set_startup_hook(lambda: readline.insert_text(command))
        try:
            edited_command = input("> ")
            if edited_command.strip():  # 确保命令不为空
                os.system(edited_command)
        except KeyboardInterrupt:
            print("\n已取消执行")
        finally:
            readline.set_startup_hook()  # 清除预填充
    except Exception as e:
        PrettyOutput.print(f"执行命令时发生错误: {str(e)}", OutputType.ERROR)

def process_request(request: str) -> Optional[str]:
    """处理用户请求并返回对应的shell命令
    
    Args:
        request: 用户的自然语言请求
        
    Returns:
        Optional[str]: 对应的shell命令，如果处理失败则返回None
    """
    try:
        # 获取语言模型实例
        PlatformRegistry.suppress_output = True
        model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
        model.set_suppress_output(True)

        shell = os.environ.get("SHELL") or "bash"
        current_path = os.getcwd()
        
        # 设置系统提示
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
        PrettyOutput.print(f"处理请求时发生错误: {str(e)}", OutputType.ERROR)
        return None

def main():
    # 创建参数解析器
    load_env_from_file()
    parser = argparse.ArgumentParser(
        description="将自然语言需求转换为shell命令",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "查找当前目录下所有的Python文件"
  %(prog)s "压缩所有jpg图片"
  %(prog)s "查找最近一周修改过的文档"
""")
    
    # 添加参数
    parser.add_argument(
        "request",
        help="用自然语言描述你需要执行的操作"
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
