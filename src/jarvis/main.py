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
from jarvis.models import DDGSModel, OllamaModel
from jarvis.utils import PrettyOutput, OutputType, get_multiline_input, load_env_from_file
from jarvis.zte_llm import create_zte_llm

# 定义支持的平台和模型
SUPPORTED_PLATFORMS = {
    "ollama": {
        "models": ["llama3.2", "qwen2.5:14b"],
        "default": "qwen2.5:14b"
    },
    "ddgs": {
        "models": ["gpt-4o-mini", "claude-3-haiku", "llama-3.1-70b", "mixtral-8x7b"],
        "default": "gpt-4o-mini"
    },
    "zte": {
        "models": ["NebulaBiz", "nebulacoder", "NTele-72B"],
        "default": "NebulaBiz"
    }
}

def load_tasks() -> list:
    """Load tasks from .jarvis file if it exists."""
    if not os.path.exists(".jarvis"):
        return []
    
    try:
        with open(".jarvis", "r", encoding="utf-8") as f:
            tasks = yaml.safe_load(f)
            
        if not isinstance(tasks, list):
            PrettyOutput.print("Warning: .jarvis file should contain a list of tasks", OutputType.ERROR)
            return []
            
        return [str(task) for task in tasks if task]  # Convert all tasks to strings and filter out empty ones
    except Exception as e:
        PrettyOutput.print(f"Error loading .jarvis file: {str(e)}", OutputType.ERROR)
        return []

def select_task(tasks: list) -> str:
    """Let user select a task from the list or skip."""
    if not tasks:
        return ""
    
    PrettyOutput.print("\nFound predefined tasks:", OutputType.INFO)
    for i, task in enumerate(tasks, 1):
        PrettyOutput.print(f"[{i}] {task}", OutputType.INFO)
    PrettyOutput.print("[0] Skip predefined tasks", OutputType.INFO)
    
    while True:
        try:
            choice = input("\nSelect a task number (0 to skip): ").strip()
            if not choice:
                return ""
            
            choice = int(choice)
            if choice == 0:
                return ""
            elif 1 <= choice <= len(tasks):
                return tasks[choice - 1]
            else:
                PrettyOutput.print("Invalid choice. Please try again.", OutputType.ERROR)
        except ValueError:
            PrettyOutput.print("Please enter a valid number.", OutputType.ERROR)

def main():
    """Main entry point for Jarvis."""
    parser = argparse.ArgumentParser(description="Jarvis AI Assistant")
    
    # 添加平台选择参数
    parser.add_argument(
        "--platform",
        choices=list(SUPPORTED_PLATFORMS.keys()),
        default="ollama",
        help="选择运行平台 (默认: ollama)"
    )
    
    # 添加模型选择参数
    parser.add_argument(
        "--model",
        help="选择模型 (默认: 根据平台自动选择)"
    )
    
    # 添加API基础URL参数
    parser.add_argument(
        "--api-base",
        default="http://localhost:11434",
        help="Ollama API基础URL (仅用于Ollama平台, 默认: http://localhost:11434)"
    )
    
    args = parser.parse_args()

    load_env_from_file()
    
    # 验证并设置默认模型
    if args.model:
        if args.model not in SUPPORTED_PLATFORMS[args.platform]["models"]:
            supported_models = ", ".join(SUPPORTED_PLATFORMS[args.platform]["models"])
            PrettyOutput.print(
                f"错误: 平台 {args.platform} 不支持模型 {args.model}\n"
                f"支持的模型: {supported_models}",
                OutputType.ERROR
            )
            return 1
    else:
        args.model = SUPPORTED_PLATFORMS[args.platform]["default"]

    try:
        # 根据平台创建相应的模型实例
        if args.platform == "ollama":
            model = OllamaModel(
                model_name=args.model,
                api_base=args.api_base
            )
            platform_name = f"Ollama ({args.model})"
        elif args.platform == "ddgs":  # ddgs
            model = DDGSModel(model_name=args.model)
            platform_name = f"DuckDuckGo Search ({args.model})"
        elif args.platform == "zte":  # zte
            model = create_zte_llm(model_name=args.model)
            platform_name = f"ZTE ({args.model})"

        tool_registry = ToolRegistry()
        agent = Agent(model, tool_registry)

        # 欢迎信息
        PrettyOutput.print(f"Jarvis 已初始化 - {platform_name}", OutputType.SYSTEM)
        
        # 加载预定义任务
        tasks = load_tasks()
        if tasks:
            selected_task = select_task(tasks)
            if selected_task:
                PrettyOutput.print(f"\n执行任务: {selected_task}", OutputType.INFO)
                agent.run(selected_task)
                return 0
        
        # 如果没有选择预定义任务，进入交互模式
        while True:
            try:
                user_input = get_multiline_input("请输入您的任务(输入空行退出):")
                if not user_input:
                    break
                agent.run(user_input)
            except KeyboardInterrupt:
                print("\n正在退出...")
                break
            except Exception as e:
                PrettyOutput.print(f"错误: {str(e)}", OutputType.ERROR)

    except Exception as e:
        PrettyOutput.print(f"初始化错误: {str(e)}", OutputType.ERROR)
        return 1

    return 0

if __name__ == "__main__":
    exit(main()) 