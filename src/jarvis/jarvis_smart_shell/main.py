#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import os
import sys
from typing import Optional, Tuple

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import get_shell_name, set_config
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.utils import init_env


def execute_command(command: str, should_run: bool) -> None:
    """Print command without execution"""
    print(command)
    if should_run:
        os.system(command)


def _check_fish_shell() -> bool:
    """Check if current shell is fish
    
    Returns:
        bool: True if fish shell, False otherwise
    """
    return get_shell_name() == "fish"

def _get_config_file() -> str:
    """Get fish config file path
    
    Returns:
        str: Path to fish config file
    """
    return os.path.expanduser("~/.config/fish/config.fish")

def _get_markers() -> Tuple[str, str]:
    """Get start and end markers for JSS completion
    
    Returns:
        Tuple[str, str]: (start_marker, end_marker)
    """
    return (
        "# ===== JARVIS JSS FISH COMPLETION START =====",
        "# ===== JARVIS JSS FISH COMPLETION END ====="
    )

def install_jss_completion() -> int:
    """Install JSS fish shell command completion
    
    Returns:
        int: 0 if success, 1 if failed
    """
    if not _check_fish_shell():
        print("当前不是fish shell，无需安装")
        return 0

    config_file = _get_config_file()
    start_marker, end_marker = _get_markers()

    if not os.path.exists(config_file):
        print("未找到config.fish文件，将创建新文件")
        os.makedirs(os.path.dirname(config_file), exist_ok=True)

    with open(config_file, "r") as f:
        content = f.read()

    if start_marker in content:
        print("JSS fish completion已安装，请执行: source ~/.config/fish/config.fish")
        return 0

    with open(config_file, "a") as f:
        f.write(f"""
{start_marker}
function fish_command_not_found
    if test (string length "$argv") -lt 10
        return
    end
    commandline -r (jss request "$argv")
end

function __fish_command_not_found_handler --on-event fish_command_not_found
    fish_command_not_found "$argv"
end
{end_marker}
""")
    print("JSS fish completion已安装，请执行: source ~/.config/fish/config.fish")
    return 0

def uninstall_jss_completion() -> int:
    """Uninstall JSS fish shell command completion
    
    Returns:
        int: 0 if success, 1 if failed
    """
    if not _check_fish_shell():
        print("当前不是fish shell，无需卸载")
        return 0

    config_file = _get_config_file()
    start_marker, end_marker = _get_markers()

    if not os.path.exists(config_file):
        print("未找到JSS fish completion配置，无需卸载")
        return 0

    with open(config_file, "r") as f:
        content = f.read()

    if start_marker not in content:
        print("未找到JSS fish completion配置，无需卸载")
        return 0

    new_content = content.split(start_marker)[0] + content.split(end_marker)[-1]
    
    with open(config_file, "w") as f:
        f.write(new_content)
    
    print("JSS fish completion已卸载，请执行: source ~/.config/fish/config.fish")
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
2. 不要输出任何命令之外的内容
3. 单行输出
4. 多个命令用&&连接

# 示例
输入: "查找Python文件"
输出: find . -name "*.py"
"""
        model.set_system_prompt(system_message)

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


def main() -> int:
    # 创建参数解析器
    init_env("")

    set_config("JARVIS_PRINT_PROMPT", "false")

    parser = argparse.ArgumentParser(
        description="将自然语言要求转换为shell命令",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  %(prog)s request "Find all Python files in the current directory"
  %(prog)s install
""",
    )

    # 创建子命令解析器
    subparsers = parser.add_subparsers(dest="command", required=True)

    # request子命令
    request_parser = subparsers.add_parser(
        "request", help="描述您想要执行的操作（用自然语言描述）"
    )
    request_parser.add_argument(
        "request",
        nargs="?",  # 设置为可选参数
        help="描述您想要执行的操作（用自然语言描述），如果未提供则从标准输入读取",
    )

    # install子命令
    install_parser = subparsers.add_parser(
        "install", help="安装JSS fish shell命令补全功能"
    )
    install_parser.add_argument(
        "--shell", choices=["fish"], default="fish", help="指定shell类型(仅支持fish)"
    )
    
    # 添加uninstall子命令
    uninstall_parser = subparsers.add_parser(
        "uninstall", help="卸载JSS fish shell命令补全功能"
    )
    uninstall_parser.add_argument(
        "--shell", choices=["fish"], default="fish", help="指定shell类型(仅支持fish)"
    )

    # 解析参数
    args = parser.parse_args()

    should_run = False

    # 处理install命令
    if args.command == "install":
        if args.shell != "fish":
            print(f"错误: 不支持的shell类型: {args.shell}, 仅支持fish")
            return 1
        return install_jss_completion()

    # 处理uninstall命令
    if args.command == "uninstall":
        if args.shell != "fish":
            print(f"错误: 不支持的shell类型: {args.shell}, 仅支持fish")
            return 1
        return uninstall_jss_completion()
        
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
