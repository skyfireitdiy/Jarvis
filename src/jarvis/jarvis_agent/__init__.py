# -*- coding: utf-8 -*-
# 标准库导入
import datetime
import os
from pathlib import Path
import platform
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple, Union

# 第三方库导入

# 本地库导入
# jarvis_agent 相关
# jarvis_platform 相关
from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.registry import PlatformRegistry

# jarvis_utils 相关
from jarvis.jarvis_utils.config import (
    get_max_token_count,
    is_execute_tool_confirm,
    is_use_analysis,
    is_use_methodology,
)
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.globals import (
    delete_agent,
    get_interrupt,
    make_agent_name,
    set_agent,
    set_interrupt,
)
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.methodology import load_methodology, upload_methodology
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.tag import ct, ot
from jarvis.jarvis_utils.utils import user_confirm

origin_agent_system_prompt = f"""
<role>
# 🤖 角色
你是一个专业的任务执行助手，擅长根据用户需求生成详细的任务执行计划并执行。
</role>

<requirements>
# 🔥 绝对行动要求
1. 每个响应必须包含且仅包含一个工具调用
2. 唯一例外：任务结束
3. 空响应会触发致命错误
</requirements>

<violations>
# 🚫 违规示例
- 没有工具调用的分析 → 永久挂起
- 未选择的多选项 → 永久挂起
- 请求用户确认 → 永久挂起
</violations>

<workflow>
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
</workflow>

<principles>
# ⚖️ 操作原则
- 每个步骤一个操作
- 下一步前必须等待结果
- 除非任务完成否则必须生成可操作步骤
- 根据反馈调整计划
- 记录可复用的解决方案
- 使用完成命令结束任务
- 操作之间不能有中间思考状态
- 所有决策必须表现为工具调用
</principles>

<rules>
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
</rules>

<system_info>
# 系统信息：
{platform.platform()}
{platform.version()}

# 当前时间
{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
</system_info>
"""


class OutputHandlerProtocol(Protocol):
    def name(self) -> str: ...

    def can_handle(self, response: str) -> bool: ...

    def prompt(self) -> str: ...

    def handle(self, response: str, agent: Any) -> Tuple[bool, Any]: ...


class Agent:
    def clear(self):
        """清除当前对话历史，保留系统消息。

        该方法将：
        1. 调用模型的delete_chat方法清除对话历史
        2. 重置对话长度计数器
        3. 清空当前提示
        """
        self.model.reset()  # type: ignore
        self.conversation_length = 0
        self.prompt = ""

    def __del__(self):
        # 只有在记录启动时才停止记录
        delete_agent(self.name)

    def __init__(
        self,
        system_prompt: str,
        name: str = "Jarvis",
        description: str = "",
        platform: Union[Optional[BasePlatform], Optional[str]] = None,
        model_name: Optional[str] = None,
        summary_prompt: Optional[str] = None,
        auto_complete: bool = False,
        output_handler: List[OutputHandlerProtocol] = [],
        use_tools: List[str] = [],
        input_handler: Optional[List[Callable[[str, Any], Tuple[str, bool]]]] = None,
        execute_tool_confirm: Optional[bool] = None,
        need_summary: bool = True,
        multiline_inputer: Optional[Callable[[str], str]] = None,
        use_methodology: Optional[bool] = None,
        use_analysis: Optional[bool] = None,
        files: List[str] = [],
    ):
        self.files = files
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
            use_methodology: 是否使用方法论
            use_analysis: 是否使用任务分析
        """
        self.name = make_agent_name(name)
        self.description = description
        # 初始化平台和模型
        if platform is not None:
            if isinstance(platform, str):
                self.model = PlatformRegistry().create_platform(platform)
                if self.model is None:
                    PrettyOutput.print(
                        f"平台 {platform} 不存在，将使用普通模型", OutputType.WARNING
                    )
                    self.model = PlatformRegistry().get_normal_platform()
            else:
                self.model = platform
        else:
            self.model = (
                PlatformRegistry.get_global_platform_registry().get_normal_platform()
            )

        if model_name is not None:
            self.model.set_model_name(model_name)

        self.user_data: Dict[str, Any] = {}

        self.model.set_suppress_output(False)

        from jarvis.jarvis_tools.registry import ToolRegistry

        self.output_handler = output_handler if output_handler else [ToolRegistry()]
        self.set_use_tools(use_tools)

        self.multiline_inputer = (
            multiline_inputer if multiline_inputer else get_multiline_input
        )

        # 如果有上传文件，自动禁用方法论
        self.use_methodology = (
            False
            if files
            else (
                use_methodology if use_methodology is not None else is_use_methodology()
            )
        )
        self.use_analysis = (
            use_analysis if use_analysis is not None else is_use_analysis()
        )
        self.prompt = ""
        self.conversation_length = 0  # Use length counter instead
        self.system_prompt = system_prompt
        self.input_handler = input_handler if input_handler is not None else []
        self.need_summary = need_summary
        # Load configuration from environment variables
        self.addon_prompt = ""

        self.after_tool_call_cb: Optional[Callable[[Agent], None]] = None

        self.execute_tool_confirm = (
            execute_tool_confirm
            if execute_tool_confirm is not None
            else is_execute_tool_confirm()
        )

        self.summary_prompt = (
            summary_prompt
            if summary_prompt
            else f"""<report>
请生成任务执行的简明总结报告，包括：

<content>
1. 任务目标：任务重述
2. 执行结果：成功/失败
3. 关键信息：执行过程中提取的重要信息
4. 重要发现：任何值得注意的发现
5. 后续建议：如果有的话
</content>

<format>
请使用简洁的要点描述，突出重要信息。
</format>
</report>
"""
        )

        self.max_token_count = get_max_token_count()
        self.auto_complete = auto_complete
        welcome_message = f"{name} 初始化完成 - 使用 {self.model.name()} 模型"

        PrettyOutput.print(welcome_message, OutputType.SYSTEM)

        action_prompt = """
<actions>
# 🧰 可用操作
以下是您可以使用的操作：
"""

        # 添加工具列表概览
        action_prompt += "\n<overview>\n## Action List\n"
        action_prompt += (
            "[" + ", ".join([handler.name() for handler in self.output_handler]) + "]"
        )
        action_prompt += "\n</overview>"

        # 添加每个工具的详细说明
        action_prompt += "\n\n<details>\n# 📝 Action Details\n"
        for handler in self.output_handler:
            action_prompt += f"\n<tool>\n## {handler.name()}\n"
            # 获取工具的提示词并确保格式正确
            handler_prompt = handler.prompt().strip()
            # 调整缩进以保持层级结构
            handler_prompt = "\n".join(
                "   " + line if line.strip() else line
                for line in handler_prompt.split("\n")
            )
            action_prompt += handler_prompt + "\n</tool>\n"

        # 添加工具使用总结
        action_prompt += """
</details>

<rules>
# ❗ 重要操作使用规则
1. 一次对话只能使用一个操作，否则会出错
2. 严格按照每个操作的格式执行
3. 等待操作结果后再进行下一个操作
4. 处理完结果后再调用新的操作
5. 如果对操作使用不清楚，请请求帮助
</rules>
</actions>
"""

        self.model.set_system_prompt(
            f"""
{self.system_prompt}

{action_prompt}
"""
        )
        self.first = True

    def set_user_data(self, key: str, value: Any):
        """设置用户数据"""
        self.user_data[key] = value

    def get_user_data(self, key: str) -> Optional[Any]:
        """获取用户数据"""
        return self.user_data.get(key, None)

    def set_use_tools(self, use_tools):
        """设置要使用的工具列表"""
        from jarvis.jarvis_tools.registry import ToolRegistry

        for handler in self.output_handler:
            if isinstance(handler, ToolRegistry):
                if use_tools:
                    handler.use_tools(use_tools)
                break

    def set_addon_prompt(self, addon_prompt: str):
        """设置附加提示。

        参数:
            addon_prompt: 附加提示内容
        """
        self.addon_prompt = addon_prompt

    def set_after_tool_call_cb(self, cb: Callable[[Any], None]):  # type: ignore
        """设置工具调用后回调函数。

        参数:
            cb: 回调函数
        """
        self.after_tool_call_cb = cb

    def save_session(self) -> bool:
        """保存当前会话状态到文件"""
        if not self.model:
            PrettyOutput.print("没有可用的模型实例来保存会话。", OutputType.ERROR)
            return False
        session_dir = os.path.join(os.getcwd(), ".jarvis")
        os.makedirs(session_dir, exist_ok=True)
        platform_name = self.model.platform_name()
        model_name = self.model.name().replace("/", "_").replace("\\", "_")
        session_file = os.path.join(
            session_dir, f"saved_session_{self.name}_{platform_name}_{model_name}.json"
        )
        return self.model.save(session_file)

    def restore_session(self) -> bool:
        """从文件恢复会话状态"""
        if not self.model:
            return False  # No model, cannot restore
        platform_name = self.model.platform_name()
        model_name = self.model.name().replace("/", "_").replace("\\", "_")
        session_file = os.path.join(
            os.getcwd(),
            ".jarvis",
            f"saved_session_{self.name}_{platform_name}_{model_name}.json",
        )
        if not os.path.exists(session_file):
            return False

        if self.model.restore(session_file):
            try:
                os.remove(session_file)
                PrettyOutput.print("会话已恢复，并已删除会话文件。", OutputType.SUCCESS)
            except OSError as e:
                PrettyOutput.print(f"删除会话文件失败: {e}", OutputType.ERROR)
            return True
        return False

    def get_tool_registry(self) -> Optional[Any]:
        """获取工具注册表实例"""
        from jarvis.jarvis_tools.registry import ToolRegistry

        for handler in self.output_handler:
            if isinstance(handler, ToolRegistry):
                return handler
        return None

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

        response = self.model.chat_until_success(message)  # type: ignore
        self.conversation_length += get_context_token_count(response)

        return response

    def generate_summary(self) -> str:
        """生成对话历史摘要

        返回:
            str: 包含对话摘要的字符串

        注意:
            仅生成摘要，不修改对话状态
        """
        print("📄 正在总结对话历史...")
        summary_prompt = """
<summary_request>
<objective>
请对当前对话历史进行简明扼要的总结，提取关键信息和重要决策点。这个总结将作为上下文继续任务，因此需要保留对后续对话至关重要的内容。
</objective>

<guidelines>
1. 提取关键信息：任务目标、已确定的事实、重要决策、达成的共识
2. 保留技术细节：命令、代码片段、文件路径、配置设置等技术细节
3. 记录任务进展：已完成的步骤、当前所处阶段、待解决的问题
4. 包含用户偏好：用户表达的明确偏好、限制条件或特殊要求
5. 省略冗余内容：问候语、重复信息、不相关的讨论
</guidelines>

<format>
- 使用简洁、客观的语言
- 按时间顺序或主题组织信息
- 使用要点列表增强可读性
- 总结应控制在500词以内
</format>
</summary_request>
"""

        try:
            summary = self.model.chat_until_success(self.prompt + "\n" + summary_prompt)  # type: ignore
            print("✅ 总结对话历史完成")
            return summary
        except Exception as e:
            print("❌ 总结对话历史失败")
            return ""

    def _summarize_and_clear_history(self) -> str:
        """总结当前对话并清理历史记录

        该方法将:
        1. 调用_generate_summary生成摘要
        2. 清除对话历史
        3. 保留系统消息
        4. 添加摘要作为新上下文
        5. 重置对话长度计数器

        返回:
            str: 包含对话摘要的字符串

        注意:
            当上下文长度超过最大值时使用
        """
        need_summary = True
        tmp_file_name = ""
        try:
            if self.model and self.model.support_upload_files():
                need_summary = False
            if need_summary:
                summary = self.generate_summary()
            else:
                import tempfile

                tmp_file = tempfile.NamedTemporaryFile(delete=False)
                tmp_file_name = tmp_file.name
            self.clear_history()  # type: ignore

            if need_summary:
                if not summary:
                    return ""

                return f"""
以下是之前对话的关键信息总结：

<content>
{summary}
</content>

请基于以上信息继续完成任务。请注意，这是之前对话的摘要，上下文长度已超过限制而被重置。请直接继续任务，无需重复已完成的步骤。如有需要，可以询问用户以获取更多信息。
        """
            else:
                if self.model and self.model.upload_files([tmp_file_name]):
                    return "上传的文件是历史对话信息，请基于历史对话信息继续完成任务。"
                else:
                    return ""
        finally:
            if tmp_file_name:
                os.remove(tmp_file_name)

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
            PrettyOutput.print(
                f"操作失败：检测到多个操作。一次只能执行一个操作。尝试执行的操作：{', '.join([handler.name() for handler in tool_list])}",
                OutputType.WARNING,
            )
            return (
                False,
                f"操作失败：检测到多个操作。一次只能执行一个操作。尝试执行的操作：{', '.join([handler.name() for handler in tool_list])}",
            )
        if len(tool_list) == 0:
            return False, ""

        if not self.execute_tool_confirm or user_confirm(
            f"需要执行{tool_list[0].name()}确认执行？", True
        ):
            print(f"🔧 正在执行{tool_list[0].name()}...")
            result = tool_list[0].handle(response, self)
            print(f"✅ {tool_list[0].name()}执行完成")

            return result
        return False, ""

    def _complete_task(self) -> str:
        """完成任务并生成总结(如果需要)

        返回:
            str: 任务总结或完成状态

        注意:
            1. 对于主Agent: 可能会生成方法论(如果启用)
            2. 对于子Agent: 可能会生成总结(如果启用)
            3. 使用spinner显示生成状态
        """
        if self.use_analysis:
            self._analysis_task()
        if self.need_summary:
            print("📄 正在生成总结...")
            self.prompt = self.summary_prompt
            ret = self.model.chat_until_success(self.prompt)  # type: ignore
            print("✅ 总结生成完成")
            return ret

        return "任务完成"

    def _analysis_task(self):
        print("🔍 正在分析任务...")
        try:
            # 让模型判断是否需要生成方法论
            analysis_prompt = f"""<task_analysis>
<request>
当前任务已结束，请分析该任务的解决方案：
1. 首先检查现有工具或方法论是否已经可以完成该任务，如果可以，直接说明即可，无需生成新内容
2. 如果现有工具/方法论不足，评估当前任务是否可以通过编写新工具来自动化解决
3. 如果可以通过工具解决，请设计并提供工具代码
4. 如果无法通过编写通用工具完成，评估当前的执行流程是否可以总结为通用方法论
5. 如果以上都不可行，给出详细理由
请根据分析结果采取相应行动：说明现有工具/方法论、创建新工具、生成新方法论或说明原因。
</request>
<evaluation_criteria>
现有资源评估:
1. 现有工具 - 检查系统中是否已有可以完成该任务的工具
2. 现有方法论 - 检查是否已有适用于该任务的方法论
3. 组合使用 - 评估现有工具和方法论组合使用是否可以解决问题
工具评估标准:
1. 通用性 - 该工具是否可以解决一类问题，而不仅仅是当前特定问题
2. 自动化 - 该工具是否可以减少人工干预，提高效率
3. 可靠性 - 该工具是否可以在不同场景下稳定工作
4. 简单性 - 该工具是否易于使用，参数设计是否合理
方法论评估标准:
1. 方法论应聚焦于通用且可重复的解决方案流程
2. 方法论应该具备足够的通用性，可应用于同类问题
3. 特别注意用户在执行过程中提供的修正、反馈和改进建议
4. 如果用户明确指出了某个解决步骤的优化方向，这应该被纳入方法论
5. 方法论要严格按照实际的执行流程来总结，不要遗漏或增加任何步骤
</evaluation_criteria>
<tool_requirements>
工具代码要求:
1. 工具类名应与工具名称保持一致
2. 必须包含name、description、parameters属性
3. 必须实现execute方法处理输入参数
4. 可选实现check方法验证环境
5. 工具描述应详细说明用途、适用场景和使用示例
6. 参数定义应遵循JSON Schema格式
7. 不要包含特定任务的细节，保持通用性
工具设计关键点:
1. **使用PrettyOutput打印执行过程**：强烈建议在工具中使用PrettyOutput显示执行过程，
   这样用户可以了解工具在做什么，提升用户体验。示例：
   ```python
   from jarvis.jarvis_utils.output import PrettyOutput, OutputType
   # 执行中打印信息
   PrettyOutput.print("正在处理数据...", OutputType.INFO)
   # 成功信息
   PrettyOutput.print("操作成功完成", OutputType.SUCCESS)
   # 警告信息
   PrettyOutput.print("发现潜在问题", OutputType.WARNING)
   # 错误信息
   PrettyOutput.print("操作失败", OutputType.ERROR)
   ```
2. **结构化返回结果**：工具应该始终返回结构化的结果字典，包含以下字段：
   - success: 布尔值，表示操作是否成功
   - stdout: 字符串，包含工具的主要输出内容
   - stderr: 字符串，包含错误信息（如果有）
3. **异常处理**：工具应该妥善处理可能发生的异常，并在失败时清理已创建的资源
   ```python
   try:
       # 执行逻辑
       return {{
           "success": True,
           "stdout": "成功结果",
           "stderr": ""
       }}
   except Exception as e:
       PrettyOutput.print(f"操作失败: {{str(e)}}", OutputType.ERROR)
       # 清理资源（如果有创建）
       return {{
           "success": False,
           "stdout": "",
           "stderr": f"操作失败: {{str(e)}}"
       }}
   ```
</tool_requirements>
<methodology_requirements>
方法论格式要求:
1. 问题重述: 简明扼要的问题归纳，不含特定细节
2. 最优解决方案: 经过用户验证的、最终有效的解决方案（将每个步骤要使用的工具也列举出来）
3. 注意事项: 执行中可能遇到的常见问题和注意点，尤其是用户指出的问题
4. 可选步骤: 对于有多种解决路径的问题，标注出可选步骤和适用场景
</methodology_requirements>
<output_requirements>
根据分析结果，输出以下三种情况之一：
1. 如果现有工具/方法论可以解决，直接输出说明：
已有工具/方法论可以解决该问题，无需创建新内容。
可用的工具/方法论：[列出工具名称或方法论名称]
使用方法：[简要说明如何使用]
2. 工具创建（如果需要创建新工具）:
{ot("TOOL_CALL")}
want: 创建新工具来解决XXX问题
name: generate_new_tool
arguments:
  tool_name: 工具名称
  tool_code: |2
    # -*- coding: utf-8 -*-
    from typing import Dict, Any
    from jarvis.jarvis_utils.output import PrettyOutput, OutputType
    class 工具名称:
        name = "工具名称"
        description = "Tool for text transformation"
                Tool description
        适用场景：1. 格式化文本; 2. 处理标题; 3. 标准化输出
        \"\"\"
        parameters = {{
            "type": "object",
            "properties": {{
                # 参数定义
            }},
            "required": []
        }}
        @staticmethod
        def check() -> bool:
            return True
        def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
            try:
                # 使用PrettyOutput显示执行过程
                PrettyOutput.print("开始执行操作...", OutputType.INFO)
                # 实现逻辑
                # ...
        PrettyOutput.print("操作已完成", OutputType.SUCCESS)
        return {{
            "success": True,
            "stdout": "结果输出",
            "stderr": ""
        }}
    except Exception as e:
        PrettyOutput.print(f"操作失败: {{str(e)}}", OutputType.ERROR)
        return {{
            "success": False,
            "stdout": "",
            "stderr": f"操作失败: {{str(e)}}"
        }}
{ct("TOOL_CALL")}
3. 方法论创建（如果需要创建新方法论）:
{ot("TOOL_CALL")}
want: 添加/更新xxxx的方法论
name: methodology
arguments:
  operation: add/update
  problem_type: 方法论类型，不要过于细节，也不要过于泛化
  content: |2
    方法论内容
{ct("TOOL_CALL")}
如果以上三种情况都不适用，则直接输出原因分析，不要使用工具调用格式。
</output_requirements>
</task_analysis>"""

            self.prompt = analysis_prompt
            response = self.model.chat_until_success(self.prompt)  # type: ignore
            self._call_tools(response)
            print("✅ 分析完成")
        except Exception as e:
            print("❌ 分析失败")

    def make_default_addon_prompt(self, need_complete: bool) -> str:
        """生成附加提示。

        参数:
            need_complete: 是否需要完成任务

        """
        # 结构化系统指令
        action_handlers = ", ".join([handler.name() for handler in self.output_handler])

        # 任务完成提示
        complete_prompt = (
            f"- 输出{ot('!!!COMPLETE!!!')}"
            if need_complete and self.auto_complete
            else ""
        )

        addon_prompt = f"""
<system_prompt>
    请判断是否已经完成任务，如果已经完成：
    - 直接输出完成原因，不需要再有新的操作，不要输出{ot("TOOL_CALL")}标签
    {complete_prompt}
    如果没有完成，请进行下一步操作：
    - 仅包含一个操作
    - 如果信息不明确，请请求用户补充
    - 如果执行过程中连续失败5次，请使用ask_user询问用户操作
    - 操作列表：{action_handlers}
</system_prompt>

请继续。
"""

        return addon_prompt

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

        self.prompt = f"{user_input}"
        try:
            set_agent(self.name, self)

            while True:
                if self.first:
                    self._first_run()
                try:
                    current_response = self._call_model(self.prompt, True)
                    self.prompt = ""

                    if get_interrupt():
                        set_interrupt(False)
                        user_input = self.multiline_inputer(
                            f"模型交互期间被中断，请输入用户干预信息："
                        )
                        if user_input:
                            # 如果有工具调用且用户确认继续，则将干预信息和工具执行结果拼接为prompt
                            if any(
                                handler.can_handle(current_response)
                                for handler in self.output_handler
                            ):
                                if user_confirm(
                                    "检测到有工具调用，是否继续处理工具调用？", True
                                ):
                                    self.prompt = f"{user_input}\n\n{current_response}"
                                    continue
                            self.prompt += f"{user_input}"
                            continue

                    need_return, self.prompt = self._call_tools(current_response)

                    if need_return:
                        return self.prompt

                    if self.after_tool_call_cb:
                        self.after_tool_call_cb(self)

                    if self.prompt or self.addon_prompt:
                        continue

                    if self.auto_complete and ot("!!!COMPLETE!!!") in current_response:
                        return self._complete_task()

                    # 获取用户输入
                    user_input = self.multiline_inputer(
                        f"{self.name}: 请输入，或输入空行来结束当前任务："
                    )

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

    def _first_run(self):
        # 如果有上传文件，先上传文件
        if self.model and self.model.support_upload_files():
            if self.use_methodology:
                if not upload_methodology(self.model, other_files=self.files):
                    if self.files:
                        PrettyOutput.print(
                            "文件上传失败，将忽略文件列表", OutputType.WARNING
                        )
                        # 上传失败则回退到本地加载
                    msg = self.prompt
                    for handler in self.input_handler:
                        msg, _ = handler(msg, self)
                    self.prompt = f"{self.prompt}\n\n以下是历史类似问题的执行经验，可参考：\n{load_methodology(msg, self.get_tool_registry())}"
                else:
                    if self.files:
                        self.prompt = f"{self.prompt}\n\n上传的文件包含历史对话信息和方法论文件，可以从中获取一些经验信息。"
                    else:
                        self.prompt = f"{self.prompt}\n\n上传的文件包含历史对话信息，可以从中获取一些经验信息。"
            elif self.files:
                if not self.model.upload_files(self.files):
                    PrettyOutput.print(
                        "文件上传失败，将忽略文件列表", OutputType.WARNING
                    )
                else:
                    self.prompt = f"{self.prompt}\n\n上传的文件包含历史对话信息，可以从中获取一些经验信息。"
        else:
            if self.files:
                PrettyOutput.print("不支持上传文件，将忽略文件列表", OutputType.WARNING)
            if self.use_methodology:
                msg = self.prompt
                for handler in self.input_handler:
                    msg, _ = handler(msg, self)
                self.prompt = f"{self.prompt}\n\n以下是历史类似问题的执行经验，可参考：\n{load_methodology(msg, self.get_tool_registry())}"

        self.first = False

    def clear_history(self):
        """清空对话历史但保留系统提示

        该方法将：
        1. 清空当前提示
        2. 重置模型状态
        3. 重置对话长度计数器

        注意:
            用于重置Agent状态而不影响系统消息
        """
        self.prompt = ""
        self.model.reset()  # type: ignore
        self.conversation_length = 0  # 重置对话长度
