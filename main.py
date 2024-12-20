#!/usr/bin/env python3
import os
import sys
import argparse
from typing import Optional, Dict
from colorama import init, Fore, Style
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from agent.llama_agent import LlamaAgent
from tools import ToolRegistry
from llm import create_llm

def parse_llm_params(params_list: Optional[list]) -> Dict:
    """Parse LLM parameters from command line"""
    if not params_list:
        return {}
    
    params = {}
    for param in params_list:
        key, value = param.split('=', 1)
        # Try to convert to appropriate type
        try:
            # Try as int
            params[key] = int(value)
        except ValueError:
            try:
                # Try as float
                params[key] = float(value)
            except ValueError:
                # Keep as string
                params[key] = value
    return params

def setup_llm(args):
    """Setup LLM based on command line arguments"""
    llm_params = parse_llm_params(args.llm_params)
    
    try:
        # Create LLM instance using the registry
        llm = create_llm(args.model_name, **llm_params)
        return llm
    except Exception as e:
        print(f"{Fore.RED}Error creating LLM: {e}{Style.RESET_ALL}")
        sys.exit(1)

def setup_argument_parser() -> argparse.ArgumentParser:
    """Setup command line argument parser"""
    parser = argparse.ArgumentParser(description='Jarvis AI Assistant')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Print detailed interaction logs with LLM')
    parser.add_argument('--model-name', default='ollama',
                       help='Name of the LLM to use (e.g. ollama, openai, zte)')
    parser.add_argument('--llm-params', nargs='+',
                       help='Additional LLM parameters in format key=value')
    parser.add_argument('--tools-dir',
                       help='Directory containing additional tool implementations')
    return parser

def setup_tools(tools_dir: Optional[str] = None) -> ToolRegistry:
    """Setup and discover tools"""
    # Create a new registry instance with the specified directory
    tool_registry = ToolRegistry(tools_dir=tools_dir)
    
    # Print discovered tools
    print(f"{Fore.CYAN}Discovered tools:{Style.RESET_ALL}")
    for tool_id in tool_registry.list_tools():
        print(f"  • {tool_id}")
    
    return tool_registry

def main():
    """Main entry point"""
    # Initialize colorama
    init()
    
    # Parse command line arguments
    parser = setup_argument_parser()
    args = parser.parse_args()
    
    # Setup LLM
    llm = setup_llm(args)
    print(f"{Fore.GREEN}Using LLM: {args.model_name}{Style.RESET_ALL}")
    
    # Setup tools
    tool_registry = setup_tools(args.tools_dir)
    
    # Create agent
    agent = LlamaAgent(llm=llm, tool_registry=tool_registry, verbose=args.verbose)
    
    # Start REPL
    print("\nWelcome to Jarvis! How can I help you today?")
    print("Type 'exit' or press Ctrl+C to quit")
    print(f"{Fore.CYAN}(For multiline input, press Enter twice or type 'done' to finish){Style.RESET_ALL}\n")
    
    while True:
        try:
            lines = []
            print(f"{Fore.GREEN}>{Style.RESET_ALL}", end=" ")
            while True:
                line = input().strip()
                if not line:
                    if not lines:  # First empty line without input
                        continue
                    break  # Second empty line or empty line after input
                if line.lower() == 'exit':
                    print("Exiting...")
                    return
                if line.lower() == 'done':
                    break
                lines.append(line)
            
            if not lines:
                continue
                
            task = "\n".join(lines)
            agent.process_input(task)
            
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\n{Fore.RED}Error: {str(e)}{Style.RESET_ALL}")
            if args.verbose:
                import traceback
                traceback.print_exc()

if __name__ == '__main__':
    main() 