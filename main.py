import os
import argparse
from colorama import init, Fore, Style
from dotenv import load_dotenv

from utils.logger import Logger as ColorLogger
from tools import ShellTool, PythonTool, MathTool
from agent import LlamaAgent
from llm import OllamaLLM, OpenAILLM

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

def main():
    # Load environment variables from .env file
    load_dotenv()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Jarvis AI Assistant')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Print detailed interaction logs with LLM')
    parser.add_argument('--model', choices=['ollama', 'openai', 'custom'], 
                       default='ollama',
                       help='Choose LLM provider (default: ollama)')
    parser.add_argument('--model-name', default=None,
                       help='Specific model name to use')
    parser.add_argument('--custom-module',
                       help='Python module containing custom LLM implementation')
    parser.add_argument('--llm-params', nargs='+',
                       help='Additional LLM parameters in format key=value')
    
    args = parser.parse_args()
    
    # Initialize colorama
    init()
    
    # Parse LLM parameters
    llm_params = {}
    if args.llm_params:
        for param in args.llm_params:
            try:
                key, value = param.split('=', 1)
                # Try to convert value to appropriate type
                try:
                    value = eval(value)  # Safely evaluate numbers, bools, etc.
                except:
                    pass  # Keep as string if eval fails
                llm_params[key] = value
            except ValueError:
                print(f"{Fore.YELLOW}Warning: Ignoring invalid parameter format: {param}{Style.RESET_ALL}")
    
    # Setup LLM based on arguments
    if args.model == 'openai':
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            print(f"{Fore.RED}Error: OPENAI_API_KEY environment variable not set{Style.RESET_ALL}")
            return
        llm = OpenAILLM(
            model_name=args.model_name or "gpt-3.5-turbo",
            api_key=api_key,
            **llm_params
        )
    elif args.model == 'custom':
        if not args.custom_module:
            print(f"{Fore.RED}Error: --custom-module required for custom LLM{Style.RESET_ALL}")
            return
        try:
            if args.custom_module == 'zte_llm':
                from llm import create_zte_llm
                llm = create_zte_llm(**llm_params)
            else:
                import importlib
                custom_module = importlib.import_module(args.custom_module)
                llm = custom_module.create_llm(**llm_params)
        except Exception as e:
            print(f"{Fore.RED}Error loading custom LLM: {str(e)}{Style.RESET_ALL}")
            return
    else:
        llm = OllamaLLM(
            model_name=args.model_name or "llama3:latest",
            **llm_params
        )
    
    # Create agent with chosen LLM
    agent = LlamaAgent(llm=llm, verbose=args.verbose)
    
    # Register tools
    agent.register_tool(ShellTool(tool_id="shell"))
    agent.register_tool(PythonTool(tool_id="python"))
    agent.register_tool(MathTool(tool_id="math"))
    
    # Print welcome message
    print(f"{Fore.GREEN}🤖 Welcome to Jarvis AI Assistant!{Style.RESET_ALL}")
    print(f"Using LLM: {llm.get_model_name()}")
    
    # Get task from user with multiline support
    task = get_multiline_input("Please enter your task description (or press Enter for default task)")
    
    # Use default task if none provided
    if not task:
        task = "Show current time and date"
    
    # Execute task
    agent.execute_task(task)

if __name__ == "__main__":
    main()
