"""Command line interface for Jarvis."""

import argparse
import yaml
import os
from .agent import Agent
from .tools import ToolRegistry
from .models import DDGSModel
from .utils import PrettyOutput, OutputType, get_multiline_input

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
    parser.add_argument("--model", 
                       choices=["gpt-4o-mini", "claude-3-haiku", "llama-3.1-70b", "mixtral-8x7b"],
                       default="gpt-4o-mini",
                       help="Model to use (default: gpt-4o-mini)")
    args = parser.parse_args()

    try:
        model = DDGSModel(model_name=args.model)
        tool_registry = ToolRegistry()
        agent = Agent(model, tool_registry)

        # Welcome message
        PrettyOutput.print(f"Jarvis initialized with {args.model}.", OutputType.SYSTEM)
        
        # Load predefined tasks
        tasks = load_tasks()
        if tasks:
            selected_task = select_task(tasks)
            if selected_task:
                PrettyOutput.print(f"\nExecuting task: {selected_task}", OutputType.INFO)
                agent.run(selected_task)
                return 0
        
        # If no predefined task was selected, enter interactive mode
        while True:
            try:
                user_input = get_multiline_input("请输入您的任务(输入空行退出):")
                if not user_input:
                    break
                agent.run(user_input)
            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except Exception as e:
                PrettyOutput.print(f"Error: {str(e)}", OutputType.ERROR)

    except Exception as e:
        PrettyOutput.print(f"Initialization error: {str(e)}", OutputType.ERROR)
        return 1

    return 0

if __name__ == "__main__":
    exit(main()) 