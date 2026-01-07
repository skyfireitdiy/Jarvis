# -*- coding: utf-8 -*-
"""Tmux 自动启动封装模块

检测系统是否安装tmux，如果不在tmux环境中运行，自动创建tmux会话并重新执行命令。
"""

import getpass
import os
import shlex
import shutil
import subprocess
import sys
import uuid
from typing import Optional

from jarvis.jarvis_utils.output import PrettyOutput, OutputType


def _get_username() -> str:
    """获取当前用户名。

    优先使用getpass.getuser()，降级到环境变量USER，
    最后返回'unknown'作为兜底。

    Returns:
        str: 用户名
    """
    try:
        return getpass.getuser()
    except Exception:
        return os.environ.get("USER", "unknown")


def _generate_session_name() -> str:
    """生成带用户名前缀的tmux session名称。

    统一格式：{username}-jarvis-{uuid}
    使用UUID确保唯一性，支持多用户环境。

    Returns:
        str: 生成的session名称
    """
    username = _get_username()
    unique_suffix = uuid.uuid4().hex[:8]
    return f"{username}-jarvis-{unique_suffix}"


def dispatch_to_tmux_window(
    task_arg: Optional[str], argv: list[str], window_name: str = "jarvis-dispatch"
) -> bool:
    """将任务派发到新的 tmux 窗格（pane）中执行。

    Args:
        task_arg: 任务内容（已废弃，保留用于兼容）
        argv: 当前命令行参数（需要过滤 --dispatch）
        window_name: 窗口名称前缀（已废弃，保留用于兼容）

    Returns:
        bool: 是否成功派发（True表示成功，False表示失败）

    注意:
        在 tmux 环境中直接在当前窗口创建新窗格。
        如果不在 tmux 环境中，会查找 jarvis 创建的 tmux session
        并在其中创建窗格作为降级方案。
        使用水平分割（split-window -h）创建新窗格，适合代码任务。
    """
    # 检查tmux是否安装
    tmux_path = shutil.which("tmux")
    if tmux_path is None:
        return False

    # 检查是否已在tmux环境中运行
    if "TMUX" not in os.environ:
        # 不在tmux中，尝试查找jarvis创建的session作为降级方案
        return _dispatch_to_existing_jarvis_session(task_arg, argv)

    # 生成窗口名称（使用任务内容的前20个字符）
    if task_arg and str(task_arg).strip():
        # 清理任务内容，移除换行和特殊字符
        clean_task = str(task_arg).strip()[:20].replace("\n", " ").replace("\r", " ")
        window_name = f"{window_name}-{clean_task}"

    # 过滤 --dispatch/-d 参数，避免循环派发
    # 由于 --dispatch/-d 是布尔参数，通常不会带值
    # 但为了健壮性，处理所有可能的格式
    filtered_argv = []
    skip_next = False
    for i, arg in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if arg == "--dispatch" or arg == "-d":
            # 情况1: --dispatch/-d（无值），直接跳过
            continue
        elif arg.startswith("--dispatch=") or arg.startswith("-d="):
            # 情况2: --dispatch=value/-d=value，整个参数跳过
            continue
        else:
            # 保留其他参数
            filtered_argv.append(arg)

    # 获取当前窗口标识，用于后续布局切换
    # tmux select-layout 支持 session_name:window_index 格式的目标参数
    current_window = None
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "#{session_name}:#{window_index}"],
            capture_output=True,
            text=True,
            check=True,
        )
        current_window = result.stdout.strip()
        # 验证格式是否正确（应包含冒号分隔符）
        if not current_window or ":" not in current_window:
            PrettyOutput.print(
                f"⚠️ Invalid window format: '{current_window}'",
                OutputType.WARNING,
                timestamp=False,
            )
            current_window = None
    except subprocess.CalledProcessError as e:
        PrettyOutput.print(
            f"⚠️ Failed to get current window: {e}",
            OutputType.WARNING,
            timestamp=False,
        )

    # 构造 tmux split-window 命令（在当前窗口创建新的窗格）
    # split-window -h "<command>" - 水平分割（左右布局）
    executable = sys.executable
    # 使用 shlex.quote() 安全地转义每个参数，防止 shell 注入
    quoted_args = [shlex.quote(arg) for arg in filtered_argv]
    # 获取用户的默认shell，主命令结束后启动shell保持panel活动
    user_shell = os.environ.get("SHELL", "/bin/sh")
    # 先切换到当前工作目录，再执行命令
    cwd = os.getcwd()
    command = f'cd {shlex.quote(cwd)} && {executable} {" ".join(quoted_args)}; exec "{user_shell}"'

    tmux_args = [
        "tmux",
        "split-window",
        "-h",  # 水平分割（左右布局），适合代码任务
        command,
    ]

    # 执行tmux命令
    try:
        subprocess.run(tmux_args, check=True)
        # 创建新pane后，自动切换到tiled布局
        if current_window:
            try:
                subprocess.run(
                    ["tmux", "select-layout", "-t", current_window, "tiled"], check=True
                )
            except subprocess.CalledProcessError as e:
                # 布局切换失败记录错误，但不影响主流程
                PrettyOutput.print(
                    f"⚠️ Failed to set tiled layout for window {current_window}: {e}",
                    OutputType.WARNING,
                    timestamp=False,
                )
        return True
    except subprocess.CalledProcessError as e:
        PrettyOutput.print(
            f"⚠️ Failed to dispatch to tmux window: {e}",
            OutputType.WARNING,
            timestamp=False,
        )
        return False


def check_and_launch_tmux() -> None:
    """检测tmux并在需要时启动tmux会话。

    注意:
        此函数使用subprocess.execvp替换当前进程，如果成功则不会返回。
        Session名称统一使用 {username}-jarvis-{uuid} 格式。
    """
    # 检查tmux是否安装
    tmux_path = shutil.which("tmux")
    if tmux_path is None:
        # tmux未安装，正常继续执行
        return

    # 检查是否已在tmux环境中运行
    # tmux会设置TMUX环境变量
    if "TMUX" in os.environ:
        # 已在tmux中，正常继续执行
        return

    # tmux已安装且不在tmux中，优先查找现有 session
    existing_session = find_or_create_jarvis_session(force_create=False)

    # 如果找到现有 session，附加到该 session
    if existing_session:
        PrettyOutput.print(
            f"ℹ️ 找到现有 session: {existing_session}，正在附加...",
            OutputType.INFO,
            timestamp=False,
        )
        tmux_args = [
            "tmux",
            "attach",
            "-t",
            existing_session,
        ]
        try:
            os.execvp("tmux", tmux_args)
        except OSError as e:
            PrettyOutput.print(
                f"⚠️ Failed to attach to tmux session '{existing_session}': {e}",
                OutputType.WARNING,
                timestamp=False,
            )
            return

    # 未找到现有 session，创建新的 session
    # 为会话名称添加随机后缀，避免冲突
    session_name = _generate_session_name()
    # 构造tmux命令：new-session -s <session_name> -- <command>
    # -s: 指定会话名称
    # --: 后面的参数是要执行的命令

    # 获取当前可执行文件路径和参数
    executable = sys.executable
    argv = sys.argv

    # 获取用户的默认shell
    user_shell = os.environ.get("SHELL", "/bin/sh")

    # 构造tmux命令参数
    # 使用shell包装器来确保会话在主命令结束后继续运行
    # 参考 dispatch_to_tmux_window 的实现，使用 shlex.quote 安全转义参数
    quoted_args = [shlex.quote(arg) for arg in argv]
    command = f'{executable} {" ".join(quoted_args)}; exec "{user_shell}"'
    tmux_args = [
        "tmux",
        "new-session",
        "-s",
        session_name,
        command,
    ]

    # 替换当前进程为tmux
    # execvp会替换当前进程，不会返回
    try:
        os.execvp("tmux", tmux_args)
    except OSError as e:
        # 如果执行失败，输出警告并继续
        PrettyOutput.print(
            f"⚠️ Failed to launch tmux: {e}",
            OutputType.WARNING,
            timestamp=False,
        )
        return


def _find_jarvis_session() -> Optional[str]:
    """查找 jarvis tmux session。

    Returns:
        Optional[str]: 找到的 session 名称，未找到返回 None

    注意:
        仅查找带用户名前缀的 "jarvis" session。
        格式：{username}-jarvis-{uuid}
    """
    try:
        result = subprocess.run(
            ["tmux", "list-sessions"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        # 获取用户名用于构建前缀
        username = _get_username()
        # 解析 session 名称：格式为 "session-name: windows (created ...)"
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                # 提取 session 名称（冒号之前的部分）
                session_name = line.split(":")[0].strip()
                # 匹配带用户名前缀的会话：{username}-jarvis-{uuid}
                expected_prefix = f"{username}-jarvis-"
                if session_name.startswith(expected_prefix):
                    # 精确前缀匹配：检查去除前缀后的部分是否为数字或UUID
                    suffix = session_name[len(expected_prefix) :]
                    if suffix and (
                        suffix[0].isdigit() or suffix[0] in "abcdef0123456789"
                    ):
                        # 匹配成功：后缀以数字或UUID字符开头
                        return session_name
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        # 正常情况：没有活动的 tmux 会话时不打印警告
        pass
    except Exception as e:
        # 保留真正的意外错误警告
        PrettyOutput.print(
            f"⚠️ Unexpected error while listing sessions: {e}",
            OutputType.WARNING,
            timestamp=False,
        )
    return None


def find_or_create_jarvis_session(force_create: bool = True) -> Optional[str]:
    """查找或创建 jarvis session。

    优先查找现有的 jarvis session，找到则返回 session 名称，
    未找到则创建新 session。

    Args:
        force_create: 未找到时是否创建新 session

    Returns:
        Optional[str]: 找到或创建的 session 名称，未找到且不创建则返回 None
    """
    # 先尝试查找现有 session
    existing_session = _find_jarvis_session()
    if existing_session:
        return existing_session

    # 未找到现有 session
    if not force_create:
        return None

    # 创建新的 session
    session_name = _generate_session_name()
    try:
        # 创建新的 detached session
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name],
            check=True,
            timeout=10,
        )
        return session_name
    except subprocess.CalledProcessError as e:
        PrettyOutput.print(
            f"⚠️ Failed to create tmux session '{session_name}': {e}",
            OutputType.WARNING,
            timestamp=False,
        )
        return None
    except subprocess.TimeoutExpired:
        PrettyOutput.print(
            f"⚠️ Creating tmux session '{session_name}' timed out",
            OutputType.WARNING,
            timestamp=False,
        )
        return None


def _dispatch_to_existing_jarvis_session(
    task_arg: Optional[str], argv: list[str]
) -> bool:
    """将任务派发到现有 jarvis tmux session 的 panel 中执行。

    这是一个降级方案：当不在 tmux 环境中时，尝试找到 jarvis 创建的 session
    并在其中创建 panel 执行命令。如果未找到 session，则创建一个新的 session。

    Args:
        task_arg: 任务内容（已废弃，保留用于兼容）
        argv: 当前命令行参数（需要过滤 --dispatch）

    Returns:
        bool: 是否成功派发（True表示成功，False表示失败）
    """
    # 查找 jarvis session
    session_name = _find_jarvis_session()
    if not session_name:
        # 未找到现有 session，创建一个新的 session
        PrettyOutput.print(
            "ℹ️ 未找到 jarvis tmux session，正在创建新 session...",
            OutputType.INFO,
            timestamp=False,
        )
        # 生成新的 session 名称
        session_name = _generate_session_name()
        try:
            # 创建新的 detached session
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", session_name],
                check=True,
                timeout=10,
            )
            PrettyOutput.print(
                f"✅ 已创建新的 tmux session: {session_name}",
                OutputType.SUCCESS,
                timestamp=False,
            )
        except subprocess.CalledProcessError as e:
            PrettyOutput.print(
                f"❌ 创建 tmux session 失败: {e}",
                OutputType.ERROR,
                timestamp=False,
            )
            return False
        except subprocess.TimeoutExpired:
            PrettyOutput.print(
                "❌ 创建 tmux session 超时",
                OutputType.ERROR,
                timestamp=False,
            )
            return False
    else:
        PrettyOutput.print(
            f"ℹ️ 找到 jarvis session: {session_name}",
            OutputType.INFO,
            timestamp=False,
        )

    # 过滤 --dispatch/-d 参数，避免循环派发
    filtered_argv = []
    skip_next = False
    for i, arg in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if arg == "--dispatch" or arg == "-d":
            continue
        elif arg.startswith("--dispatch=") or arg.startswith("-d="):
            continue
        else:
            filtered_argv.append(arg)

    # 构造 tmux split-window 命令（在指定 session 的当前窗口创建新 pane）
    executable = sys.executable
    quoted_args = [shlex.quote(arg) for arg in filtered_argv]
    user_shell = os.environ.get("SHELL", "/bin/sh")
    # 先切换到当前工作目录，再执行命令
    cwd = os.getcwd()
    command = f'cd {shlex.quote(cwd)} && {executable} {" ".join(quoted_args)}; exec "{user_shell}"'

    tmux_args = [
        "tmux",
        "split-window",
        "-h",  # 水平分割（左右布局）
        "-t",  # 指定目标 session
        session_name,
        command,
    ]

    # 执行 tmux 命令
    try:
        subprocess.run(tmux_args, check=True)
        # 创建新 pane 后，切换到 tiled 布局
        subprocess.run(
            ["tmux", "select-layout", "-t", session_name, "tiled"],
            check=True,
        )
        PrettyOutput.print(
            f"✅ 任务已派发到 tmux session '{session_name}' 的 panel 中",
            OutputType.SUCCESS,
            timestamp=False,
        )
        return True
    except subprocess.CalledProcessError as e:
        PrettyOutput.print(
            f"⚠️ Failed to dispatch to tmux session '{session_name}': {e}",
            OutputType.WARNING,
            timestamp=False,
        )
        return False
