# -*- coding: utf-8 -*-
"""Tmux 自动启动封装模块

检测系统是否安装tmux，如果不在tmux环境中运行，自动创建tmux会话并重新执行命令。
"""

import os
import shutil
import sys


def check_and_launch_tmux(session_name: str = "jarvis-auto") -> None:
    """检测tmux并在需要时启动tmux会话。

    Args:
        session_name: tmux会话名称，默认为"jarvis-auto"

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

    # tmux已安装且不在tmux中，启动tmux会话
    # 构造tmux命令：new-session -A -s <session_name> -- <command>
    # -A: 如果会话已存在则attach，否则创建新会话
    # -s: 指定会话名称
    # --: 后面的参数是要执行的命令

    # 获取当前可执行文件路径和参数
    executable = sys.executable
    argv = sys.argv

    # 构造tmux命令参数
    tmux_args = [
        "tmux",
        "new-session",
        "-A",  # Attach if session exists
        "-s",
        session_name,
        "--",
        executable,
    ]
    tmux_args.extend(argv)

    # 替换当前进程为tmux
    # execvp会替换当前进程，不会返回
    try:
        os.execvp("tmux", tmux_args)
    except OSError as e:
        # 如果执行失败，输出警告并继续
        print(f"Warning: Failed to launch tmux: {e}", file=sys.stderr)
        return
