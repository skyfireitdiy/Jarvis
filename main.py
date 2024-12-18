import os
import argparse
from colorama import init, Fore, Style
import ollama

from logger import ColorLogger
from tools import ShellTool, PythonTool, MathTool
from agent import LlamaAgent

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Jarvis AI Assistant')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Print detailed interaction logs with LLM')
    args = parser.parse_args()
    
    # Initialize colorama
    init()
    
    # Create agent with verbose setting
    agent = LlamaAgent(verbose=args.verbose)
    
    # Register tools with correct IDs
    agent.register_tool(ShellTool(tool_id="shell"))
    agent.register_tool(PythonTool(tool_id="python"))  # Changed from "python (execution)"
    agent.register_tool(MathTool(tool_id="math"))
    
    # Print welcome message
    print(f"{Fore.GREEN}🤖 Welcome to Jarvis AI Assistant!{Style.RESET_ALL}")
    
    # Get task from user
    print("Please enter your task description (or press Enter for default task):")
    task = input("> ").strip()
    
    # Use default task if none provided
    if not task:
        task = "Show current time and date"
    
    # Execute task
    agent.execute_task(task)

if __name__ == "__main__":
    main()
