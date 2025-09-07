# -*- coding: utf-8 -*-
"""任务管理模块，负责加载和选择预定义任务"""
import os
from typing import Dict

import yaml  # type: ignore
from prompt_toolkit import prompt
from rich.table import Table
from rich.console import Console

from jarvis.jarvis_agent import (
    OutputType,
    PrettyOutput,
    get_multiline_input,
    user_confirm,
)
from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.fzf import fzf_select


class TaskManager:
    """任务管理器，负责预定义任务的加载和选择"""

    @staticmethod
    def load_tasks() -> Dict[str, str]:
        """Load tasks from .jarvis files in user home and current directory."""
        tasks: Dict[str, str] = {}

        # Check pre-command in data directory
        data_dir = get_data_dir()
        pre_command_path = os.path.join(data_dir, "pre-command")
        if os.path.exists(pre_command_path):
            PrettyOutput.print(
                f"从{pre_command_path}加载预定义任务...", OutputType.INFO
            )
            try:
                with open(
                    pre_command_path, "r", encoding="utf-8", errors="ignore"
                ) as f:
                    user_tasks = yaml.safe_load(f)
                if isinstance(user_tasks, dict):
                    for name, desc in user_tasks.items():
                        if desc:
                            tasks[str(name)] = str(desc)
                PrettyOutput.print(
                    f"预定义任务加载完成 {pre_command_path}", OutputType.SUCCESS
                )
            except (yaml.YAMLError, OSError):
                PrettyOutput.print(
                    f"预定义任务加载失败 {pre_command_path}", OutputType.ERROR
                )

        # Check .jarvis/pre-command in current directory
        pre_command_path = ".jarvis/pre-command"
        if os.path.exists(pre_command_path):
            abs_path = os.path.abspath(pre_command_path)
            PrettyOutput.print(f"从{abs_path}加载预定义任务...", OutputType.INFO)
            try:
                with open(
                    pre_command_path, "r", encoding="utf-8", errors="ignore"
                ) as f:
                    local_tasks = yaml.safe_load(f)
                if isinstance(local_tasks, dict):
                    for name, desc in local_tasks.items():
                        if desc:
                            tasks[str(name)] = str(desc)
                PrettyOutput.print(
                    f"预定义任务加载完成 {pre_command_path}", OutputType.SUCCESS
                )
            except (yaml.YAMLError, OSError):
                PrettyOutput.print(
                    f"预定义任务加载失败 {pre_command_path}", OutputType.ERROR
                )

        return tasks

    @staticmethod
    def select_task(tasks: Dict[str, str]) -> str:
        """Let user select a task from the list or skip. Returns task description if selected."""
        if not tasks:
            return ""

        task_names = list(tasks.keys())
        # 使用 rich.Table 展示预定义任务
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("No.", style="cyan", no_wrap=True)
        table.add_column("任务名", style="bold")
        for i, name in enumerate(task_names, 1):
            table.add_row(str(i), name)
        Console().print(table)
        PrettyOutput.print("[0] 跳过预定义任务", OutputType.INFO)

        # Try fzf selection first (with numbered options and a skip option)
        fzf_list = [f"{0:>3} | 跳过预定义任务"] + [
            f"{i:>3} | {name}" for i, name in enumerate(task_names, 1)
        ]
        selected_str = fzf_select(fzf_list, prompt="选择一个任务编号 (ESC跳过) > ")
        if selected_str:
            try:
                num_part = selected_str.split("|", 1)[0].strip()
                idx = int(num_part)
                if idx == 0:
                    return ""
                if 1 <= idx <= len(task_names):
                    selected_task = tasks[task_names[idx - 1]]
                    PrettyOutput.print(f"将要执行任务:\n {selected_task}", OutputType.INFO)
                    # 询问是否需要补充信息
                    need_additional = user_confirm("需要为此任务添加补充信息吗？", default=False)
                    if need_additional:
                        additional_input = get_multiline_input("请输入补充信息：")
                        if additional_input:
                            selected_task = f"{selected_task}\n\n补充信息:\n{additional_input}"
                    return selected_task
            except Exception:
                # 如果解析失败，则回退到手动输入
                pass

        while True:
            try:
                choice_str = prompt(
                    "\n请选择一个任务编号（0 或者直接回车跳过预定义任务）："
                ).strip()
                if not choice_str:
                    return ""

                choice = int(choice_str)
                if choice == 0:
                    return ""
                if 1 <= choice <= len(task_names):
                    selected_task = tasks[task_names[choice - 1]]
                    PrettyOutput.print(
                        f"将要执行任务:\n {selected_task}", OutputType.INFO
                    )
                    # 询问是否需要补充信息
                    need_additional = user_confirm(
                        "需要为此任务添加补充信息吗？", default=False
                    )
                    if need_additional:
                        additional_input = get_multiline_input("请输入补充信息：")
                        if additional_input:
                            selected_task = (
                                f"{selected_task}\n\n补充信息:\n{additional_input}"
                            )
                    return selected_task
                PrettyOutput.print(
                    "无效的选择。请选择列表中的一个号码。", OutputType.WARNING
                )

            except (KeyboardInterrupt, EOFError):
                return ""
            except ValueError as val_err:
                PrettyOutput.print(f"选择任务失败: {str(val_err)}", OutputType.ERROR)
