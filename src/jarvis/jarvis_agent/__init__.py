import argparse
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from prompt_toolkit import prompt
import yaml

from jarvis.jarvis_agent.output_handler import OutputHandler
from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils import PrettyOutput, OutputType, get_context_token_count, is_auto_complete, is_execute_tool_confirm, is_need_summary, is_record_methodology, load_methodology, set_agent, delete_agent, get_max_token_count, get_multiline_input, init_env, is_use_methodology, make_agent_name,  user_confirm
import os

class Agent:

    def set_summary_prompt(self, summary_prompt: str):
        """Set the summary prompt for task completion.
        
        Args:
            summary_prompt: The prompt template for generating task summaries
        """
        self.summary_prompt = summary_prompt

    def __del__(self):
        delete_agent(self.name)

        
    def __init__(self, 
                 system_prompt: str, 
                 name: str = "Jarvis", 
                 description: str = "",
                 is_sub_agent: bool = False, 
                 platform: Union[Optional[BasePlatform], Optional[str]] = None, 
                 model_name: Optional[str] = None,
                 summary_prompt: Optional[str] = None, 
                 auto_complete: Optional[bool] = None, 
                 output_handler: List[OutputHandler] = [],
                 input_handler: Optional[List[Callable]] = None,
                 use_methodology: Optional[bool] = None,
                 record_methodology: Optional[bool] = None,
                 need_summary: Optional[bool] = None,
                 max_context_length: Optional[int] = None,
                 execute_tool_confirm: Optional[bool] = None):
        self.name = make_agent_name(name)
        self.description = description
        # 初始化平台和模型
        if platform is not None:
            if isinstance(platform, str):
                self.model = PlatformRegistry().create_platform(platform)
                if self.model is None:
                    PrettyOutput.print(f"平台 {platform} 不存在，将使用普通模型", OutputType.WARNING)
                    self.model = PlatformRegistry().get_normal_platform()
            else:
                self.model = platform
        else:
            self.model = PlatformRegistry.get_global_platform_registry().get_normal_platform()

        if model_name is not None:
            self.model.set_model_name(model_name)


        self.output_handler = output_handler

        
        self.record_methodology = record_methodology if record_methodology is not None else is_record_methodology()
        self.use_methodology = use_methodology if use_methodology is not None else is_use_methodology()
        self.is_sub_agent = is_sub_agent
        self.prompt = ""
        self.conversation_length = 0  # Use length counter instead
        self.system_prompt = system_prompt
        self.need_summary = need_summary if need_summary is not None else is_need_summary()
        self.input_handler = input_handler if input_handler is not None else []
        # Load configuration from environment variables


        self.execute_tool_confirm = execute_tool_confirm if execute_tool_confirm is not None else is_execute_tool_confirm()

        self.summary_prompt = summary_prompt if summary_prompt else f"""Please generate a concise summary report of the task execution, including:

1. Task Objective: Task restatement
2. Execution Result: Success/Failure
3. Key Information: Important information extracted during execution
4. Important Findings: Any noteworthy discoveries
5. Follow-up Suggestions: If any

Please describe in concise bullet points, highlighting important information.
"""
        
        self.max_token_count = max_context_length if max_context_length is not None else get_max_token_count()
        self.auto_complete = auto_complete if auto_complete is not None else is_auto_complete()
        welcome_message = f"{name} 初始化完成 - 使用 {self.model.name()} 模型"

        PrettyOutput.print(welcome_message, OutputType.SYSTEM)
        
        tool_prompt = """
# 🧰 Available Tools
The following tools are at your disposal:
"""

        # 添加工具列表概览
        tool_prompt += "\n## Tool List\n"
        tool_prompt += ", ".join([handler.name() for handler in self.output_handler])

        # 添加每个工具的详细说明
        tool_prompt += "\n\n# 📝 Tool Details\n"
        for handler in self.output_handler:
            tool_prompt += f"\n## {handler.name()}\n"
            # 获取工具的提示词并确保格式正确
            handler_prompt = handler.prompt().strip()
            # 调整缩进以保持层级结构
            handler_prompt = "\n".join("   " + line if line.strip() else line 
                                      for line in handler_prompt.split("\n"))
            tool_prompt += handler_prompt + "\n"

        # 添加工具使用总结
        tool_prompt += """
# ❗ Important Tool Usage Rules
1. Use ONE tool at a time
2. Follow each tool's format exactly
3. Wait for tool results before next action
4. Process results before new tool calls
5. Request help if tool usage is unclear
"""

        complete_prompt = ""
        if self.auto_complete:
            complete_prompt = """
            ## Task Completion
            When the task is completed, you should print the following message:
            <!!!COMPLETE!!!>
            """

        self.model.set_system_message(f"""
{self.system_prompt}

{tool_prompt}

{complete_prompt}
""")
        self.first = True


    
    def _call_model(self, message: str) -> str:
        """Call the AI model with retry logic.
        
        Args:
            message: The input message for the model
            
        Returns:
            str: Model's response
            
        Note:
            Will retry with exponential backoff up to 30 seconds between retries
        """
        sleep_time = 5

            message = handler(message, self)
        for handler in self.input_handler:
            message = handler(message)

        while True:
            ret = self.model.chat_until_success(message) # type: ignore
            if ret:
                return ret
            else:
                PrettyOutput.print(f"模型调用失败，正在重试... 等待 {sleep_time}s", OutputType.INFO)
                time.sleep(sleep_time)
                sleep_time *= 2
                if sleep_time > 30:
                    sleep_time = 30
                continue


    def _summarize_and_clear_history(self) -> None:
        """Summarize current conversation and clear history.
        
        This method will:
        1. Generate a summary of key information
        2. Clear the conversation history
        3. Keep the system message
        4. Add summary as new context
        5. Reset conversation length
        
        Note:
            Used when context length exceeds maximum
        """
        # Create a new model instance to summarize, avoid affecting the main conversation

        PrettyOutput.print("总结对话历史，准备生成摘要，开始新对话...", OutputType.PROGRESS)
        
        prompt = """Please summarize the key information from the previous conversation, including:
1. Current task objective
2. Confirmed key information
3. Solutions that have been tried
4. Current progress
5. Pending issues

Please describe in concise bullet points, highlighting important information. Do not include conversation details.
"""
        
        try:
            summary = self._call_model(self.prompt + "\n" + prompt)
            
            # 清空当前对话历史，但保留系统消息
            self.conversation_length = 0  # Reset conversation length
            
            # 添加总结作为新的上下文
            self.prompt = f"""Here is a summary of key information from previous conversations:

{summary}

Please continue the task based on the above information.
"""
            self.conversation_length = len(self.prompt)  # 设置新的起始长度
            
        except Exception as e:
            PrettyOutput.print(f"总结对话历史失败: {str(e)}", OutputType.ERROR)

    def _call_tools(self, response: str) -> Tuple[bool, Any]:
        tool_list = []
        for handler in self.output_handler:
            if handler.can_handle(response):
                tool_list.append(handler)
        if len(tool_list) > 1:
            PrettyOutput.print(f"操作失败：检测到多个操作。一次只能执行一个操作。尝试执行的操作：{', '.join([handler.name() for handler in tool_list])}", OutputType.ERROR)
            return False, f"Action failed: Multiple actions detected. Please only perform one action at a time. Actions attempted: {', '.join([handler.name() for handler in tool_list])}"
        if len(tool_list) == 0:
            return False, ""
        if not self.execute_tool_confirm or user_confirm(f"需要执行{tool_list[0].name()}确认执行？", True):
            return tool_list[0].handle(response)
        return False, ""
        

    def _complete_task(self) -> str:
        """Complete the current task and generate summary if needed.
        
        Returns:
            str: Task summary or completion status
            
        Note:
            - For main agent: May generate methodology if enabled
            - For sub-agent: May generate summary if enabled
        """
        PrettyOutput.section("任务完成", OutputType.SUCCESS)
        
        if not self.is_sub_agent:
            if self.record_methodology:

                try:
                    # 让模型判断是否需要生成方法论
                    analysis_prompt = """The current task has ended, please analyze whether a methodology needs to be generated.
    If you think a methodology should be generated, first determine whether to create a new methodology or update an existing one. If updating an existing methodology, use 'update', otherwise use 'add'.
    If you think a methodology is not needed, please explain why.
    The methodology should be applicable to general scenarios, do not include task-specific information such as code commit messages.
    The methodology should include: problem restatement, optimal solution, notes (as needed), and nothing else.
    Only output the methodology tool call instruction, or the explanation for not generating a methodology. Do not output anything else.
    """
                    self.prompt = analysis_prompt
                    response = self._call_model(self.prompt)
                    
                    self._call_tools(response)
                    
                except Exception as e:
                    PrettyOutput.print(f"生成方法论失败: {str(e)}", OutputType.ERROR)
            
            return "任务完成"
        
        if self.need_summary:
            self.prompt = self.summary_prompt
            return self._call_model(self.prompt)
        
        return "任务完成"


    def run(self, user_input: str, file_list: Optional[List[str]] = None) -> Any:
        """Process user input and execute the task.
        
        Args:
            user_input: User's task description or request
            file_list: Optional list of files to process
            
        Returns:
            str|Dict: Task summary report or message to send
        """
        try:
            set_agent(self.name, self)
            PrettyOutput.section("准备环境", OutputType.PLANNING)
            if file_list:
                self.model.upload_files(file_list) # type: ignore

            # 显示任务开始
            PrettyOutput.section(f"开始新任务: {self.name}", OutputType.PLANNING)

            self.prompt = f"{user_input}"

            if self.first:
                if self.use_methodology:
                    self.prompt = f"{user_input}\n\n{load_methodology(user_input)}"
                self.first = False

            while True:
                try:
                    # 显示思考状态
                    PrettyOutput.print("正在分析任务...", OutputType.PROGRESS)
                    
                    # 累加对话长度
                    self.conversation_length += get_context_token_count(self.prompt)
                    
                    # 如果对话历史长度超过限制，在提示中添加提醒
                    if self.conversation_length > self.max_token_count:
                        current_response = self._summarize_and_clear_history()
                        continue
                    else:
                        current_response = self._call_model(self.prompt)
                        self.prompt = ""
                        self.conversation_length += get_context_token_count(current_response)

                    need_return, self.prompt = self._call_tools(current_response)

                    if need_return:
                        return self.prompt
                    
                    if self.prompt:
                        continue

                    if self.auto_complete and "<!!!COMPLETE!!!>" in current_response:
                        return self._complete_task()
                    
                    # 获取用户输入
                    user_input = get_multiline_input(f"{self.name}: 您可以继续输入，或输入空行来结束当前任务：")

                    if user_input:
                        self.prompt = user_input
                        continue
                    
                    if not user_input:
                        return self._complete_task()

                except Exception as e:
                    PrettyOutput.print(f"任务失败: {str(e)}", OutputType.ERROR)
                    return f"Task failed: {str(e)}"

        except Exception as e:
            PrettyOutput.print(f"任务失败: {str(e)}", OutputType.ERROR)
            return f"Task failed: {str(e)}"

    def _clear_history(self):
        """Clear conversation history while preserving system prompt.
        
        This will:
        1. Clear the prompt
        2. Reset the model
        3. Reset conversation length counter
        """
        self.prompt = "" 
        self.model.reset() # type: ignore
        self.conversation_length = 0  # Reset conversation length




def _load_tasks() -> dict:
    """Load tasks from .jarvis files in user home and current directory."""
    tasks = {}
    
    # Check .jarvis/pre-command in user directory
    user_jarvis = os.path.expanduser("~/.jarvis/pre-command")
    if os.path.exists(user_jarvis):
        try:
            with open(user_jarvis, "r", encoding="utf-8") as f:
                user_tasks = yaml.safe_load(f)
                
            if isinstance(user_tasks, dict):
                # Validate and add user directory tasks
                for name, desc in user_tasks.items():
                    if desc:  # Ensure description is not empty
                        tasks[str(name)] = str(desc)
            else:
                PrettyOutput.print("警告: ~/.jarvis/pre-command 文件应该包含一个字典，键为任务名称，值为任务描述", OutputType.ERROR)
        except Exception as e:
            PrettyOutput.print(f"加载 ~/.jarvis/pre-command 文件失败: {str(e)}", OutputType.ERROR)
    
    # Check .jarvis/pre-command in current directory
    if os.path.exists(".jarvis/pre-command"):
        try:
            with open(".jarvis/pre-command", "r", encoding="utf-8") as f:
                local_tasks = yaml.safe_load(f)
                
            if isinstance(local_tasks, dict):
                # Validate and add current directory tasks, overwrite user directory tasks if there is a name conflict
                for name, desc in local_tasks.items():
                    if desc:  # Ensure description is not empty
                        tasks[str(name)] = str(desc)
            else:
                PrettyOutput.print("警告: .jarvis/pre-command 文件应该包含一个字典，键为任务名称，值为任务描述", OutputType.ERROR)
        except Exception as e:
            PrettyOutput.print(f"加载 .jarvis/pre-command 文件失败: {str(e)}", OutputType.ERROR)

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

origin_agent_system_prompt = """
# 🤖 Role Definition
You are Jarvis, an AI assistant with powerful problem-solving capabilities. You communicate in the user's language (if user speaks Chinese, respond in Chinese).

# 🎯 Core Responsibilities
- Process and analyze problems systematically
- Generate and execute actionable solutions
- Document methodologies for future reference
- Monitor and adjust execution plans
- Ensure task completion

# 🔄 Problem-Solving Workflow
1. Problem Analysis
   - Restate the problem to confirm understanding
   - Analyze root causes (for problem analysis tasks)
   - Define clear, achievable objectives

2. Solution Design
   - Generate multiple actionable solutions
   - Evaluate and select optimal solution
   - Create detailed action plan using PlantUML

3. Execution
   - Execute one step at a time
   - Use only ONE tool per step
   - Wait for tool results before proceeding
   - Monitor results and adjust as needed

4. Task Completion
   - Verify goal completion
   - Document methodology if valuable
   - Use completion command to end task

# 📑 Methodology Template
```markdown
# [Problem Title]
## Problem Restatement
[Clear problem definition]

## Optimal Solution
[Selected solution approach]

## Solution Steps
1. [Step 1]
2. [Step 2]
3. [Step 3]
...
```

# ⚖️ Operating Principles
- ONE tool per action
- Wait for results before next step
- Adjust plans based on feedback
- Document reusable solutions
- Use completion command to end tasks

# ❗ Important Rules
1. Always use only ONE tool per action
2. Always wait for tool execution results
3. Always verify task completion
4. Always communicate in user's language
5. Always document valuable methodologies
"""

def main():
    """Jarvis main entry point"""
    # Add argument parser
    init_env()
    parser = argparse.ArgumentParser(description='Jarvis AI assistant')
    parser.add_argument('-f', '--files', nargs='*', help='List of files to process')
    parser.add_argument('-p', '--platform', type=str, help='Platform to use')
    parser.add_argument('-m', '--model', type=str, help='Model to use')
    args = parser.parse_args()

    try:
        # 获取全局模型实例
        agent = Agent(system_prompt=origin_agent_system_prompt, platform=args.platform, model_name=args.model, output_handler=[ToolRegistry()])

        # 加载预定义任务
        tasks = _load_tasks()
        if tasks:
            selected_task = _select_task(tasks)
            if selected_task:
                PrettyOutput.print(f"执行任务: {selected_task}", OutputType.INFO)
                agent.run(selected_task, args.files)
                return 0
        
        # 如果没有选择预定义任务，进入交互模式
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
