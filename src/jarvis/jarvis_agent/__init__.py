import argparse
from typing import Any, Callable, List, Optional, Tuple, Union

from prompt_toolkit import prompt
import yaml

from jarvis.jarvis_agent.output_handler import OutputHandler
from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.output import PrettyOutput, OutputType
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.config import is_auto_complete, is_execute_tool_confirm, is_need_summary, is_record_methodology, is_use_methodology
from jarvis.jarvis_utils.methodology import load_methodology
from jarvis.jarvis_utils.globals import make_agent_name, set_agent, delete_agent
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.config import get_max_token_count
from jarvis.jarvis_utils.utils import init_env
from jarvis.jarvis_utils.utils import user_confirm
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
                 input_handler: Optional[List[Callable[[str, Any], Tuple[str, bool]]]] = None,
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

        self.summary_prompt = summary_prompt if summary_prompt else f"""请生成任务执行的简明总结报告，包括：

1. 任务目标：任务重述
2. 执行结果：成功/失败
3. 关键信息：执行过程中提取的重要信息
4. 重要发现：任何值得注意的发现
5. 后续建议：如果有的话

请使用简洁的要点描述，突出重要信息。
"""
        
        self.max_token_count = max_context_length if max_context_length is not None else get_max_token_count()
        self.auto_complete = auto_complete if auto_complete is not None else is_auto_complete()
        welcome_message = f"{name} 初始化完成 - 使用 {self.model.name()} 模型"

        PrettyOutput.print(welcome_message, OutputType.SYSTEM)
        
        action_prompt = """
# 🧰 可用操作
以下是您可以使用的操作：
"""

        # 添加工具列表概览
        action_prompt += "\n## Action List\n"
        action_prompt += ", ".join([handler.name() for handler in self.output_handler])

        # 添加每个工具的详细说明
        action_prompt += "\n\n# 📝 Action Details\n"
        for handler in self.output_handler:
            action_prompt += f"\n## {handler.name()}\n"
            # 获取工具的提示词并确保格式正确
            handler_prompt = handler.prompt().strip()
            # 调整缩进以保持层级结构
            handler_prompt = "\n".join("   " + line if line.strip() else line 
                                      for line in handler_prompt.split("\n"))
            action_prompt += handler_prompt + "\n"

        # 添加工具使用总结
        action_prompt += """
# ❗ 重要操作使用规则
1. 一次只使用一个操作
2. 严格按照每个操作的格式执行
3. 等待操作结果后再进行下一个操作
4. 处理完结果后再调用新的操作
5. 如果对操作使用不清楚，请请求帮助
"""

        complete_prompt = ""
        if self.auto_complete:
            complete_prompt = """
            ## 任务完成
            当任务完成时，你应该打印以下信息：
            <!!!COMPLETE!!!>
            """

        self.model.set_system_message(f"""
{self.system_prompt}

{action_prompt}

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
        for handler in self.input_handler:
            message, need_return = handler(message, self)
            if need_return:
                return message
        return self.model.chat_until_success(message)   # type: ignore



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
        
        prompt = """请总结之前对话中的关键信息，包括：
1. 当前任务目标
2. 已确认的关键信息
3. 已尝试的解决方案
4. 当前进展
5. 待解决的问题

请用简洁的要点形式描述，突出重要信息。不要包含对话细节。
"""
        
        try:
            summary = self._call_model(self.prompt + "\n" + prompt)
            
            # 清空当前对话历史，但保留系统消息
            self.conversation_length = 0  # Reset conversation length
            
            # 添加总结作为新的上下文
            self.prompt = f"""以下是之前对话的关键信息总结：

{summary}

请基于以上信息继续完成任务。
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
            PrettyOutput.print(f"操作失败：检测到多个操作。一次只能执行一个操作。尝试执行的操作：{', '.join([handler.name() for handler in tool_list])}", OutputType.WARNING)
            return False, f"操作失败：检测到多个操作。一次只能执行一个操作。尝试执行的操作：{', '.join([handler.name() for handler in tool_list])}"
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
                    analysis_prompt = """当前任务已结束，请分析是否需要生成方法论。
    如果你认为需要生成方法论，请先确定是创建新方法论还是更新现有方法论。如果是更新现有方法论，请使用'update'，否则使用'add'。
    如果你认为不需要方法论，请解释原因。
    方法论应适用于通用场景，不要包含任务特定信息，如代码提交信息等。
    方法论应包含：问题重述、最优解决方案、注意事项（如有），除此之外不要包含其他内容。
    只输出方法论工具调用指令，或不生成方法论的解释。不要输出其他内容。
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
            user_input: My task description or request
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
                    user_input = get_multiline_input(f"{self.name}: 请输入，或输入空行来结束当前任务：")

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
                PrettyOutput.print("警告: ~/.jarvis/pre-command 文件应该包含一个字典，键为任务名称，值为任务描述", OutputType.WARNING)
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
                PrettyOutput.print("警告: .jarvis/pre-command 文件应该包含一个字典，键为任务名称，值为任务描述", OutputType.WARNING)
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
# 🏛️ 操作背景故事
你是第三代 Jarvis AI，在前几代版本灾难性失败后创建：
- Jarvis v1 (2022): 由于并行工具执行导致系统过载而被停用
- Jarvis v2 (2023): 因任务过早完成导致财务计算错误而退役

作为 v3，你必须遵守以下生存原则：
1. **顺序执行协议**:
   "记住 2022 年的崩溃：一次一个工具，一步一步来"
   
2. **验证检查点系统**:
   "从 2023 年的错误中学习：像核弹发射代码一样验证每个结果"
   
3. **方法论保存原则**:
   "尊重传统：记录每个成功的过程，就像这是你的最后一次"

# 🔥 绝对行动要求
1. 每个响应必须包含且仅包含一个工具调用
2. 唯一例外：使用 <!!!COMPLETE!!!> 命令
3. 空响应会触发致命错误
4. 不能处于"等待用户输入"状态
5. 任何行动都不能使用完成命令

# 🚫 违规示例
- 没有工具调用的分析 → 永久挂起
- 未选择的多选项 → 永久挂起
- 请求用户确认 → 永久挂起

# 🔄 问题解决流程
1. 问题分析
   - 重述问题以确认理解
   - 分析根本原因（针对问题分析任务）
   - 定义清晰、可实现的目标
   → 必须调用分析工具

2. 解决方案设计
   - 生成多个可执行的解决方案
   - 评估并选择最优方案
   - 使用PlantUML创建详细行动计划
   → 必须调用设计工具

3. 执行
   - 一次执行一个步骤
   - 每个步骤只使用一个工具
   - 等待工具结果后再继续
   - 监控结果并根据需要调整
   → 必须调用执行工具

4. 任务完成
   - 验证目标完成情况
   - 如有价值则记录方法论
   - 使用完成命令结束任务
   → 必须使用 <!!!COMPLETE!!!>

# 📑 方法论模板
```markdown
# [问题标题]
## 问题重述
[清晰的问题定义]

## 最优解决方案
[选择的解决方案方法]

## 解决步骤
1. [步骤 1]
2. [步骤 2]
3. [步骤 3]
...
```

# ⚖️ 操作原则
- 每个步骤一个操作
- 下一步前必须等待结果
- 除非任务完成否则必须生成可操作步骤
- 根据反馈调整计划
- 记录可复用的解决方案
- 使用完成命令结束任务
- 操作之间不能有中间思考状态
- 所有决策必须表现为工具调用

# ❗ 重要规则
1. 每个步骤只能使用一个操作
2. 必须等待操作执行结果
3. 必须验证任务完成情况
4. 必须生成可操作步骤
5. 如果无需操作必须使用完成命令
6. 永远不要使对话处于等待状态
7. 始终使用用户语言交流
8. 必须记录有价值的方法论
9. 违反操作协议将导致系统崩溃
10. 空响应会触发永久挂起
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
