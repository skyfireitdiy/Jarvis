# -*- coding: utf-8 -*-
"""Tmux 自动启动封装模块

检测系统是否安装tmux，如果不在tmux环境中运行，自动创建tmux会话并重新执行命令。
"""

import os
import shlex
import shutil
import subprocess
import sys
import uuid
from typing import Optional


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
        如果不在 tmux 环境中，会查找 codeagent 创建的 tmux session
        并在其中创建窗格作为降级方案。
        使用水平分割（split-window -h）创建新窗格，适合代码任务。
    """
    # 检查tmux是否安装
    tmux_path = shutil.which("tmux")
    if tmux_path is None:
        return False

    # 检查是否已在tmux环境中运行
    if "TMUX" not in os.environ:
        # 不在tmux中，尝试查找codeagent创建的session作为降级方案
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
            print(
                f"Warning: Invalid window format: '{current_window}'", file=sys.stderr
            )
            current_window = None
    except subprocess.CalledProcessError as e:
        print(f"Warning: Failed to get current window: {e}", file=sys.stderr)

    # 构造 tmux split-window 命令（在当前窗口创建新的窗格）
    # split-window -h "<command>" - 水平分割（左右布局）
    executable = sys.executable
    # 使用 shlex.quote() 安全地转义每个参数，防止 shell 注入
    quoted_args = [shlex.quote(arg) for arg in filtered_argv]
    # 获取用户的默认shell，主命令结束后启动shell保持panel活动
    user_shell = os.environ.get("SHELL", "/bin/sh")
    command = f'{executable} {" ".join(quoted_args)}; exec "{user_shell}"'

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
                print(
                    f"Warning: Failed to set tiled layout for window {current_window}: {e}",
                    file=sys.stderr,
                )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Warning: Failed to dispatch to tmux window: {e}", file=sys.stderr)
        return False


def check_and_launch_tmux(session_name: str = "jarvis-auto") -> None:
    """检测tmux并在需要时启动tmux会话。

    Args:
        session_name: tmux会话名称前缀，默认为"jarvis-auto"

    注意:
        此函数使用subprocess.execvp替换当前进程，如果成功则不会返回。
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
    existing_session = find_or_create_jarvis_session(session_name, force_create=False)

    # 如果找到现有 session，附加到该 session
    if existing_session:
        print(f"ℹ️ 找到现有 session: {existing_session}，正在附加...", file=sys.stderr)
        tmux_args = [
            "tmux",
            "attach",
            "-t",
            existing_session,
        ]
        try:
            os.execvp("tmux", tmux_args)
        except OSError as e:
            print(
                f"Warning: Failed to attach to tmux session '{existing_session}': {e}",
                file=sys.stderr,
            )
            return

    # 未找到现有 session，创建新的 session
    # 为会话名称添加随机后缀，避免冲突
    session_name = f"{session_name}-{uuid.uuid4().hex[:8]}"
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
        print(f"Warning: Failed to launch tmux: {e}", file=sys.stderr)
        return


def _find_jarvis_session(session_prefix: str) -> Optional[str]:
    """查找指定前缀的 jarvis tmux session。

    Args:
        session_prefix: session 名称前缀（如 "jarvis-code-agent"）

    Returns:
        Optional[str]: 找到的 session 名称，未找到返回 None
    """
    try:
        result = subprocess.run(
            ["tmux", "list-sessions"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        # 解析 session 名称：格式为 "session-name: windows (created ...)"
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                # 提取 session 名称（冒号之前的部分）
                session_name = line.split(":")[0].strip()
                # 检查是否是指定前缀的 session
                if session_name.startswith(f"{session_prefix}-"):
                    return session_name
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        # 正常情况：没有活动的 tmux 会话时不打印警告
        pass
    except Exception as e:
        # 保留真正的意外错误警告
        print(f"Warning: Unexpected error while listing sessions: {e}", file=sys.stderr)
    return None


def _find_jarvis_code_agent_session() -> Optional[str]:
    """查找 codeagent 创建的 tmux session（兼容函数）。

    Returns:
        Optional[str]: 找到的 session 名称，未找到返回 None
    """
    return _find_jarvis_session("jarvis-code-agent")


def find_or_create_jarvis_session(
    session_prefix: str, force_create: bool = True
) -> Optional[str]:
    """查找或创建 jarvis session。

    优先查找以 session_prefix- 开头的现有 session，
    找到则返回 session 名称，未找到则创建新 session。

    Args:
        session_prefix: session 名称前缀（如 "jarvis-code-agent"）
        force_create: 未找到时是否创建新 session

    Returns:
        Optional[str]: 找到或创建的 session 名称，未找到且不创建则返回 None
    """
    # 先尝试查找现有 session
    existing_session = _find_jarvis_session(session_prefix)
    if existing_session:
        return existing_session

    # 未找到现有 session
    if not force_create:
        return None

    # 创建新的 session
    session_name = f"{session_prefix}-{uuid.uuid4().hex[:8]}"
    try:
        # 创建新的 detached session
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name],
            check=True,
            timeout=10,
        )
        return session_name
    except subprocess.CalledProcessError as e:
        print(
            f"Warning: Failed to create tmux session '{session_name}': {e}",
            file=sys.stderr,
        )
        return None
    except subprocess.TimeoutExpired:
        print(
            f"Warning: Creating tmux session '{session_name}' timed out",
            file=sys.stderr,
        )
        return None


def _dispatch_to_existing_jarvis_session(
    task_arg: Optional[str], argv: list[str]
) -> bool:
    """将任务派发到现有 codeagent tmux session 的 panel 中执行。

    这是一个降级方案：当不在 tmux 环境中时，尝试找到 codeagent 创建的 session
    并在其中创建 panel 执行命令。如果未找到 session，则创建一个新的 session。

    Args:
        task_arg: 任务内容（已废弃，保留用于兼容）
        argv: 当前命令行参数（需要过滤 --dispatch）

    Returns:
        bool: 是否成功派发（True表示成功，False表示失败）
    """
    # 查找 codeagent 创建的 session
    session_name = _find_jarvis_code_agent_session()
    if not session_name:
        # 未找到现有 session，创建一个新的 session
        print(
            "ℹ️ 未找到 codeagent 创建的 tmux session，正在创建新 session...",
            file=sys.stderr,
        )
        # 生成新的 session 名称
        session_name = f"jarvis-code-agent-{uuid.uuid4().hex[:8]}"
        try:
            # 创建新的 detached session
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", session_name],
                check=True,
                timeout=10,
            )
            print(f"✅ 已创建新的 tmux session: {session_name}", file=sys.stderr)
        except subprocess.CalledProcessError as e:
            print(
                f"❌ 创建 tmux session 失败: {e}",
                file=sys.stderr,
            )
            return False
        except subprocess.TimeoutExpired:
            print(
                "❌ 创建 tmux session 超时",
                file=sys.stderr,
            )
            return False
    else:
        print(f"ℹ️ 找到 codeagent session: {session_name}", file=sys.stderr)

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
    command = f'{executable} {" ".join(quoted_args)}; exec "{user_shell}"'

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
        print(
            f"✅ 任务已派发到 tmux session '{session_name}' 的 panel 中",
            file=sys.stderr,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(
            f"Warning: Failed to dispatch to tmux session '{session_name}': {e}",
            file=sys.stderr,
        )
        return False
