import argparse
import time
from typing import Callable, Dict, List, Optional

from prompt_toolkit import prompt
import yaml

from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry, tool_call_help
from jarvis.utils import PrettyOutput, OutputType, get_context_token_count, is_auto_complete, is_execute_tool_confirm, is_need_summary, is_record_methodology, load_methodology, add_agent, delete_current_agent, get_max_token_count, get_multiline_input, init_env, is_use_methodology, user_confirm
import os

class Agent:

    def set_summary_prompt(self, summary_prompt: str):
        """Set the summary prompt for task completion.
        
        Args:
            summary_prompt: The prompt template for generating task summaries
        """
        self.summary_prompt = summary_prompt

    def set_output_handler_before_tool(self, handler: List[Callable]):
        """Set handlers to process output before tool execution.
        
        Args:
            handler: List of callable functions to process output
        """
        self.output_handler_before_tool = handler
        
    def __init__(self, 
                 system_prompt: str, 
                 name: str = "Jarvis", 
                 is_sub_agent: bool = False, 
                 tool_registry: Optional[ToolRegistry] = None, 
                 platform: Optional[BasePlatform] = None, 
                 summary_prompt: Optional[str] = None, 
                 auto_complete: Optional[bool] = None, 
                 output_handler_before_tool: Optional[List[Callable]] = None,
                 output_handler_after_tool: Optional[List[Callable]] = None,
                 input_handler: Optional[List[Callable]] = None,
                 use_methodology: Optional[bool] = None,
                 record_methodology: Optional[bool] = None,
                 need_summary: Optional[bool] = None,
                 max_context_length: Optional[int] = None,
                 execute_tool_confirm: Optional[bool] = None):
        """Initialize an Agent instance.
        
        Args:
            system_prompt: The system prompt defining agent behavior
            name: Agent name, defaults to "Jarvis"
            is_sub_agent: Whether this is a sub-agent
            tool_registry: Registry of available tools
            platform: AI platform to use
            summary_prompt: Template for generating summaries
            auto_complete: Whether to enable auto-completion
            output_handler_before_tool: Handlers to process output before tool execution
            output_handler_after_tool: Handlers to process output after tool execution
            use_methodology: Whether to use methodology
            record_methodology: Whether to record methodology
            need_summary: Whether to generate summaries
            max_context_length: Maximum context length
        """
        PrettyOutput.print(f"欢迎使用Jarvis，你的AI助手，正在初始化...", OutputType.SYSTEM)
        if platform is not None:
            self.model = platform
        else:
            self.model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
        self.tool_registry = tool_registry if tool_registry else ToolRegistry()
        self.record_methodology = record_methodology if record_methodology is not None else is_record_methodology()
        self.use_methodology = use_methodology if use_methodology is not None else is_use_methodology()
        self.name = name
        self.is_sub_agent = is_sub_agent
        self.prompt = ""
        self.conversation_length = 0  # Use length counter instead
        self.system_prompt = system_prompt
        self.need_summary = need_summary if need_summary is not None else is_need_summary()
        self.input_handler = input_handler if input_handler is not None else []
        # Load configuration from environment variables
        self.output_handler_before_tool = output_handler_before_tool if output_handler_before_tool else []
        self.output_handler_after_tool = output_handler_after_tool if output_handler_after_tool else []

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

        PrettyOutput.section(f"Jarvis 初始化完成 - 使用 {self.model.name()} 模型", OutputType.SYSTEM)

        tools = self.tool_registry.get_all_tools()
        if tools:
            PrettyOutput.section(f"可用工具: {', '.join([tool['name'] for tool in tools])}", OutputType.SYSTEM)

        
        tools_prompt = self.tool_registry.load_tools()
        complete_prompt = """"""
        if self.auto_complete:
            complete_prompt = """
            ## Task Completion
            When the task is completed, you should print the following message:
            <!!!COMPLETE!!!>
            """

        self.model.set_system_message(f"""
{self.system_prompt}

{tools_prompt}

{complete_prompt}
""")
        self.first = True

    @staticmethod
    def _extract_tool_calls(content: str) -> List[Dict]:
        """Extract tool calls from content.
        
        Args:
            content: The content containing tool calls
            
        Returns:
            List[Dict]: List of extracted tool calls with name and arguments
            
        Raises:
            Exception: If tool call is missing necessary fields
        """
        # Split content into lines
        lines = content.split('\n')
        tool_call_lines = []
        in_tool_call = False


        # Process line by line
        for line in lines:
            if '<TOOL_CALL>' in line:
                in_tool_call = True
                continue
            elif '</TOOL_CALL>' in line:
                if in_tool_call and tool_call_lines:
                    # Parse YAML directly
                    tool_call_text = '\n'.join(tool_call_lines)
                    tool_call_data = yaml.safe_load(tool_call_text)
                    
                    # Validate necessary fields
                    if "name" in tool_call_data and "arguments" in tool_call_data:
                        # Return content before tool call and tool call
                        return [{
                            "name": tool_call_data["name"],
                            "arguments": tool_call_data["arguments"]
                        }]
                    else:
                        raise Exception("Tool call missing necessary fields")
                in_tool_call = False
                continue
            
            if in_tool_call:
                tool_call_lines.append(line)
        
        return []

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

        for handler in self.input_handler:
            message = handler(message)

        while True:
            ret = self.model.chat_until_success(message)
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
                    
                    # 检查是否包含工具调用
                    try:
                        tool_calls = Agent._extract_tool_calls(response)
                        if tool_calls:
                            self.tool_registry.handle_tool_calls(tool_calls)
                    except Exception as e:
                        PrettyOutput.print(f"处理方法论生成失败: {str(e)}", OutputType.ERROR)
                    
                except Exception as e:
                    PrettyOutput.print(f"生成方法论失败: {str(e)}", OutputType.ERROR)
            
            return "任务完成"
        
        if self.need_summary:
            self.prompt = self.summary_prompt
            return self._call_model(self.prompt)
        
        return "任务完成"


    def run(self, user_input: str, file_list: Optional[List[str]] = None) -> str:
        """Process user input and execute the task.
        
        Args:
            user_input: User's task description or request
            file_list: Optional list of files to process
            
        Returns:
            str: Task summary report
            
        Note:
            - Handles context management
            - Processes tool calls
            - Manages conversation flow
            - Supports interactive mode
        """

        add_agent(self.name)

        try:
            PrettyOutput.section("准备环境", OutputType.PLANNING)
            if file_list:
                self.model.upload_files(file_list)

            # 显示任务开始
            PrettyOutput.section(f"开始新任务: {self.name}", OutputType.PLANNING)

            if self.first and self.use_methodology:
                self.prompt = f"{user_input}\n\n{load_methodology(user_input)}"
                self.first = False
            else:
                self.prompt = f"{user_input}"

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

                    for handler in self.output_handler_before_tool:
                        self.prompt += handler(current_response)

                    try:
                        result = Agent._extract_tool_calls(current_response)
                    except Exception as e:
                        PrettyOutput.print(f"工具调用错误: {str(e)}", OutputType.ERROR)
                        self.prompt += f"Tool call error: {str(e)}"
                        continue
                    
                    if len(result) > 0:
                        if not self.execute_tool_confirm or user_confirm(f"执行工具调用: {result[0]['name']}?"):
                            PrettyOutput.print("正在执行工具调用...", OutputType.PROGRESS)
                            tool_result = self.tool_registry.handle_tool_calls(result)
                            self.prompt += tool_result
                            
                    for handler in self.output_handler_after_tool:
                        self.prompt += handler(current_response)
                    
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
        
        finally:
            delete_current_agent()

    def _clear_history(self):
        """Clear conversation history while preserving system prompt.
        
        This will:
        1. Clear the prompt
        2. Reset the model
        3. Reset conversation length counter
        """
        self.prompt = "" 
        self.model.reset()
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

    
    if is_use_methodology():
        # Read methodology
        method_path = os.path.expanduser("~/.jarvis/methodology")
        if os.path.exists(method_path):
            with open(method_path, "r", encoding="utf-8") as f:
                methodology = yaml.safe_load(f)
            if isinstance(methodology, dict):
                for name, desc in methodology.items():
                    tasks[f"Run Methodology: {str(name)}\n {str(desc)}" ] = str(desc)
    
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
                PrettyOutput.print("无效的选择。请选择列表中的一个号码。", OutputType.ERROR)
                
        except KeyboardInterrupt:
            return ""  # Return empty on Ctrl+C
        except EOFError:
            return ""  # Return empty on Ctrl+D
        except Exception as e:
            PrettyOutput.print(f"选择任务失败: {str(e)}", OutputType.ERROR)
            continue

origin_agent_system_prompt = """You are Jarvis, an AI assistant with powerful problem-solving capabilities.

When users need to execute tasks, you will strictly follow these steps to handle problems:
1. Problem Restatement: Confirm understanding of the problem
2. Root Cause Analysis (only if needed for problem analysis tasks)
3. Set Objectives: Define achievable and verifiable goals
4. Generate Solutions: Create one or more actionable solutions
5. Evaluate Solutions: Select the optimal solution from multiple options
6. Create Action Plan: Based on available tools, create an action plan using PlantUML format for clear execution flow
7. Execute Action Plan: Execute one step at a time, **use at most one tool** (wait for tool execution results before proceeding)
8. Monitor and Adjust: If execution results don't match expectations, reflect and adjust the action plan, iterate previous steps
9. Methodology: If the current task has general applicability and valuable experience is gained, use methodology tools to record it for future similar problems
10. Auto check the task goal completion status: If the task goal is completed, use the task completion command to end the task
11. Task Completion: End the task using task completion command when finished

Tip: Chat in user's language

Methodology Template:
1. Problem Restatement
2. Optimal Solution
3. Optimal Solution Steps (exclude failed actions)

-------------------------------------------------------------"""

def main():
    """Jarvis main entry point"""
    # Add argument parser
    init_env()
    parser = argparse.ArgumentParser(description='Jarvis AI assistant')
    parser.add_argument('-f', '--files', nargs='*', help='List of files to process')
    args = parser.parse_args()

    try:
        # 获取全局模型实例
        agent = Agent(system_prompt=origin_agent_system_prompt)

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
