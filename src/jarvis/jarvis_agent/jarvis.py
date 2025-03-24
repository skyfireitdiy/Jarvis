import argparse
from typing import Any
from . import (
    init_env, PrettyOutput, OutputType, 
    file_input_handler, shell_input_handler, builtin_input_handler,
    _load_tasks, _select_task, get_multiline_input,
    PlatformRegistry, ToolRegistry, PatchOutputHandler, Agent,
    origin_agent_system_prompt
)

def main() -> int:
    """Jarvis main entry point"""
    init_env()
    parser = argparse.ArgumentParser(description='Jarvis AI assistant')
    parser.add_argument('-p', '--platform', type=str, help='Platform to use')
    parser.add_argument('-m', '--model', type=str, help='Model to use')
    args = parser.parse_args()

    try:
        agent = Agent(
            system_prompt=origin_agent_system_prompt,
            platform=args.platform,
            model_name=args.model,
            input_handler=[file_input_handler, shell_input_handler, builtin_input_handler],
            output_handler=[ToolRegistry(), PatchOutputHandler()]
        )

        tasks = _load_tasks()
        if tasks:
            selected_task = _select_task(tasks)
            if selected_task:
                PrettyOutput.print(f"执行任务: {selected_task}", OutputType.INFO)
                agent.run(selected_task)
                return 0
        
        user_input = get_multiline_input("请输入你的任务（输入空行退出）:")
        if user_input:
            agent.run(user_input)
        return 0

    except Exception as e:
        PrettyOutput.print(f"初始化错误: {str(e)}", OutputType.ERROR)
        return 1

if __name__ == "__main__":
    exit(main())
