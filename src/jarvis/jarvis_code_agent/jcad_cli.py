# -*- coding: utf-8 -*-
"""Jarvis Code Agent Dispatcher CLI

便捷命令，用于快速启动 jca 任务派发。
"""

import os
import subprocess
import sys
import tempfile
from typing import Any, Optional

import typer
from typer.models import ArgumentInfo

from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.input import (
    get_multiline_input as get_multiline_input_enhanced,
)

# 创建 typer 应用
app = typer.Typer(help="Jarvis Code Agent Dispatcher - jca 的便捷封装")


def _write_task_to_temp_file(task_content: str) -> str:
    """将任务内容写入临时文件并返回文件路径

    参数:
        task_content: 任务内容（字符串）

    返回:
        str: 临时文件路径
    """
    # 使用 tempfile.mkstemp 在 /tmp 目录创建临时文件

    fd, temp_path = tempfile.mkstemp(
        suffix=".txt",
        prefix="jcad_task_",
        text=True,
        dir="/tmp",
    )

    # 写入内容
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(task_content)
        f.flush()
        os.fsync(f.fileno())

    PrettyOutput.auto_print(f"📝 临时文件已创建: {temp_path}")
    return temp_path


def run_jca_dispatch(
    task: Any,
    is_dispatch_mode: bool = False,
    stay_in_session_after_exit: bool = True,
    force_dispatch: bool = False,
) -> None:
    """执行 jca -n -w --dispatch --task <task>"""
    # 确保 task 是字符串内容而非类型对象
    if isinstance(task, str):
        task_str = task
    elif isinstance(task, ArgumentInfo):
        # 处理 typer 的 ArgumentInfo 对象，提取 default 属性
        task_str = task.default if task.default is not None else ""
    else:
        # 处理非字符串类型，尝试获取实际值
        task_str = str(task) if task is not None else ""

    # 检查 task_str 是否为空
    if not task_str or not task_str.strip():
        PrettyOutput.auto_print(
            f"❌ 错误: 任务内容为空，无法执行。task 类型: {type(task).__name__}, task 值: {task}"
        )
        sys.exit(1)

    # 判断是文件路径还是直接内容
    is_task_file = os.path.exists(task_str)

    # dispatch 模式下使用临时文件时，需要手动处理 tmux 和文件删除
    # force_dispatch 强制使用 dispatch 模式（适用于临时文件场景）
    if (is_dispatch_mode and is_task_file) or force_dispatch:
        # 构造 tmux split-window 命令
        import shlex

        # 获取当前工作目录
        cwd = os.getcwd()

        # 不使用 shlex.quote，直接使用双引号包裹路径
        quoted_cwd = shlex.quote(cwd)
        # 对于任务文件路径，使用转义而非 shlex.quote
        quoted_task_file = task_str.replace("'", "'\"'\"'")

        # 构造命令：cd 到工作目录，执行 jca
        # 注意：不自动删除任务文件，避免被清理机制误删
        command = f"cd {quoted_cwd} && jca -n -w --task-file '{quoted_task_file}'"

        try:
            # 使用智能调度函数创建 tmux panel
            from jarvis.jarvis_utils.tmux_wrapper import dispatch_command_to_panel

            session_name = dispatch_command_to_panel(
                command,
                stay_in_session_after_exit=stay_in_session_after_exit,
                shell_fallback=False,
            )
            if not session_name:
                PrettyOutput.auto_print("❌ 错误: dispatch 模式创建 tmux panel 失败")
                sys.exit(1)

            # 父进程退出，不等待子进程完成
            sys.exit(0)
        except subprocess.CalledProcessError as e:
            PrettyOutput.auto_print(f"❌ 执行 tmux 命令失败: {e}")
            sys.exit(1)
        except Exception as e:
            PrettyOutput.auto_print(f"❌ dispatch 失败: {e}")
            sys.exit(1)
    else:
        # 非 dispatch 模式或非文件模式：使用原有逻辑
        if is_task_file:
            # 如果是文件路径，使用 --task-file 参数
            cmd = ["jca", "-n", "-w", "--dispatch", "--task-file", task_str]
        else:
            # 如果是直接内容，使用 --task 参数
            cmd = ["jca", "-n", "-w", "--dispatch", "--task", task_str]
        try:
            # 直接执行 jca 命令，不捕获输出，让用户直接看到 jca 的输出
            result = subprocess.run(cmd)
            sys.exit(result.returncode)
        except FileNotFoundError:
            PrettyOutput.auto_print(
                "❌ 错误: 找不到 'jca' 命令，请确保 jarvis 已正确安装"
            )
            sys.exit(1)
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 执行 jca 命令失败: {e}")
            sys.exit(1)


@app.command()
def main(
    task: Optional[str] = typer.Argument(
        None, help="任务内容（可选，不提供则进入交互模式）"
    ),
) -> None:
    """Jarvis Code Agent Dispatcher - jca 的便捷封装

    用法:
        jcad "你的任务"           # 直接执行任务
        jcad                      # 进入交互模式输入任务
    """

    if task:
        # 直接模式：传入任务字符串
        # 判断是否为文件路径（已存在的文件不添加规则）
        if not os.path.exists(task):
            # 不是文件，在任务开头添加 builtin_rules
            task = "'<rule:builtin_rules>'\n" + task

        # 检查是否包含多行内容（换行符）
        if "\n" in task:
            # 多行输入：创建临时文件
            temp_file_path = _write_task_to_temp_file(task)
            run_jca_dispatch(temp_file_path, is_dispatch_mode=True, force_dispatch=True)
        else:
            # 单行输入：直接传递
            run_jca_dispatch(task)
    else:
        # 交互模式：多行输入（使用input模块的增强接口）
        task_content = get_multiline_input_enhanced(
            "请输入任务内容（Ctrl+J/Ctrl+] 确认，Enter 换行）"
        )
        if not task_content.strip():
            PrettyOutput.auto_print("ℹ️ 未输入任务内容，退出")
            sys.exit(0)

        # 在任务开头添加 builtin_rules
        task_content = "'<rule:builtin_rules>'\n" + task_content

        # 创建临时文件
        temp_file_path = _write_task_to_temp_file(task_content)
        run_jca_dispatch(temp_file_path, is_dispatch_mode=True, force_dispatch=True)


if __name__ == "__main__":
    app()
