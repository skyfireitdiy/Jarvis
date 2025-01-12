#!/usr/bin/env python3
"""Command line interface for Jarvis."""

import argparse
import yaml
import os
import sys
from pathlib import Path

# 添加父目录到Python路径以支持导入
sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.agent import Agent
from jarvis.tools import ToolRegistry
from jarvis.models import KimiModel
from jarvis.utils import PrettyOutput, OutputType, get_multiline_input, load_env_from_file


def load_tasks() -> dict:
    """Load tasks from .jarvis file if it exists."""
    if not os.path.exists(".jarvis"):
        return {}
    
    try:
        with open(".jarvis", "r", encoding="utf-8") as f:
            tasks = yaml.safe_load(f)
            
        if not isinstance(tasks, dict):
            PrettyOutput.print("Warning: .jarvis file should contain a dictionary of task_name: task_description", OutputType.ERROR)
            return {}
            
        # Validate format and convert all values to strings
        validated_tasks = {}
        for name, desc in tasks.items():
            if desc:  # Ensure description is not empty
                validated_tasks[str(name)] = str(desc)
                
        return validated_tasks
    except Exception as e:
        PrettyOutput.print(f"Error loading .jarvis file: {str(e)}", OutputType.ERROR)
        return {}

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
            choice = input("\nSelect a task number (0 to skip): ").strip()
            if not choice:
                return ""
            
            choice = int(choice)
            if choice == 0:
                return ""
            elif 1 <= choice <= len(task_names):
                selected_name = task_names[choice - 1]
                return tasks[selected_name]  # Return the task description
            else:
                PrettyOutput.print("Invalid choice. Please try again.", OutputType.ERROR)
        except ValueError:
            PrettyOutput.print("Please enter a valid number.", OutputType.ERROR)

def main():
    """Main entry point for Jarvis."""
    # Add argument parser
    parser = argparse.ArgumentParser(description='Jarvis AI Assistant')
    parser.add_argument('-f', '--files', nargs='*', help='List of files to process')
    args = parser.parse_args()

    load_env_from_file()
    
    try:
        kimi_api_key = os.getenv("KIMI_API_KEY")
        if not kimi_api_key:
            PrettyOutput.section("环境配置缺失", OutputType.ERROR)
            PrettyOutput.print("\n需要设置 KIMI_API_KEY 才能使用 Jarvis。请按以下步骤操作：", OutputType.INFO, timestamp=False)
            PrettyOutput.print("\n1. 获取 Kimi API Key:", OutputType.INFO, timestamp=False)
            PrettyOutput.print("   • 访问 Kimi AI 平台: https://kimi.moonshot.cn", OutputType.INFO, timestamp=False)
            PrettyOutput.print("   • 登录您的账号", OutputType.INFO, timestamp=False)
            PrettyOutput.print("   • 打开浏览器开发者工具 (F12 或右键 -> 检查)", OutputType.INFO, timestamp=False)
            PrettyOutput.print("   • 切换到 Network 标签页", OutputType.INFO, timestamp=False)
            PrettyOutput.print("   • 发送任意消息", OutputType.INFO, timestamp=False)
            PrettyOutput.print("   • 在请求中找到 Authorization 头部", OutputType.INFO, timestamp=False)
            PrettyOutput.print("   • 复制 token 值（去掉 'Bearer ' 前缀）", OutputType.INFO, timestamp=False)
            
            PrettyOutput.print("\n2. 设置环境变量:", OutputType.INFO, timestamp=False)
            PrettyOutput.print("   方法 1: 创建或编辑 ~/.jarvis_env 文件:", OutputType.INFO, timestamp=False)
            PrettyOutput.print("   echo 'KIMI_API_KEY=your_key_here' > ~/.jarvis_env", OutputType.CODE, timestamp=False)
            
            PrettyOutput.print("\n   方法 2: 直接设置环境变量:", OutputType.INFO, timestamp=False)
            PrettyOutput.print("   export KIMI_API_KEY=your_key_here", OutputType.CODE, timestamp=False)
            
            PrettyOutput.print("\n设置完成后重新运行 Jarvis。", OutputType.INFO, timestamp=False)
            return 1
        
        model = KimiModel(kimi_api_key)

        tool_registry = ToolRegistry(model)
        agent = Agent(model, tool_registry)

        # 欢迎信息
        PrettyOutput.print(f"Jarvis 已初始化 - With Kimi", OutputType.SYSTEM)
        
        # 加载预定义任务
        tasks = load_tasks()
        if tasks:
            selected_task = select_task(tasks)
            if selected_task:
                PrettyOutput.print(f"\n执行任务: {selected_task}", OutputType.INFO)
                agent.run(selected_task, args.files)
                return 0
        
        # 如果没有选择预定义任务，进入交互模式
        while True:
            try:
                user_input = get_multiline_input("请输入您的任务(输入空行退出):")
                if not user_input or user_input == "__interrupt__":
                    break
                agent.run(user_input, args.files)
            except Exception as e:
                PrettyOutput.print(f"错误: {str(e)}", OutputType.ERROR)

    except Exception as e:
        PrettyOutput.print(f"初始化错误: {str(e)}", OutputType.ERROR)
        return 1

    return 0

if __name__ == "__main__":
    exit(main()) 