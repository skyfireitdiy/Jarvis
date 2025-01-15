#!/usr/bin/env python3
"""Command line interface for Jarvis."""

import argparse
import yaml
import os
import sys
from pathlib import Path
from prompt_toolkit import prompt

from jarvis.models.registry import PlatformRegistry

# 添加父目录到Python路径以支持导入
sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.agent import Agent
from jarvis.tools import ToolRegistry
from jarvis.utils import PrettyOutput, OutputType, get_multiline_input, load_env_from_file


def load_tasks() -> dict:
    """Load tasks from .jarvis files in user home and current directory."""
    tasks = {}
    
    # 检查用户目录下的 .jarvis
    user_jarvis = os.path.expanduser("~/.jarvis")
    if os.path.exists(user_jarvis):
        try:
            with open(user_jarvis, "r", encoding="utf-8") as f:
                user_tasks = yaml.safe_load(f)
                
            if isinstance(user_tasks, dict):
                # 验证并添加用户目录的任务
                for name, desc in user_tasks.items():
                    if desc:  # 确保描述不为空
                        tasks[str(name)] = str(desc)
            else:
                PrettyOutput.print("Warning: ~/.jarvis file should contain a dictionary of task_name: task_description", OutputType.ERROR)
        except Exception as e:
            PrettyOutput.print(f"Error loading ~/.jarvis file: {str(e)}", OutputType.ERROR)
    
    # 检查当前目录下的 .jarvis
    if os.path.exists(".jarvis"):
        try:
            with open(".jarvis", "r", encoding="utf-8") as f:
                local_tasks = yaml.safe_load(f)
                
            if isinstance(local_tasks, dict):
                # 验证并添加当前目录的任务，如果有重名则覆盖用户目录的任务
                for name, desc in local_tasks.items():
                    if desc:  # 确保描述不为空
                        tasks[str(name)] = str(desc)
            else:
                PrettyOutput.print("Warning: .jarvis file should contain a dictionary of task_name: task_description", OutputType.ERROR)
        except Exception as e:
            PrettyOutput.print(f"Error loading .jarvis file: {str(e)}", OutputType.ERROR)
    
    return tasks

def select_task(tasks: dict) -> str:
    """Let user select a task from the list or skip. Returns task description if selected."""
    if not tasks:
        return ""
    
    # Convert tasks to list for ordered display
    task_names = list(tasks.keys())
    
    PrettyOutput.print("\nAvailable tasks:", OutputType.INFO)
    for i, name in enumerate(task_names, 1):
        PrettyOutput.print(f"[{i}] {name}", OutputType.INFO)
    PrettyOutput.print("[0] 跳过预定义任务", OutputType.INFO)
    
    
    while True:
        try:
            choice = prompt(
                "\n请选择一个任务编号(0跳过): ",
            ).strip()
            
            if not choice:
                return ""
            
            choice = int(choice)
            if choice == 0:
                return ""
            elif 1 <= choice <= len(task_names):
                selected_name = task_names[choice - 1]
                return tasks[selected_name]  # Return the task description
            else:
                PrettyOutput.print("Invalid choice. Please select a number from the list.", OutputType.ERROR)
                
        except KeyboardInterrupt:
            return ""  # Return empty on Ctrl+C
        except EOFError:
            return ""  # Return empty on Ctrl+D
        except Exception as e:
            PrettyOutput.print(f"选择失败: {str(e)}", OutputType.ERROR)
            continue

def main():
    """Jarvis 的主入口点"""
    # 添加参数解析器
    parser = argparse.ArgumentParser(description='Jarvis AI 助手')
    parser.add_argument('-f', '--files', nargs='*', help='要处理的文件列表')
    parser.add_argument('--keep-history', action='store_true', help='保持聊天历史(不删除会话)')
    parser.add_argument('-p', '--platform', default='', help='选择AI平台')
    parser.add_argument('-m', '--model', default='', help='模型')  # 用于指定使用的模型名称，默认使用环境变量或平台默认模型
    args = parser.parse_args()

    load_env_from_file()

    platform = args.platform if args.platform else os.getenv('JARVIS_PLATFORM')

    if not platform:
        PrettyOutput.print("未指定AI平台，请使用 -p 参数或者设置 JARVIS_PLATFORM 环境变量", OutputType.ERROR)
        return 1

    PlatformRegistry.get_global_platform_registry().set_global_platform_name(platform)
    
    try:
        # 获取全局模型实例
        agent = Agent()

        # 如果用户传入了模型参数，则更换当前模型为用户指定的模型
        if args.model:
            PrettyOutput.print(f"用户传入了模型参数，更换模型: {args.model}", OutputType.USER)
            agent.model.set_model_name(args.model)

        # 欢迎信息
        PrettyOutput.print(f"Jarvis 已初始化 - With {platform} 平台，模型: {agent.model.name()}", OutputType.SYSTEM)
        if args.keep_history:
            PrettyOutput.print("已启用历史保留模式", OutputType.INFO)
        
        # 加载预定义任务
        tasks = load_tasks()
        if tasks:
            selected_task = select_task(tasks)
            if selected_task:
                PrettyOutput.print(f"\n执行任务: {selected_task}", OutputType.INFO)
                agent.run(selected_task, args.files, keep_history=args.keep_history)
                return 0
        
        # 如果没有选择预定义任务，进入交互模式
        while True:
            try:
                user_input = get_multiline_input("请输入您的任务(输入空行退出):")
                if not user_input or user_input == "__interrupt__":
                    break
                agent.run(user_input, args.files, keep_history=args.keep_history)
            except Exception as e:
                PrettyOutput.print(f"错误: {str(e)}", OutputType.ERROR)

    except Exception as e:
        PrettyOutput.print(f"初始化错误: {str(e)}", OutputType.ERROR)
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
