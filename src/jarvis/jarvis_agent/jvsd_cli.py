# -*- coding: utf-8 -*-
"""Jarvis Agent Dispatcher CLI

便捷命令，用于快速启动 jvs 任务派发。
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

import typer
from typer.models import ArgumentInfo

from jarvis.jarvis_utils.output import OutputType, PrettyOutput

# 创建 typer 应用
app = typer.Typer(help="Jarvis Agent Dispatcher - jvs 的便捷封装")


def get_multiline_input(prompt: str = "请输入任务内容（空行结束）:") -> str:
    """获取多行输入，直到遇到空行或 EOF"""
    lines = []
    PrettyOutput.auto_print(prompt)
    while True:
        try:
            line = input()
            if line.strip() == "":
                break
            lines.append(line)
        except EOFError:
            break
    return "\n".join(lines)


def _write_task_to_temp_file(task_content: str) -> str:
    """将任务内容写入临时文件并返回文件路径

    参数:
        task_content: 任务内容（字符串）

    返回:
        str: 临时文件路径
    """
    temp_file = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        prefix="jvsd_task_",
        delete=False,
        encoding="utf-8",
    )
    try:
        temp_file.write(task_content)
        return temp_file.name
    except Exception:
        # 如果写入失败，清理临时文件
        try:
            temp_file.close()
            Path(temp_file.name).unlink(missing_ok=True)
        except Exception:
            pass
        raise
    finally:
        temp_file.close()


def run_jvs_dispatch(task: Any) -> None:
    """执行 jvs -n -d --task <task>"""
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
    if os.path.exists(task_str):
        # 如果是文件路径，使用 --task-file 参数
        cmd = ["jvs", "-n", "-d", "--task-file", task_str]
    else:
        # 如果是直接内容，使用 --task 参数
        cmd = ["jvs", "-n", "-d", "--task", task_str]
    try:
        # 打印即将执行的命令
        PrettyOutput.print(
            f"Executing command: {' '.join(cmd)}", output_type=OutputType.DEBUG
        )
        # 直接执行 jvs 命令，不捕获输出，让用户直接看到 jvs 的输出
        result = subprocess.run(cmd)
        sys.exit(result.returncode)
    except FileNotFoundError:
        PrettyOutput.auto_print("❌ 错误: 找不到 'jvs' 命令，请确保 jarvis 已正确安装")
        sys.exit(1)
    except Exception as e:
        PrettyOutput.auto_print(f"❌ 执行 jvs 命令失败: {e}")
        sys.exit(1)


@app.command()
def main(
    task: Optional[str] = typer.Argument(
        None, help="任务内容（可选，不提供则进入交互模式）"
    ),
) -> None:
    """Jarvis Agent Dispatcher - jvs 的便捷封装

    用法:
        jvsd "你的任务"           # 直接执行任务
        jvsd                      # 进入交互模式输入任务
    """
    # 调试信息：打印接收到的 task 参数
    PrettyOutput.print(
        f"[DEBUG] main() 接收到的 task 参数: type={type(task).__name__}, value={task}",
        output_type=OutputType.DEBUG,
    )

    if task:
        # 直接模式：传入任务字符串
        # 检查是否包含多行内容（换行符）
        if "\n" in task:
            # 多行输入：创建临时文件
            temp_file_path = _write_task_to_temp_file(task)
            try:
                # 使用临时文件路径作为任务参数
                run_jvs_dispatch(temp_file_path)
            finally:
                # 清理临时文件
                try:
                    Path(temp_file_path).unlink(missing_ok=True)
                except Exception:
                    pass
        else:
            # 单行输入：直接传递
            run_jvs_dispatch(task)
    else:
        # 交互模式：多行输入
        task_content = get_multiline_input()
        if not task_content.strip():
            PrettyOutput.auto_print("ℹ️ 未输入任务内容，退出")
            sys.exit(0)

        # 创建临时文件
        temp_file_path = _write_task_to_temp_file(task_content)
        try:
            # 使用临时文件路径作为任务参数
            run_jvs_dispatch(temp_file_path)
        finally:
            # 清理临时文件
            try:
                Path(temp_file_path).unlink(missing_ok=True)
            except Exception:
                pass


if __name__ == "__main__":
    app()
