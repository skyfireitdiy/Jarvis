import argparse
import yaml
import os
from typing import Optional, List
from jarvis.jarvis_agent import Agent
from jarvis.jarvis_utils.output import PrettyOutput, OutputType
from jarvis.jarvis_utils.utils import init_env

# 从__init__.py导入系统提示
from jarvis.jarvis_agent import origin_agent_system_prompt

def load_config(config_path: str) -> dict:
    """Load configuration from YAML file
    
    Args:
        config_path: Path to the YAML configuration file
        
    Returns:
        dict: Configuration dictionary
    """
    if not os.path.exists(config_path):
        PrettyOutput.print(f"配置文件 {config_path} 不存在，使用默认配置", OutputType.WARNING)
        return {}
    
    with open(config_path, 'r', encoding='utf-8') as f:
        try:
            config = yaml.safe_load(f)
            return config if config else {}
        except yaml.YAMLError as e:
            PrettyOutput.print(f"配置文件解析失败: {str(e)}", OutputType.ERROR)
            return {}

def create_agent_from_config(config: dict) -> Agent:
    """Create Agent instance from configuration dictionary
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Agent: Initialized Agent instance
    """
    return Agent(
        system_prompt=config.get('system_prompt', origin_agent_system_prompt),
        name=config.get('name', "Jarvis"),
        description=config.get('description', ""),
        platform=config.get('platform'),
        model_name=config.get('model'),
        summary_prompt=config.get('summary_prompt'),
        auto_complete=config.get('auto_complete'),
        use_methodology=config.get('use_methodology'),
        record_methodology=config.get('record_methodology'),
        need_summary=config.get('need_summary'),
        max_context_length=config.get('max_context_length'),
        execute_tool_confirm=config.get('execute_tool_confirm')
    )

def main():
    """Main entry point for Jarvis agent"""
    # Initialize environment
    init_env()
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Jarvis AI assistant')
    parser.add_argument('-c', '--config', type=str, required=True, 
                        help='Path to the YAML configuration file')
    parser.add_argument('-f', '--files', nargs='*', 
                        help='List of files to process')
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Create agent from configuration
    try:
        agent = create_agent_from_config(config)
        
        # Run agent with initial task if specified
        initial_task = config.get('initial_task')
        if initial_task:
            PrettyOutput.print(f"执行初始任务: {initial_task}", OutputType.INFO)
            agent.run(initial_task, args.files)
            return 0
        
        # Enter interactive mode if no initial task
        while True:
            try:
                user_input = get_multiline_input("请输入你的任务（输入空行退出）:")
                if not user_input:
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
