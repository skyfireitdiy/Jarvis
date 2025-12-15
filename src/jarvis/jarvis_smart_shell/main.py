#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
from typing import Optional
from typing import Tuple

import typer

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import get_shell_name
from jarvis.jarvis_utils.config import set_config
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.utils import init_env

app = typer.Typer(
    help="将自然语言要求转换为shell命令",
    epilog="""
Example:
  jss request "Find all Python files in the current directory"
  jss install
""",
)


def execute_command(command: str, should_run: bool) -> None:
    """Print command without execution"""
    PrettyOutput.auto_print(command)
    if should_run:
        os.system(command)


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
        "# ===== JARVIS JSS FISH COMPLETION END =====",
    )


def _check_bash_shell() -> bool:
    """Check if current shell is bash

    Returns:
        bool: True if bash shell, False otherwise
    """
    return get_shell_name() == "bash"


def _get_bash_config_file() -> str:
    """Get bash config file path

    Returns:
        str: Path to bash config file (~/.bashrc)
    """
    return os.path.expanduser("~/.bashrc")


def _get_bash_markers() -> Tuple[str, str]:
    """Get start and end markers for JSS completion in bash

    Returns:
        Tuple[str, str]: (start_marker, end_marker)
    """
    return (
        "# ===== JARVIS JSS BASH COMPLETION START =====",
        "# ===== JARVIS JSS BASH COMPLETION END =====",
    )


def _check_zsh_shell() -> bool:
    """Check if current shell is zsh

    Returns:
        bool: True if zsh shell, False otherwise
    """
    return get_shell_name() == "zsh"


def _get_zsh_config_file() -> str:
    """Get zsh config file path

    Returns:
        str: Path to zsh config file (~/.zshrc)
    """
    return os.path.expanduser("~/.zshrc")


def _get_zsh_markers() -> Tuple[str, str]:
    """Get start and end markers for JSS completion in zsh

    Returns:
        Tuple[str, str]: (start_marker, end_marker)
    """
    return (
        "# ===== JARVIS JSS ZSH COMPLETION START =====",
        "# ===== JARVIS JSS ZSH COMPLETION END =====",
    )


@app.command("install")
def install_jss_completion(
    shell: str = typer.Option("fish", help="指定shell类型(支持fish, bash, zsh)"),
) -> None:
    """为指定的shell安装'命令未找到'处理器，实现自然语言命令建议"""
    if shell not in ("fish", "bash", "zsh"):
        PrettyOutput.auto_print(
            f"❌ 错误: 不支持的shell类型: {shell}, 仅支持fish, bash, zsh"
        )
        raise typer.Exit(code=1)

    if shell == "fish":
        config_file = _get_config_file()
        start_marker, end_marker = _get_markers()

        if not os.path.exists(config_file):
            PrettyOutput.auto_print("ℹ️ 未找到 config.fish 文件，将创建新文件")
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
            with open(config_file, "w") as f:
                f.write("")

        with open(config_file, "r") as f:
            content = f.read()

        if start_marker in content:
            PrettyOutput.auto_print(
                "✅ JSS fish completion 已安装，请执行: source ~/.config/fish/config.fish"
            )
            return

        with open(config_file, "a") as f:
            f.write(
                f"""
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
"""
            )
        PrettyOutput.auto_print(
            "✅ JSS fish completion 已安装，请执行: source ~/.config/fish/config.fish"
        )
    elif shell == "bash":
        config_file = _get_bash_config_file()
        start_marker, end_marker = _get_bash_markers()

        if not os.path.exists(config_file):
            PrettyOutput.auto_print("ℹ️ 未找到 ~/.bashrc 文件，将创建新文件")
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
            with open(config_file, "w") as f:
                f.write("")

        with open(config_file, "r") as f:
            content = f.read()

        if start_marker in content:
            PrettyOutput.auto_print(
                "✅ JSS bash completion 已安装，请执行: source ~/.bashrc"
            )
            return
        else:
            with open(config_file, "a") as f:
                f.write(
                    f"""
{start_marker}
# Bash 'command not found' handler for JSS
# 行为：
# - 生成可编辑的建议命令，用户可直接编辑后回车执行
# - 非交互模式下仅打印建议
command_not_found_handle() {{
    local cmd="$1"
    shift || true
    local text="$cmd $*"

    # 与 fish 行为保持一致：对过短输入不处理
    if [ ${{#text}} -lt 10 ]; then
        return 127
    fi

    local suggestion edited
    suggestion=$(jss request "$text")
    if [ -n "$suggestion" ]; then
        # 交互式：用 readline 预填命令，用户可直接回车执行或编辑
        if [[ $- == *i* ]]; then
            edited="$suggestion"
            # -e 启用 readline；-i 预填默认值；无提示前缀，使体验更接近 fish 的“替换命令行”
            read -e -i "$edited" edited
            if [ -n "$edited" ]; then
                eval "$edited"
                return $?
            fi
        else
            # 非交互：仅打印建议
            printf '%s\n' "$suggestion"
        fi
    fi
    return 127
}}
{end_marker}
"""
                )
            PrettyOutput.auto_print(
                "✅ JSS bash completion 已安装，请执行: source ~/.bashrc"
            )
    elif shell == "zsh":
        config_file = _get_zsh_config_file()
        start_marker, end_marker = _get_zsh_markers()

        if not os.path.exists(config_file):
            PrettyOutput.auto_print("ℹ️ 未找到 ~/.zshrc 文件，将创建新文件")
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
            with open(config_file, "w") as f:
                f.write("")

        with open(config_file, "r") as f:
            content = f.read()

        if start_marker in content:
            PrettyOutput.auto_print(
                "✅ JSS zsh completion 已安装，请执行: source ~/.zshrc"
            )
            return

        with open(config_file, "a") as f:
            f.write(
                f"""
{start_marker}
# Zsh 'command not found' handler for JSS
# 行为：
# - 生成可编辑的建议命令，用户可直接编辑后回车执行
# - 非交互模式下仅打印建议
command_not_found_handler() {{
    local cmd="$1"
    shift || true
    local text="$cmd $*"

    # 与 fish 行为保持一致：对过短输入不处理
    if [ ${{#text}} -lt 10 ]; then
        return 127
    fi

    local suggestion edited
    suggestion=$(jss request "$text")
    if [ -n "$suggestion" ]; then
        if [[ -o interactive ]]; then
            local editor="${{VISUAL:-${{EDITOR:-vi}}}}"
            local tmpfile edited
            tmpfile="$(mktemp -t jss-edit-XXXXXX)"
            printf '%s\n' "$suggestion" > "$tmpfile"
            "$editor" "$tmpfile"
            edited="$(sed -n '/./{{p;q;}}' "$tmpfile" | tr -d '\r')"
            rm -f "$tmpfile"
            if [ -z "$edited" ]; then
                edited="$suggestion"
            fi
            eval "$edited"
            return $?
        else
            # 非交互：仅打印建议
            print -r -- "$suggestion"
        fi
    fi
    return 127
}}
{end_marker}
"""
            )
        PrettyOutput.auto_print("✅ JSS zsh completion 已安装，请执行: source ~/.zshrc")
        return


@app.command("uninstall")
def uninstall_jss_completion(
    shell: str = typer.Option("fish", help="指定shell类型(支持fish, bash, zsh)"),
) -> None:
    """卸载JSS shell'命令未找到'处理器"""
    if shell not in ("fish", "bash", "zsh"):
        PrettyOutput.auto_print(
            f"❌ 错误: 不支持的shell类型: {shell}, 仅支持fish, bash, zsh"
        )
        raise typer.Exit(code=1)

    if shell == "fish":
        config_file = _get_config_file()
        start_marker, end_marker = _get_markers()

        if not os.path.exists(config_file):
            PrettyOutput.auto_print("ℹ️ 未找到 JSS fish completion 配置，无需卸载")
            return

        with open(config_file, "r") as f:
            content = f.read()

        if start_marker not in content:
            PrettyOutput.auto_print("ℹ️ 未找到 JSS fish completion 配置，无需卸载")
            return

        new_content = content.split(start_marker)[0] + content.split(end_marker)[-1]

        with open(config_file, "w") as f:
            f.write(new_content)

        PrettyOutput.auto_print(
            "✅ JSS fish completion 已卸载，请执行: source ~/.config/fish/config.fish"
        )
    elif shell == "bash":
        config_file = _get_bash_config_file()
        start_marker, end_marker = _get_bash_markers()

        if not os.path.exists(config_file):
            PrettyOutput.auto_print("ℹ️ 未找到 JSS bash completion 配置，无需卸载")
            return

        with open(config_file, "r") as f:
            content = f.read()

        if start_marker not in content:
            PrettyOutput.auto_print("ℹ️ 未找到 JSS bash completion 配置，无需卸载")
            return

        new_content = content.split(start_marker)[0] + content.split(end_marker)[-1]

        with open(config_file, "w") as f:
            f.write(new_content)

        PrettyOutput.auto_print(
            "✅ JSS bash completion 已卸载，请执行: source ~/.bashrc"
        )
    elif shell == "zsh":
        config_file = _get_zsh_config_file()
        start_marker, end_marker = _get_zsh_markers()

        if not os.path.exists(config_file):
            PrettyOutput.auto_print("ℹ️ 未找到 JSS zsh completion 配置，无需卸载")
            return

        with open(config_file, "r") as f:
            content = f.read()

        if start_marker not in content:
            PrettyOutput.auto_print("ℹ️ 未找到 JSS zsh completion 配置，无需卸载")
            return

        new_content = content.split(start_marker)[0] + content.split(end_marker)[-1]

        with open(config_file, "w") as f:
            f.write(new_content)

        PrettyOutput.auto_print("✅ JSS zsh completion 已卸载，请执行: source ~/.zshrc")


def process_request(request: str) -> Optional[str]:
    """Process user request and return corresponding shell command

    Args:
        request: User's natural language request

    Returns:
        Optional[str]: Corresponding shell command, return None if processing fails
    """
    try:
        # Get language model instance
        # 使用normal平台，智能shell命令生成是一般任务
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
输入: "显示当前目录内容"
输出: ls -la
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


@app.command("request")
def request_command(
    request: Optional[str] = typer.Argument(
        None, help="描述您想要执行的操作（用自然语言描述），如果未提供则从标准输入读取"
    ),
):
    """描述您想要执行的操作（用自然语言描述）"""
    should_run = False
    if not request:
        # 检查是否在交互式终端中运行
        request = get_multiline_input(tip="请输入您要执行的功能：")
        should_run = True

    # 处理请求
    command = process_request(request)

    # 输出结果
    if command:
        execute_command(command, should_run)  # 显示并执行命令
    else:
        raise typer.Exit(code=1)


def cli():
    """Typer application entry point"""
    init_env("")
    set_config("print_prompt", "false")
    app()


def main():
    """Main entry point for the script"""
    cli()


if __name__ == "__main__":
    main()
