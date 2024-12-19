import os
import argparse
from colorama import init, Fore, Style
from dotenv import load_dotenv
from typing import Dict, Any, Optional

from utils.logger import Logger as ColorLogger
from tools import AutoRegisteringToolRegistry
from agent import LlamaAgent
from llm import OllamaLLM, OpenAILLM, BaseLLM

def get_multiline_input(prompt: str = "") -> str:
    """Get multiline input from user. Empty line to finish."""
    print(f"{prompt} (Enter empty line to finish):")
    lines = []
    while True:
        try:
            line = input("> ").strip()
            if not line and lines:  # Empty line and we have content
                break
            if line:  # Add non-empty lines
                lines.append(line)
        except EOFError:
            break
        except KeyboardInterrupt:
            print("\nInput cancelled")
            return ""
    return "\n".join(lines)

def parse_llm_params(params_list: Optional[list] = None) -> Dict[str, Any]:
    """Parse LLM parameters from command line arguments"""
    llm_params = {}
    if not params_list:
        return llm_params
        
    for param in params_list:
        try:
            key, value = param.split('=', 1)
            try:
                value = eval(value)
            except:
                pass
            llm_params[key] = value
        except ValueError:
            print(f"{Fore.YELLOW}Warning: Ignoring invalid parameter format: {param}{Style.RESET_ALL}")
    
    return llm_params

def setup_openai_llm(model_name: str, llm_params: Dict[str, Any]) -> Optional[BaseLLM]:
    """Setup OpenAI LLM"""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print(f"{Fore.RED}Error: OPENAI_API_KEY environment variable not set{Style.RESET_ALL}")
        return None
        
    return OpenAILLM(
        model_name=model_name or "gpt-3.5-turbo",
        api_key=api_key,
        **llm_params
    )

def setup_custom_llm(custom_module: str, llm_params: Dict[str, Any]) -> Optional[BaseLLM]:
    """Setup custom LLM"""
    if not custom_module:
        print(f"{Fore.RED}Error: --custom-module required for custom LLM{Style.RESET_ALL}")
        return None
        
    try:
        if custom_module == 'zte_llm':
            from llm import create_zte_llm
            return create_zte_llm(**llm_params)
        else:
            import importlib
            custom_module = importlib.import_module(custom_module)
            return custom_module.create_llm(**llm_params)
    except Exception as e:
        print(f"{Fore.RED}Error loading custom LLM: {str(e)}{Style.RESET_ALL}")
        return None

def setup_llm(args: argparse.Namespace) -> Optional[BaseLLM]:
    """Setup LLM based on command line arguments"""
    llm_params = parse_llm_params(args.llm_params)
    
    if args.model == 'openai':
        return setup_openai_llm(args.model_name, llm_params)
    elif args.model == 'custom':
        return setup_custom_llm(args.custom_module, llm_params)
    else:
        return OllamaLLM(
            model_name=args.model_name or "llama3:latest",
            **llm_params
        )

def setup_argument_parser() -> argparse.ArgumentParser:
    """Setup command line argument parser"""
    parser = argparse.ArgumentParser(description='Jarvis AI Assistant')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Print detailed interaction logs with LLM')
    parser.add_argument('--model', choices=['ollama', 'openai', 'custom'], 
                       default='ollama',
                       help='Choose LLM provider (default: ollama)')
    parser.add_argument('--model-name', default='llama3:latest',
                       help='Specific model name to use')
    parser.add_argument('--custom-module',
                       help='Python module containing custom LLM implementation')
    parser.add_argument('--llm-params', nargs='+',
                       help='Additional LLM parameters in format key=value')
    parser.add_argument('--tools-dir',
                       help='Directory containing additional tool implementations')
    return parser

def setup_tools(tools_dir: Optional[str] = None) -> AutoRegisteringToolRegistry:
    """Setup and discover tools"""
    tool_registry = AutoRegisteringToolRegistry(tools_dir=tools_dir)
    
    # Print discovered tools
    print(f"{Fore.CYAN}Discovered tools:{Style.RESET_ALL}")
    for tool_id in tool_registry.list_tools():
        print(f"  • {tool_id}")
    
    return tool_registry

def main():
    # Load environment variables from .env file
    load_dotenv()
    
    # Parse command line arguments
    parser = setup_argument_parser()
    args = parser.parse_args()
    
    # Initialize colorama
    init()
    
    # Setup LLM
    llm = setup_llm(args)
    if not llm:
        return
    
    # Create agent with chosen LLM
    agent = LlamaAgent(llm=llm, verbose=args.verbose)
    
    # Setup tools and register with agent
    tool_registry = setup_tools(args.tools_dir)
    agent.tool_registry = tool_registry  # 只需要一次设置工具注册表
    
    # Print welcome message
    print(f"{Fore.GREEN}🤖 Welcome to Jarvis AI Assistant!{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Using LLM: {llm.get_model_name()}{Style.RESET_ALL}")
    
    # Get task from user
    task = get_multiline_input("Please enter your task description (or press Enter for default task)")
    
    # Use default task if none provided
    if not task:
        task = "Show current time and date"
    
    # Execute task
    agent.execute_task(task)

if __name__ == "__main__":
    main()
