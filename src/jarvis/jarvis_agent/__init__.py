import datetime
import platform
from typing import Any, Callable, List, Optional, Tuple, Union

from yaspin import yaspin

from jarvis.jarvis_agent.output_handler import OutputHandler
from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.output import PrettyOutput, OutputType
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.config import get_max_tool_call_count, is_auto_complete, is_execute_tool_confirm
from jarvis.jarvis_utils.methodology import load_methodology
from jarvis.jarvis_utils.globals import make_agent_name, set_agent, delete_agent
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.config import get_max_token_count
from jarvis.jarvis_utils.utils import ct, ot
from jarvis.jarvis_utils.utils import user_confirm

from jarvis.jarvis_platform.registry import PlatformRegistry


origin_agent_system_prompt = f"""
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
2. 唯一例外：任务结束
3. 空响应会触发致命错误

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

# 系统信息：
{platform.platform()}
{platform.version()}

# 当前时间
{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""


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
        self.model.reset() # type: ignore
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
                 execute_tool_confirm: Optional[bool] = None,
                 need_summary: bool = True,
                 multiline_inputer: Optional[Callable[[str], str]] = None):
        """初始化Jarvis Agent实例

        参数:
            system_prompt: 系统提示词，定义Agent的行为准则
            name: Agent名称，默认为"Jarvis"
            description: Agent描述信息
            platform: 平台实例或平台名称字符串
            model_name: 使用的模型名称
            summary_prompt: 任务总结提示模板
            auto_complete: 是否自动完成任务
            output_handler: 输出处理器列表
            input_handler: 输入处理器列表
            max_context_length: 最大上下文长度
            execute_tool_confirm: 执行工具前是否需要确认
            need_summary: 是否需要生成总结
            multiline_inputer: 多行输入处理器
        """
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
        self.need_summary = need_summary
        # Load configuration from environment variables
        self.addon_prompt = ""

        self.tool_call_count = 0
        self.max_tool_call_count = get_max_tool_call_count()


        self.execute_tool_confirm = execute_tool_confirm if execute_tool_confirm is not None else is_execute_tool_confirm()

        self.summary_prompt = summary_prompt if summary_prompt else f"""请生成任务执行的简明总结报告，包括：

1. 任务目标：任务重述
2. 执行结果：成功/失败
3. 关键信息：执行过程中提取的重要信息
4. 重要发现：任何值得注意的发现
5. 后续建议：如果有的话

请使用简洁的要点描述，突出重要信息。
"""

        self.max_token_count =  get_max_token_count()
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


    def set_addon_prompt(self, addon_prompt: str):
        """设置附加提示。

        参数:
            addon_prompt: 附加提示内容
        """
        self.addon_prompt = addon_prompt

    def make_default_addon_prompt(self, need_complete: bool) -> str:
        """生成附加提示。

        参数:
            need_complete: 是否需要完成任务

        """
        # 结构化系统指令
        action_handlers = '\n'.join([f'- {handler.name()}' for handler in self.output_handler])

        addon_prompt = f"""

**系统指令：**
- 每次响应必须且只能包含一个操作
- 严格遵循操作调用格式
- 必须包含参数和说明
- 操作结束需等待结果
- 如果判断任务已经完成，不必输出操作
- 如果信息不明确，请请求用户补充
- 如果执行过程中连续失败5次，请使用ask_user询问用户操作

**可用操作列表：**
{action_handlers}
"""

        # 任务完成提示
        complete_prompt = f"并输出{ot('!!!COMPLETE!!!')}" if need_complete and self.auto_complete else ""
        addon_prompt += f"\n\n如果任务已完成{complete_prompt}，请：\n1. 说明完成原因\n2. 保持输出格式规范"

        return addon_prompt

    def _call_model(self, message: str, need_complete: bool = False) -> str:
        """调用AI模型并实现重试逻辑

        参数:
            message: 输入给模型的消息
            need_complete: 是否需要完成任务标记

        返回:
            str: 模型的响应

        注意:
            1. 将使用指数退避重试，最多重试30秒
            2. 会自动处理输入处理器链
            3. 会自动添加附加提示
            4. 会检查并处理上下文长度限制
        """
        for handler in self.input_handler:
            message, need_return = handler(message, self)
            if need_return:
                return message

        if self.addon_prompt:
            message += f"\n\n{self.addon_prompt}"
            self.addon_prompt = ""
        else:
            message += f"\n\n{self.make_default_addon_prompt(need_complete)}"

        # 累加对话长度
        self.conversation_length += get_context_token_count(message)

        if self.conversation_length > self.max_token_count:
            message = self._summarize_and_clear_history() + "\n\n" + message
            self.conversation_length += get_context_token_count(message)

        print("🤖 模型思考：")
        return self.model.chat_until_success(message)   # type: ignore


    def _summarize_and_clear_history(self) -> str:
        """总结当前对话并清理历史记录

        该方法将:
        1. 生成关键信息摘要
        2. 清除对话历史
        3. 保留系统消息
        4. 添加摘要作为新上下文
        5. 重置对话长度计数器

        返回:
            str: 包含对话摘要的字符串

        注意:
            当上下文长度超过最大值时使用
        """
        # Create a new model instance to summarize, avoid affecting the main conversation

        with yaspin(text="正在总结对话历史...", color="cyan") as spinner:

            prompt = """请详细总结之前对话中的关键信息，生成一个全面而精确的对话摘要，包括以下方面：

1. 任务目标与需求:
   - 用户最初提出的核心问题或任务
   - 任务的预期结果和成功标准
   - 用户明确强调的任何特殊要求或限制条件

2. 背景与上下文信息:
   - 问题的业务或技术背景
   - 相关系统、平台或环境的信息
   - 已知的约束条件或依赖关系

3. 已获取的关键信息:
   - 用户确认的重要事实
   - 收集到的相关数据或状态
   - 已验证的系统参数或配置

4. 问题分析与诊断:
   - 已识别的根本原因(针对问题诊断任务)
   - 关键的技术细节或错误信息
   - 排除的可能性和已验证的假设

5. 解决方案进展:
   - 已尝试的方法及其结果
   - 成功实施的步骤
   - 失败的尝试及原因
   - 用户对解决方案的反馈

6. 当前状态:
   - 任务完成的程度
   - 当前遇到的障碍或挑战
   - 下一步需要解决的问题

7. 决策记录:
   - 做出的关键决策及其理由
   - 用户表达的偏好
   - 关键的选择点及选择依据

请以结构化方式组织信息，使用明确的段落和要点，确保新的对话能无缝继续。摘要应该足够详细，以便于在没有完整历史记录的情况下理解任务全貌和当前进展。

注意：保留专业术语和技术细节，但不要包含无关的对话内容或冗长的代码片段。
"""

            try:
                with spinner.hidden():
                    summary = self.model.chat_until_success(self.prompt + "\n" + prompt) # type: ignore

                self.model.reset() # type: ignore

                # 清空当前对话历史，但保留系统消息
                self.conversation_length = 0  # Reset conversation length

                # 添加总结作为新的上下文
                spinner.text = "总结对话历史完成"
                spinner.ok("✅")
                return  f"""以下是之前对话的关键信息总结：

{summary}

请基于以上信息继续完成任务。请注意，这是之前对话的摘要，上下文长度已超过限制而被重置。请直接继续任务，无需重复已完成的步骤。如有需要，可以询问用户以获取更多信息。
"""
            except Exception as e:
                spinner.text = "总结对话历史失败"
                spinner.fail("❌")
                return ""

    def _call_tools(self, response: str) -> Tuple[bool, Any]:
        """调用工具执行响应

        参数:
            response: 包含工具调用信息的响应字符串

        返回:
            Tuple[bool, Any]:
                - 第一个元素表示是否需要返回结果
                - 第二个元素是返回结果或错误信息

        注意:
            1. 一次只能执行一个工具
            2. 如果配置了确认选项，会在执行前请求用户确认
            3. 使用spinner显示执行状态
        """
        tool_list = []
        for handler in self.output_handler:
            if handler.can_handle(response):
                tool_list.append(handler)
        if len(tool_list) > 1:
            PrettyOutput.print(f"操作失败：检测到多个操作。一次只能执行一个操作。尝试执行的操作：{', '.join([handler.name() for handler in tool_list])}", OutputType.WARNING)
            return False, f"操作失败：检测到多个操作。一次只能执行一个操作。尝试执行的操作：{', '.join([handler.name() for handler in tool_list])}"
        if len(tool_list) == 0:
            return False, ""
        if self.tool_call_count >= self.max_tool_call_count:
            if user_confirm(f"工具调用次数超过限制，是否继续执行？", True):
                self.reset_tool_call_count()
            else:
                return False, ""
        if not self.execute_tool_confirm or user_confirm(f"需要执行{tool_list[0].name()}确认执行？", True):
            with yaspin(text=f"正在执行{tool_list[0].name()}...", color="cyan") as spinner:
                with spinner.hidden():
                    result = tool_list[0].handle(response, self)
                spinner.text = f"{tool_list[0].name()}执行完成"
                spinner.ok("✅")
                self.tool_call_count += 1
                return result
        return False, ""
    
    def reset_tool_call_count(self):
        self.tool_call_count = 0


    def _complete_task(self) -> str:
        """完成任务并生成总结(如果需要)

        返回:
            str: 任务总结或完成状态

        注意:
            1. 对于主Agent: 可能会生成方法论(如果启用)
            2. 对于子Agent: 可能会生成总结(如果启用)
            3. 使用spinner显示生成状态
        """
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
                analysis_prompt = f"""当前任务已结束，请分析是否需要生成方法论。

如果你认为需要生成方法论，请先确定是创建新方法论还是更新现有方法论。如果是更新现有方法论，请使用'update'，否则使用'add'。
如果你认为不需要方法论，请解释原因。

方法论评估标准:
1. 方法论应聚焦于通用且可重复的解决方案流程
2. 方法论应该具备足够的通用性，可应用于同类问题
3. 特别注意用户在执行过程中提供的修正、反馈和改进建议
4. 如果用户明确指出了某个解决步骤的优化方向，这应该被纳入方法论
5. 如果用户在解决过程中发现了更高效的方法，这应被记录并优先使用

方法论格式要求:
1. 问题重述: 简明扼要的问题归纳，不含特定细节
2. 最优解决方案: 经过用户验证的、最终有效的解决方案（将每个步骤要使用的工具也列举出来）
3. 注意事项: 执行中可能遇到的常见问题和注意点，尤其是用户指出的问题
4. 可选步骤: 对于有多种解决路径的问题，标注出可选步骤和适用场景

方法论质量控制:
1. 只记录有实际意义的流程，不记录执行过程中的错误或无效尝试
2. 保留最终有效的解决步骤和用户认可的解决方案
3. 不要包含特定代码片段、文件路径或其他特定于单一任务的细节
4. 确保方法论遵循用户认可的执行路径，尤其是用户指出的改进点

只输出方法论工具调用指令，或不生成方法论的解释。不要输出其他内容。

方法论格式：
{ot("TOOL_CALL")}
want: 添加/更新xxxx的方法论
name: methodology
arguments:
  operation: add/update
  problem_type: 方法论类型，例如：code_review, bug_fix 等
  content: |
    方法论内容
{ct("TOOL_CALL")}
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
        if self.need_summary:
            with yaspin(text="正在生成总结...", color="cyan") as spinner:
                self.prompt = self.summary_prompt
                with spinner.hidden():
                    ret = self.model.chat_until_success(self.prompt) # type: ignore
                    spinner.text = "总结生成完成"
                    spinner.ok("✅")
                    return ret

        return "任务完成"


    def run(self, user_input: str) -> Any:
        """处理用户输入并执行任务

        参数:
            user_input: 任务描述或请求

        返回:
            str|Dict: 任务总结报告或要发送的消息

        注意:
            1. 这是Agent的主运行循环
            2. 处理完整的任务生命周期
            3. 包含错误处理和恢复逻辑
            4. 自动加载相关方法论(如果是首次运行)
        """
        try:
            set_agent(self.name, self)

            self.prompt = f"{user_input}"

            if self.first:
                self.prompt = f"{user_input}\n\n以下是历史类似问题的执行经验，可参考：\n{load_methodology(user_input)}"
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
                    
                    self.reset_tool_call_count()

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
        """清空对话历史但保留系统提示

        该方法将：
        1. 清空当前提示
        2. 重置模型状态
        3. 重置对话长度计数器

        注意:
            用于重置Agent状态而不影响系统消息
        """
        self.prompt = ""
        self.model.reset() # type: ignore
        self.conversation_length = 0  # 重置对话长度



