import argparse
from typing import Any, Callable, List, Optional, Tuple, Union

from prompt_toolkit import prompt
import yaml
from yaspin import yaspin
import platform
import datetime

from jarvis.jarvis_agent.output_handler import OutputHandler
from jarvis.jarvis_agent.builtin_input_handler import builtin_input_handler
from jarvis.jarvis_agent.file_input_handler import file_input_handler
from jarvis.jarvis_agent.patch import PatchOutputHandler
from jarvis.jarvis_agent.shell_input_handler import shell_input_handler
from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.output import PrettyOutput, OutputType
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.config import is_auto_complete, is_execute_tool_confirm
from jarvis.jarvis_utils.methodology import load_methodology
from jarvis.jarvis_utils.globals import make_agent_name, set_agent, delete_agent
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.config import get_max_token_count
from jarvis.jarvis_utils.utils import ot, init_env
from jarvis.jarvis_utils.utils import user_confirm
import os

from jarvis.jarvis_tools.registry import ToolRegistry  # 显式导入ToolRegistry
from jarvis.jarvis_platform.registry import PlatformRegistry
from .patch import PatchOutputHandler


__all__ = [
    'PlatformRegistry',
    'ToolRegistry',  # 新增缺失的导出项
    'PatchOutputHandler',
    'Agent',
    'file_input_handler',
    'shell_input_handler',
    'builtin_input_handler',
    '_load_tasks',
    '_select_task',
    'get_multiline_input',
    'origin_agent_system_prompt',
    'init_env',
    'PrettyOutput',
    'OutputType'
]

class Agent:

    def set_summary_prompt(self, summary_prompt: str):
        """设置任务完成时的总结提示模板。
        
        参数:
            summary_prompt: 用于生成任务总结的提示模板
        """
        self.summary_prompt = summary_prompt

    def clear(self):
        """清除当前对话历史，保留系统消息。
        
        该方法将：
        1. 调用模型的delete_chat方法清除对话历史
        2. 重置对话长度计数器
        3. 清空当前提示
        """
        self.model.delete_chat() # type: ignore
        self.conversation_length = 0
        self.prompt = ""
        
    def __del__(self):
        delete_agent(self.name)

        
    def __init__(self, 
                 system_prompt: str, 
                 name: str = "Jarvis", 
                 description: str = "",
                 platform: Union[Optional[BasePlatform], Optional[str]] = None, 
                 model_name: Optional[str] = None,
                 summary_prompt: Optional[str] = None, 
                 auto_complete: Optional[bool] = None, 
                 output_handler: List[OutputHandler] = [],
                 input_handler: Optional[List[Callable[[str, Any], Tuple[str, bool]]]] = None,
                 max_context_length: Optional[int] = None,
                 execute_tool_confirm: Optional[bool] = None,
                 multiline_inputer: Optional[Callable[[str], str]] = None):
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

        self.model.set_suppress_output(False)

        from jarvis.jarvis_tools.registry import ToolRegistry
        self.output_handler = output_handler if output_handler else [ToolRegistry()]
        self.multiline_inputer = multiline_inputer if multiline_inputer else get_multiline_input
        
        self.prompt = ""
        self.conversation_length = 0  # Use length counter instead
        self.system_prompt = system_prompt
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
1. 一次对话只能使用一个操作，否则会出错
2. 严格按照每个操作的格式执行
3. 等待操作结果后再进行下一个操作
4. 处理完结果后再调用新的操作
5. 如果对操作使用不清楚，请请求帮助
"""

        complete_prompt = ""
        if self.auto_complete:
            complete_prompt = f"""
            ## 任务完成
            当任务完成时，你应该打印以下信息：
            {ot("!!!COMPLETE!!!")}
            """

        self.model.set_system_message(f"""
{self.system_prompt}

{action_prompt}

{complete_prompt}
""")
        self.first = True


    
    def _call_model(self, message: str, need_complete: bool = False) -> str:
        """调用AI模型并实现重试逻辑。
        
        参数:
            message: 输入给模型的消息
            
        返回:
            str: 模型的响应
            
        注意:
            将使用指数退避重试，最多重试30秒
        """
        for handler in self.input_handler:
            message, need_return = handler(message, self)
            if need_return:
                return message
                
        # 添加输出简洁性指令
        actions = '、'.join([o.name() for o in self.output_handler])
        message += f"\n\n系统指令：请严格输出且仅输出一个操作的完整调用格式，不要输出多个操作；需要输出解释、分析和思考过程。确保输出格式正确且可直接执行。每次响应必须且只能包含一个操作。可用的操作：{actions}"
        if need_complete and self.auto_complete:
            message += f"\n\n如果任务已完成，说明完成原因，并输出{ot('!!!COMPLETE!!!')}"
        else:
            message += f"\n\n如果任务已完成，只需简洁地说明完成原因。"
        # 累加对话长度
        self.conversation_length += get_context_token_count(message)

        if self.conversation_length > self.max_token_count:
            message = self._summarize_and_clear_history() + "\n\n" + message
            self.conversation_length += get_context_token_count(message)
        
        print("🤖 模型思考：")
        return self.model.chat_until_success(message)   # type: ignore


    def _summarize_and_clear_history(self) -> str:
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

        with yaspin(text="正在总结对话历史...", color="cyan") as spinner:
            
            prompt = """请总结之前对话中的关键信息，包括：
    1. 当前任务目标
    2. 已确认的关键信息
    3. 已尝试的解决方案
    4. 当前进展
    5. 待解决的问题

    请用简洁的要点形式描述，突出重要信息。不要包含对话细节。
    """
            
            try:
                with spinner.hidden():
                    summary = self.model.chat_until_success(self.prompt + "\n" + prompt) # type: ignore

                self.model.delete_chat() # type: ignore
                
                # 清空当前对话历史，但保留系统消息
                self.conversation_length = 0  # Reset conversation length
                
                # 添加总结作为新的上下文
                spinner.text = "总结对话历史完成"
                spinner.ok("✅")
                return  f"""以下是之前对话的关键信息总结：

{summary}

请基于以上信息继续完成任务。
"""
            except Exception as e:
                spinner.text = "总结对话历史失败"
                spinner.fail("❌")
                return ""

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
            with yaspin(text=f"正在执行{tool_list[0].name()}...", color="cyan") as spinner:
                with spinner.hidden():
                    result = tool_list[0].handle(response)
                spinner.text = f"{tool_list[0].name()}执行完成"
                spinner.ok("✅")
                return result
        return False, ""
        

    def _complete_task(self) -> str:
        """Complete the current task and generate summary if needed.
        
        Returns:
            str: Task summary or completion status
            
        Note:
            - For main agent: May generate methodology if enabled
            - For sub-agent: May generate summary if enabled
        """
        with yaspin(text="正在生成方法论...", color="cyan") as spinner:
            try:
                
                # 让模型判断是否需要生成方法论
                analysis_prompt = """当前任务已结束，请分析是否需要生成方法论。
如果你认为需要生成方法论，请先确定是创建新方法论还是更新现有方法论。如果是更新现有方法论，请使用'update'，否则使用'add'。
如果你认为不需要方法论，请解释原因。
方法论应适用于通用场景，不要包含任务特定信息，如代码提交信息等。
方法论应包含：问题重述、最优解决方案、注意事项（如有），除此之外不要包含其他内容。
方法论中仅记录有实际意义的流程，不要记录执行过程中的错误或无效尝试，只保留最终有效的解决步骤。
确保方法论内容严格按照本次任务的成功执行路径编写，保证它对未来类似问题的解决具有指导意义。
只输出方法论工具调用指令，或不生成方法论的解释。不要输出其他内容。
"""
                self.prompt = analysis_prompt
                with spinner.hidden():
                    response = self.model.chat_until_success(self.prompt) # type: ignore

                with spinner.hidden():
                    self._call_tools(response)
                spinner.text = "方法论生成完成"
                spinner.ok("✅")
            except Exception as e:
                spinner.text = "方法论生成失败"
                spinner.fail("❌")
        
        with yaspin(text="正在生成总结...", color="cyan") as spinner:
            self.prompt = self.summary_prompt
            with spinner.hidden():
                ret = self.model.chat_until_success(self.prompt) # type: ignore
                spinner.text = "总结生成完成"
                spinner.ok("✅")
                return ret
        
        return "任务完成"


    def run(self, user_input: str) -> Any:
        """Process user input and execute the task.
        
        Args:
            user_input: My task description or request
            
        Returns:
            str|Dict: Task summary report or message to send
        """
        try:
            set_agent(self.name, self)
            
            self.prompt = f"{user_input}"

            if self.first:
                self.prompt = f"{user_input}\n\n{load_methodology(user_input)}"
                self.first = False

            while True:
                try:
                    # 如果对话历史长度超过限制，在提示中添加提醒

                    current_response = self._call_model(self.prompt, True)
                    self.prompt = ""
                    self.conversation_length += get_context_token_count(current_response)

                    need_return, self.prompt = self._call_tools(current_response)

                    if need_return:
                        return self.prompt
                    
                    if self.prompt:
                        continue

                    if self.auto_complete and ot("!!!COMPLETE!!!") in current_response:
                        return self._complete_task()
                    
                    # 获取用户输入
                    user_input = self.multiline_inputer(f"{self.name}: 请输入，或输入空行来结束当前任务：")

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
        """清空对话历史但保留系统提示。
        
        该方法将：
        1. 清空当前提示
        2. 重置模型状态
        3. 重置对话长度计数器
        """
        self.prompt = "" 
        self.model.reset() # type: ignore
        self.conversation_length = 0  # 重置对话长度



