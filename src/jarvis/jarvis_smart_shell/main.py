#!/usr/bin/env python3
import argparse
import os
import sys
from typing import Optional

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import get_shell_name
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.utils import init_env

def execute_command(command: str, should_run: bool) -> None:
    """Print command without execution"""
    print(command)
    if should_run:
        os.system(command)


def install_fish_completion() -> int:
    """Install fish shell command completion with interactive choice
    
    Returns:
        int: 0 if success, 1 if failed
    """
    if get_shell_name() != "fish":
        print("当前不是fish shell，无需安装")
        return 0
        
    # 使用fish命令检查函数是否已加载
    check_cmd = 'functions --names | grep fish_command_not_found > /dev/null && echo "defined" || echo "undefined"'
    result = os.popen(f'fish -c \'{check_cmd}\'').read().strip()
    
    if result == "defined":
        print("fish_command_not_found函数已加载，无需安装")
        return 0
        
    config_file = os.path.expanduser("~/.config/fish/config.fish")
    
    # 检查文件内容是否已定义但未加载
    if os.path.exists(config_file):
        with open(config_file, 'r') as config:
            if "function fish_command_not_found" in config.read():
                print("fish_command_not_found函数已定义但未加载，请执行: source ~/.config/fish/config.fish")
                return 0
                
    # 创建config.fish文件如果不存在
    os.makedirs(os.path.dirname(config_file), exist_ok=True)
    
    # 追加函数定义到config.fish
    with open(config_file, 'a') as config:
        config.write("""
function fish_command_not_found
    commandline -r (jss request "$argv")
end

function __fish_command_not_found_handler --on-event fish_command_not_found
    fish_command_not_found "$argv"
end
""")
    print("Fish shell命令补全功能已安装到config.fish，请执行: source ~/.config/fish/config.fish")
    return 0


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
# 角色
将自然语言转换为shell命令

# 规则
1. 只输出命令
2. 不要解释或标记
3. 单行输出
4. 多个命令用&&连接

# 示例
输入: "查找Python文件"
输出: find . -name "*.py"
"""
        model.set_system_message(system_message)

        prefix = f"Current path: {current_path}\n"
        prefix += f"Current shell: {shell}\n"

        result = model.chat_until_success(prefix + request)

        # 提取命令
        if result and isinstance(result, str):
            command = result.strip()
            return command

        return None

    except Exception:
        return None

def main():
    # 创建参数解析器
    init_env()
    parser = argparse.ArgumentParser(
        description="将自然语言要求转换为shell命令",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  %(prog)s request "Find all Python files in the current directory"
  %(prog)s install
""")

    # 创建子命令解析器
    subparsers = parser.add_subparsers(dest='command', required=True)

    # request子命令
    request_parser = subparsers.add_parser('request', help='描述您想要执行的操作（用自然语言描述）')
    request_parser.add_argument(
        "request",
        nargs='?',  # 设置为可选参数
        help="描述您想要执行的操作（用自然语言描述），如果未提供则从标准输入读取"
    )

    # install子命令
    install_parser = subparsers.add_parser('install', help='安装fish shell的命令补全功能')


    # 解析参数
    args = parser.parse_args()

    should_run = False

    # 处理install命令
    if args.command == "install":
        return install_fish_completion()

    
    # 处理request命令
    if not args.request:
        # 检查是否在交互式终端中运行
        args.request = get_multiline_input(tip="请输入您要执行的功能：")
        should_run = True
    # 处理请求
    command = process_request(args.request)

    # 输出结果
    if command:
        execute_command(command, should_run)  # 显示并执行命令
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main())
