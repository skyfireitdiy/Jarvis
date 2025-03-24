import argparse
import os

from prompt_toolkit import prompt
import yaml
from yaspin import yaspin
from jarvis.jarvis_agent import (
     PrettyOutput, OutputType,
     get_multiline_input,
     Agent,  # 显式导入关键组件
     origin_agent_system_prompt
)
from jarvis.jarvis_agent.patch import PatchOutputHandler
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.utils import init_env
from jarvis.jarvis_agent.file_input_handler import file_input_handler
from jarvis.jarvis_agent.shell_input_handler import shell_input_handler
from jarvis.jarvis_agent.builtin_input_handler import builtin_input_handler


def _load_tasks() -> dict:
    """Load tasks from .jarvis files in user home and current directory."""
    tasks = {}

    # Check .jarvis/pre-command in user directory
    user_jarvis = os.path.expanduser("~/.jarvis/pre-command")
    if os.path.exists(user_jarvis):
        with yaspin(text=f"从{user_jarvis}加载预定义任务...", color="cyan") as spinner:
            try:
                with open(user_jarvis, "r", encoding="utf-8", errors="ignore") as f:
                    user_tasks = yaml.safe_load(f)
                    
                if isinstance(user_tasks, dict):
                    # Validate and add user directory tasks
                    for name, desc in user_tasks.items():
                        if desc:  # Ensure description is not empty
                            tasks[str(name)] = str(desc)
                spinner.text = "预定义任务加载完成"
                spinner.ok("✅")
            except Exception as e:
                spinner.text = "预定义任务加载失败"
                spinner.fail("❌")
        
    # Check .jarvis/pre-command in current directory
    if os.path.exists(".jarvis/pre-command"):
        with yaspin(text=f"从{os.path.abspath('.jarvis/pre-command')}加载预定义任务...", color="cyan") as spinner:
            try:
                with open(".jarvis/pre-command", "r", encoding="utf-8", errors="ignore") as f:
                    local_tasks = yaml.safe_load(f)
                    
                if isinstance(local_tasks, dict):
                    # Validate and add current directory tasks, overwrite user directory tasks if there is a name conflict
                    for name, desc in local_tasks.items():
                        if desc:  # Ensure description is not empty
                            tasks[str(name)] = str(desc)
                spinner.text = "预定义任务加载完成"
                spinner.ok("✅")
            except Exception as e:
                spinner.text = "预定义任务加载失败"
                spinner.fail("❌")

    return tasks

def _select_task(tasks: dict) -> str:
    """Let user select a task from the list or skip. Returns task description if selected."""
    if not tasks:
        return ""
    # Convert tasks to list for ordered display
    task_names = list(tasks.keys())
    
    task_list = ["可用任务:"]
    for i, name in enumerate(task_names, 1):
        task_list.append(f"[{i}] {name}")
    task_list.append("[0] 跳过预定义任务")
    PrettyOutput.print("\n".join(task_list), OutputType.INFO)
    
    
    while True:
        try:
            choice = prompt(
                "\n请选择一个任务编号（0 跳过预定义任务）：",
            ).strip()
            
            if not choice:
                return ""
            
            choice = int(choice)
            if choice == 0:
                return ""
            elif 1 <= choice <= len(task_names):
                selected_name = task_names[choice - 1]
                return tasks[selected_name]  # Return the task description
            else:
                PrettyOutput.print("无效的选择。请选择列表中的一个号码。", OutputType.WARNING)
                
        except KeyboardInterrupt:
            return ""  # Return empty on Ctrl+C
        except EOFError:
            return ""  # Return empty on Ctrl+D
        except Exception as e:
            PrettyOutput.print(f"选择任务失败: {str(e)}", OutputType.ERROR)
            continue




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
            input_handler=[file_input_handler, shell_input_handler, builtin_input_handler], # type: ignore
            output_handler=[ToolRegistry(), PatchOutputHandler()],
            need_summary=False
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
