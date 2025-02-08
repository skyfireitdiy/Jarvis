#!/usr/bin/env python3
"""Command line interface for Jarvis."""

import argparse
import yaml
import os
import sys
from pathlib import Path
from prompt_toolkit import prompt

from jarvis.models.registry import PlatformRegistry

# Add parent directory to Python path to support imports    
sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.agent import Agent
from jarvis.tools import ToolRegistry
from jarvis.utils import PrettyOutput, OutputType, get_multiline_input, load_env_from_file


def load_tasks() -> dict:
    """Load tasks from .jarvis files in user home and current directory."""
    tasks = {}
    
    # Check .jarvis in user directory
    user_jarvis = os.path.expanduser("~/.jarvis")
    if os.path.exists(user_jarvis):
        try:
            with open(user_jarvis, "r", encoding="utf-8") as f:
                user_tasks = yaml.safe_load(f)
                
            if isinstance(user_tasks, dict):
                # Validate and add user directory tasks
                for name, desc in user_tasks.items():
                    if desc:  # Ensure description is not empty
                        tasks[str(name)] = str(desc)
            else:
                PrettyOutput.print("Warning: ~/.jarvis file should contain a dictionary of task_name: task_description", OutputType.ERROR)
        except Exception as e:
            PrettyOutput.print(f"Error loading ~/.jarvis file: {str(e)}", OutputType.ERROR)
    
    # Check .jarvis in current directory
    if os.path.exists(".jarvis"):
        try:
            with open(".jarvis", "r", encoding="utf-8") as f:
                local_tasks = yaml.safe_load(f)
                
            if isinstance(local_tasks, dict):
                # Validate and add current directory tasks, overwrite user directory tasks if there is a name conflict
                for name, desc in local_tasks.items():
                    if desc:  # Ensure description is not empty
                        tasks[str(name)] = str(desc)
            else:
                PrettyOutput.print("Warning: .jarvis file should contain a dictionary of task_name: task_description", OutputType.ERROR)
        except Exception as e:
            PrettyOutput.print(f"Error loading .jarvis file: {str(e)}", OutputType.ERROR)

    # Read methodology
    method_path = os.path.expanduser("~/.jarvis_methodology")
    if os.path.exists(method_path):
        with open(method_path, "r", encoding="utf-8") as f:
            methodology = yaml.safe_load(f)
        if isinstance(methodology, dict):
            for name, desc in methodology.items():
                tasks[f"Run Methodology: {str(name)}\n {str(desc)}" ] = str(desc)
    
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
    PrettyOutput.print("[0] Skip predefined tasks", OutputType.INFO)
    
    
    while True:
        try:
            choice = prompt(
                "\nPlease select a task number (0 to skip): ",
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
            PrettyOutput.print(f"Failed to select task: {str(e)}", OutputType.ERROR)
            continue

def main():
    """Jarvis main entry point"""
    # Add argument parser
    load_env_from_file()
    parser = argparse.ArgumentParser(description='Jarvis AI assistant')
    parser.add_argument('-f', '--files', nargs='*', help='List of files to process')
    parser.add_argument('--keep-history', action='store_true', help='Keep chat history (do not delete session)')
    args = parser.parse_args()

    try:
        # 获取全局模型实例
        agent = Agent()

        # 如果用户传入了模型参数，则更换当前模型为用户指定的模型

        # Welcome information
        PrettyOutput.print(f"Jarvis initialized - With {agent.model.name()}", OutputType.SYSTEM)
        if args.keep_history:
            PrettyOutput.print("History preservation mode enabled", OutputType.INFO)
        
        # 加载预定义任务
        tasks = load_tasks()
        if tasks:
            selected_task = select_task(tasks)
            if selected_task:
                PrettyOutput.print(f"\nExecute task: {selected_task}", OutputType.INFO)
                agent.run(selected_task, args.files)
                return 0
        
        # 如果没有选择预定义任务，进入交互模式
        while True:
            try:
                user_input = get_multiline_input("Please enter your task (input empty line to exit):")
                if not user_input or user_input == "__interrupt__":
                    break
                agent.run(user_input, args.files)
            except Exception as e:
                PrettyOutput.print(f"Error: {str(e)}", OutputType.ERROR)

    except Exception as e:
        PrettyOutput.print(f"Initialization error: {str(e)}", OutputType.ERROR)
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
