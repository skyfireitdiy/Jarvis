# -*- coding: utf-8 -*-
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

import yaml  # type: ignore
from prompt_toolkit import prompt  # type: ignore

from jarvis.jarvis_agent import (
    Agent,
    OutputType,
    PrettyOutput,
    get_multiline_input,
    origin_agent_system_prompt,
    user_confirm,
)
from jarvis.jarvis_agent.builtin_input_handler import builtin_input_handler
from jarvis.jarvis_agent.shell_input_handler import shell_input_handler
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.utils import init_env


def _load_tasks() -> Dict[str, str]:
    """Load tasks from .jarvis files in user home and current directory."""
    tasks: Dict[str, str] = {}

    # Check pre-command in data directory
    data_dir = get_data_dir()
    pre_command_path = os.path.join(data_dir, "pre-command")
    if os.path.exists(pre_command_path):
        print(f"🔍 从{pre_command_path}加载预定义任务...")
        try:
            with open(pre_command_path, "r", encoding="utf-8", errors="ignore") as f:
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
            with open(pre_command_path, "r", encoding="utf-8", errors="ignore") as f:
                local_tasks = yaml.safe_load(f)
            if isinstance(local_tasks, dict):
                for name, desc in local_tasks.items():
                    if desc:
                        tasks[str(name)] = str(desc)
            print(f"✅ 预定义任务加载完成 {pre_command_path}")
        except (yaml.YAMLError, OSError):
            print(f"❌ 预定义任务加载失败 {pre_command_path}")

    return tasks


def _select_task(tasks: Dict[str, str]) -> str:
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
            choice_str = prompt("\n请选择一个任务编号（0 跳过预定义任务）：").strip()
            if not choice_str:
                return ""

            choice = int(choice_str)
            if choice == 0:
                return ""
            if 1 <= choice <= len(task_names):
                selected_task = tasks[task_names[choice - 1]]
                PrettyOutput.print(f"将要执行任务:\n {selected_task}", OutputType.INFO)
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


def _parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Jarvis AI assistant")
    parser.add_argument(
        "--llm_type",
        type=str,
        default="normal",
        choices=["normal", "thinking"],
        help="LLM type to use",
    )
    parser.add_argument(
        "-t",
        "--task",
        type=str,
        help="Directly input task content from command line",
    )
    parser.add_argument("-f", "--config", type=str, help="Path to custom config file")
    parser.add_argument(
        "--restore-session",
        action="store_true",
        help="Restore session from .jarvis/saved_session.json",
        default=False,
    )
    parser.add_argument(
        "-e", "--edit", action="store_true", help="Edit the configuration file"
    )
    return parser.parse_args()


def _handle_edit_mode(args: argparse.Namespace) -> None:
    """If edit flag is set, open config file in editor and exit."""
    if not args.edit:
        return

    config_file_path = (
        Path(args.config)
        if args.config
        else Path(os.path.expanduser("~/.jarvis/config.yaml"))
    )
    editors = ["nvim", "vim", "vi"]
    editor = next((e for e in editors if shutil.which(e)), None)

    if editor:
        try:
            subprocess.run([editor, str(config_file_path)], check=True)
            sys.exit(0)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            PrettyOutput.print(f"Failed to open editor: {e}", OutputType.ERROR)
            sys.exit(1)
    else:
        PrettyOutput.print(
            "No suitable editor found (nvim, vim, vi).", OutputType.ERROR
        )
        sys.exit(1)


def _initialize_agent(args: argparse.Namespace) -> Agent:
    """Initialize the agent and restore session if requested."""
    agent = Agent(
        system_prompt=origin_agent_system_prompt,
        llm_type=args.llm_type,
        input_handler=[shell_input_handler, builtin_input_handler],
        output_handler=[ToolRegistry()],  # type: ignore
        need_summary=False,
    )

    # 尝试恢复会话
    if args.restore_session:
        if agent.restore_session():
            PrettyOutput.print("会话已成功恢复。", OutputType.SUCCESS)
        else:
            PrettyOutput.print("无法恢复会话。", OutputType.WARNING)
    return agent


def _get_and_run_task(agent: Agent, task_content: Optional[str] = None) -> None:
    """Get task from various sources and run it."""
    # 优先处理命令行直接传入的任务
    if task_content:
        agent.run(task_content)
        sys.exit(0)

    if agent.first:
        tasks = _load_tasks()
        if tasks and (selected_task := _select_task(tasks)):
            PrettyOutput.print(f"开始执行任务: \n{selected_task}", OutputType.INFO)
            agent.run(selected_task)
            sys.exit(0)

    user_input = get_multiline_input("请输入你的任务（输入空行退出）:")
    if user_input:
        agent.run(user_input)
    sys.exit(0)


def main() -> None:
    """Main function for Jarvis AI assistant."""
    args = _parse_args()
    _handle_edit_mode(args)

    init_env(
        "欢迎使用 Jarvis AI 助手，您的智能助理已准备就绪！", config_file=args.config
    )

    try:
        agent = _initialize_agent(args)
        _get_and_run_task(agent, args.task)
    except Exception as err:  # pylint: disable=broad-except
        PrettyOutput.print(f"初始化错误: {str(err)}", OutputType.ERROR)
        sys.exit(1)


if __name__ == "__main__":
    main()
