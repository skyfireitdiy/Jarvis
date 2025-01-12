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
from jarvis.models import DDGSModel, OllamaModel, OpenAIModel, KimiModel
from jarvis.utils import PrettyOutput, OutputType, get_multiline_input, load_env_from_file
from jarvis.zte_llm import create_zte_llm

# 定义支持的平台和模型
SUPPORTED_PLATFORMS = {
    "kimi": {
        "models": ["kimi"],
        "default": "kimi",
        "allow_custom": False
    },
    "ollama": {
        "models": ["qwen2.5:14b", "qwq"],
        "default": "qwen2.5:14b",
        "allow_custom": True
    },
    "ddgs": {
        "models": ["gpt-4o-mini", "claude-3-haiku", "llama-3.1-70b", "mixtral-8x7b"],
        "default": "gpt-4o-mini",
        "allow_custom": False
    },
    "zte": {
        "models": ["NebulaBiz", "nebulacoder", "NTele-72B"],
        "default": "NebulaBiz",
        "allow_custom": False
    },
    "openai": {
        "models": ["deepseek-chat"],
        "default": "deepseek-chat",
        "allow_custom": True
    }
}

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

    load_env_from_file()

    parser = argparse.ArgumentParser(description="Jarvis AI Assistant")
    
    # 添加平台选择参数
    parser.add_argument(
        "--platform",
        choices=list(SUPPORTED_PLATFORMS.keys()),
        default=os.getenv("JARVIS_PLATFORM") or "kimi",
        help="选择运行平台 (默认: kimi)"
    )
    
    # 添加模型选择参数
    parser.add_argument(
        "--model",
        help="选择模型 (默认: 根据平台自动选择)"
    )
    
    # 添加API基础URL参数
    parser.add_argument(
        "--api-base",
        default=os.getenv("JARVIS_OLLAMA_API_BASE") or "http://localhost:11434",
        help="Ollama API基础URL (仅用于Ollama平台, 默认: http://localhost:11434)"
    )
    
    args = parser.parse_args()

    args.model = args.model or os.getenv("JARVIS_MODEL")
    
    # 修改模型验证逻辑
    if args.model:
        if (args.model not in SUPPORTED_PLATFORMS[args.platform]["models"] and 
            not SUPPORTED_PLATFORMS[args.platform]["allow_custom"]):
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
        if args.platform == "kimi":
            model = KimiModel(os.getenv("KIMI_API_KEY"))
            platform_name = "Kimi"
        elif args.platform == "ollama":
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
        elif args.platform == "openai":
            model = OpenAIModel(
                model_name=args.model,
                api_key=os.getenv("OPENAI_API_KEY"),
                api_base=os.getenv("OPENAI_API_BASE")
            )
            platform_name = f"OpenAI ({args.model})"

        tool_registry = ToolRegistry(model)
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
                if not user_input or user_input == "__interrupt__":
                    break
                agent.run(user_input)
            except Exception as e:
                PrettyOutput.print(f"错误: {str(e)}", OutputType.ERROR)

    except Exception as e:
        PrettyOutput.print(f"初始化错误: {str(e)}", OutputType.ERROR)
        return 1

    return 0

if __name__ == "__main__":
    exit(main()) 