# -*- coding: utf-8 -*-
"""任务管理模块，负责加载和选择预定义任务"""
import os
from typing import Dict

import yaml
from prompt_toolkit import prompt

from jarvis.jarvis_agent import (
    OutputType,
    PrettyOutput,
    get_multiline_input,
    user_confirm,
)
from jarvis.jarvis_utils.config import get_data_dir


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
            print(f"🔍 从{pre_command_path}加载预定义任务...")
            try:
                with open(
                    pre_command_path, "r", encoding="utf-8", errors="ignore"
                ) as f:
                    user_tasks = yaml.safe_load(f)
                if isinstance(user_tasks, dict):
                    for name, desc in user_tasks.items():
                        if desc:
                            tasks[str(name)] = str(desc)
                print(f"✅ 预定义任务加载完成 {pre_command_path}")
            except (yaml.YAMLError, OSError):
                print(f"❌ 预定义任务加载失败 {pre_command_path}")

        # Check .jarvis/pre-command in current directory
        pre_command_path = ".jarvis/pre-command"
        if os.path.exists(pre_command_path):
            abs_path = os.path.abspath(pre_command_path)
            print(f"🔍 从{abs_path}加载预定义任务...")
            try:
                with open(
                    pre_command_path, "r", encoding="utf-8", errors="ignore"
                ) as f:
                    local_tasks = yaml.safe_load(f)
                if isinstance(local_tasks, dict):
                    for name, desc in local_tasks.items():
                        if desc:
                            tasks[str(name)] = str(desc)
                print(f"✅ 预定义任务加载完成 {pre_command_path}")
            except (yaml.YAMLError, OSError):
                print(f"❌ 预定义任务加载失败 {pre_command_path}")

        return tasks

    @staticmethod
    def select_task(tasks: Dict[str, str]) -> str:
        """Let user select a task from the list or skip. Returns task description if selected."""
        if not tasks:
            return ""

        task_names = list(tasks.keys())
        task_list = ["可用任务:"]
        for i, name in enumerate(task_names, 1):
            task_list.append(f"[{i}] {name}")
        task_list.append("[0] 跳过预定义任务")
        PrettyOutput.print("\n".join(task_list), OutputType.INFO)

        while True:
            try:
                choice_str = prompt(
                    "\n请选择一个任务编号（0 跳过预定义任务）："
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
