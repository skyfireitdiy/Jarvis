import os
from colorama import init, Fore, Style
import ollama

from logger import ColorLogger
from execution_tools import ShellTool, PythonTool, MathTool
from agent import LlamaAgent

def main():
    # Initialize colorama
    init()
    
    # Create agent
    agent = LlamaAgent()
    
    # Register tools
    agent.register_tool(ShellTool())
    agent.register_tool(PythonTool())
    agent.register_tool(MathTool())
    
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
