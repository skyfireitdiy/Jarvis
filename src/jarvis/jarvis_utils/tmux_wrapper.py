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
    """将任务派发到新的 tmux 窗口中执行。

    Args:
        task_arg: 任务内容（用于窗口命名）
        argv: 当前命令行参数（需要过滤 --dispatch）
        window_name: tmux 窗口名称前缀，默认为"jarvis-dispatch"

    Returns:
        bool: 是否成功派发（True表示成功，False表示失败）

    注意:
        仅在 tmux 环境中才能派发。
        如果不在 tmux 环境中，返回 False。
    """
    # 检查tmux是否安装
    tmux_path = shutil.which("tmux")
    if tmux_path is None:
        return False

    # 检查是否已在tmux环境中运行
    if "TMUX" not in os.environ:
        return False

    # 生成窗口名称（使用任务内容的前20个字符）
    if task_arg and str(task_arg).strip():
        # 清理任务内容，移除换行和特殊字符
        clean_task = str(task_arg).strip()[:20].replace("\n", " ").replace("\r", " ")
        window_name = f"{window_name}-{clean_task}"

    # 过滤 --dispatch 参数，避免循环派发
    # 由于 --dispatch 是布尔参数，通常不会带值
    # 但为了健壮性，处理所有可能的格式
    filtered_argv = []
    skip_next = False
    for i, arg in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if arg == "--dispatch":
            # 情况1: --dispatch（无值），直接跳过
            continue
        elif arg.startswith("--dispatch="):
            # 情况2: --dispatch=value，整个参数跳过
            continue
        else:
            # 保留其他参数
            filtered_argv.append(arg)

    # 构造tmux new-window命令
    # new-window -n <window_name> "<command>"
    executable = sys.executable
    # 使用 shlex.quote() 安全地转义每个参数，防止 shell 注入
    quoted_args = [shlex.quote(arg) for arg in filtered_argv]
    command = f"{executable} {' '.join(quoted_args)}"

    tmux_args = [
        "tmux",
        "new-window",
        "-n",
        window_name,
        command,
    ]

    # 执行tmux命令
    try:
        subprocess.run(tmux_args, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Warning: Failed to dispatch to tmux window: {e}", file=sys.stderr)
        return False


def check_and_launch_tmux(session_name: str = "jarvis-auto") -> None:
    """检测tmux并在需要时启动tmux会话。

    Args:
        session_name: tmux会话名称，默认为"jarvis-auto"

    注意:
        此函数使用subprocess.execvp替换当前进程，如果成功则不会返回。
    """
    # 为会话名称添加随机后缀，避免冲突
    session_name = f"{session_name}-{uuid.uuid4().hex[:8]}"
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

    # tmux已安装且不在tmux中，启动tmux会话
    # 构造tmux命令：new-session -A -s <session_name> -- <command>
    # -A: 如果会话已存在则attach，否则创建新会话
    # -s: 指定会话名称
    # --: 后面的参数是要执行的命令

    # 获取当前可执行文件路径和参数
    executable = sys.executable
    argv = sys.argv

    # 获取用户的默认shell
    user_shell = os.environ.get("SHELL", "/bin/sh")

    # 构造tmux命令参数
    # 使用shell包装器来确保会话在主命令结束后继续运行
    tmux_args = [
        "tmux",
        "new-session",
        "-A",  # Attach if session exists
        "-s",
        session_name,
        "--",
        user_shell,
        "-c",
        f'{executable} {" ".join([repr(arg) for arg in argv])}; exec "{user_shell}"',  # 主命令结束后启动用户默认shell保持会话
    ]

    # 替换当前进程为tmux
    # execvp会替换当前进程，不会返回
    try:
        os.execvp("tmux", tmux_args)
    except OSError as e:
        # 如果执行失败，输出警告并继续
        print(f"Warning: Failed to launch tmux: {e}", file=sys.stderr)
        return
