# -*- coding: utf-8 -*-
"""
PromptManager: 统一管理 Agent 之系统提示词与附加提示词之构建逻辑。

设计目标（阶段一，最小变更）：
- 提供独立之提示构建类，不改现有行为
- 先行落地构建逻辑，后续在 Agent 中逐步委派使用
- 保持与现有工具/记忆系统兼容
"""

from typing import TYPE_CHECKING
from typing import Any

from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.tag import ot

if TYPE_CHECKING:
    # 避免运行时循环依赖，仅用于类型标注
    from . import Agent


class PromptManager:
    """
    提示管理器：负责构建系统提示与默认附加提示。
    注意：此类不直接访问模型，只负责拼装字符串。
    """

    def __init__(self, agent: "Agent"):
        self.agent = agent

    # ----------------------------
    # 系统提示词构建
    # ----------------------------
    def build_system_prompt(self, agent_: Any) -> str:
        """
        构建系统提示词，复用现有之工具使用提示生成逻辑，保持行为一致。
        原生 function calling 激活时不再注入文本工具清单/JSON 帮助（工具由 API tools 提供）。
        """
        if self.agent._native_active():
            action_prompt = ""
        else:
            action_prompt = self.agent.get_tool_usage_prompt()

        # 规则索引已移除，现在使用自动选择规则功能

        # 检查 task_list_manager 工具是否可用
        task_list_manager_note = ""
        tool_registry = self.agent.get_tool_registry()
        if isinstance(tool_registry, ToolRegistry):
            task_list_tool = tool_registry.get_tool("task_list_manager")
            if task_list_tool:
                task_list_manager_note = """
<task_list_manager_guide>
# 任务列表管理工具使用指南
**要点：开始处理任务的第一步，先判断是否需要建立任务列表**
开始执行任务前，先评估任务的复杂程度。**强烈建议：凡需要两步或以上的任务，都应该用 `task_list_manager` 建立任务列表**。即使任务看起来简单，使用任务列表也有助于跟踪进度、记录结果、方便调整。

**应该预先规划的任务类型（符合任一情况即应如此）：**
- **多步任务**：需要两步或以上才能完成的任务（如：实现完整功能模块、重构大型代码库、修改多个文件）
- **有依赖的任务**：任务之间相互依赖，必须按顺序执行（如：先设置数据库表，再实现 API 接口）
- **可并行的任务**：可以同时进行的独立任务（如：并行开发多个功能模块）
- **需要跟踪进度的长期任务**：需要分阶段完成、跟踪进度的长期项目
- **需要不同 Agent 类型的任务**：部分任务需要代码 Agent，部分需要通用 Agent（如：代码实现 + 文档撰写）
- **需要分阶段验证的任务**：每个阶段完成后必须验证，再继续下一步（如：先实现基础功能，测试通过后再添加高级特性）

**🚨 强烈使用的场景：**
1. **第一步：判断是否需要拆分** - 若任务符合上述类型，立即用 `add_tasks` 建立任务列表
2. **同时拆分任务** - 在 `add_tasks` 时一并提供 `main_goal` 与 `tasks_info`，一次建立并添加全部子任务
3. **强制提供 additional_info** - 每次用 `execute_task` 前必须提供详细的 additional_info 参数
4. **执行任务** - 用 `execute_task` 逐个执行任务，系统会自动创建子 Agent

**核心功能：**
- 建立任务列表并添加任务：用 `add_tasks` 操作，可一并提供 `tasks_info` 一次建立并添加全部任务
- 管理任务执行：通过 `execute_task` 自动创建子 Agent 执行任务
- 跟踪任务状态：查看任务执行过程与结果

**使用建议：**
- **关键原则**：开始处理任务的第一步就判断是否需要拆分，若需要则立即建立任务列表，避免先执行部分步骤后才发现需要拆分
- **简单任务不要拆**：若任务可在 1-3 步内完成、只涉及单个文件的修改、或只需单次工具调用，绝不建立任务列表，直接由主 Agent 执行
- **避免过度拆分**：任务拆分应当保持合理的粒度，避免将简单任务拆成过多过细的子任务，这会增加信息传递负担且可能降低效率
- **评估拆分要点**：凡可在 1-2 步内完成的任务，优先由主 Agent 直接执行，不要建立子 Agent
- 建议在 `add_tasks` 时一并提供 `tasks_info`，一次建立并添加全部任务
- 任务之间的依赖可以用任务名引用（系统自动匹配）
- 通过任务列表可以更好地组织和管理任务执行过程，确保任务按正确顺序执行
</task_list_manager_guide>
"""

        system_tools_info = self._get_system_tools_info()

        return f"""
{self.agent.system_prompt}

{action_prompt}

{task_list_manager_note}

{system_tools_info}

"""

    # ----------------------------
    # 系统工具信息
    # ----------------------------
    def _get_system_tools_info(self) -> str:
        """
        返回系统工具信息。

        返回:
            str: 格式化之系统工具信息字符串，供AI助手了解可用工具
        """
        import os
        import platform
        from datetime import datetime

        current_work_dir = os.getcwd()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        os_type = platform.system()  # Linux, Darwin, Windows
        os_release = (
            platform.freedesktop_os_release().get("PRETTY_NAME", platform.release())
            if os_type == "Linux"
            else platform.version()
        )

        return f"""
<system_info>
- 当前工作目录: {current_work_dir}
- 当前时间: {current_time}
- 系统类型: {os_type}
- 系统发行版: {os_release}
</system_info>"""

    def build_default_addon_prompt(self, need_complete: bool) -> str:
        """
        构建默认附加提示词（与 Agent.make_default_addon_prompt 行为保持一致）。
        仅进行字符串拼装，不操作会话状态。
        """
        # 结构化系统指令
        action_handlers = ", ".join(
            [handler.name() for handler in self.agent.output_handler]
        )

        # 任务完成提示
        complete_prompt = (
            f"- 若整个任务已完成，只输出 {ot('!!!COMPLETE!!!')}，不要输出其他内容；任务总结将在后续交互中询问。"
            if need_complete and self.agent.auto_complete
            else ""
        )

        # 原生 function calling 激活时不注入文本 JSON/操作清单指令；文本协议模式保留
        native = bool(self.agent._native_active())

        # 获取当前模型类型和模式提示
        mode_hint = ""
        try:
            from jarvis.jarvis_agent.builtin_input_handler import (
                get_platform_type_from_agent,
            )

            current_model_type = get_platform_type_from_agent(self.agent)
            model_type_display = {
                "smart": "Smart",
                "normal": "Normal",
                "cheap": "Cheap",
            }.get(current_model_type, current_model_type)

            # 根据模型类型推断可能的模式
            mode_hint = f"\n    - 当前使用 {model_type_display} 模型"
        except Exception:
            # 如果获取失败，不添加模式提示
            pass

        if native:
            tool_lines = (
                "    - 需要执行操作时，直接发起工具调用；工具名与参数以当前上下文给出的工具定义为准"
                "\n        - 一次可调用一个或多个互不依赖的工具；有依赖则先等前一个结果再调用下一个"
            )
            actions_line = mode_hint
        else:
            tool_registry = self.agent.get_tool_registry()
            memory_prompts = self.agent.memory_manager.add_memory_prompts_to_addon(
                "", tool_registry if isinstance(tool_registry, ToolRegistry) else None
            )
            tool_lines = (
                "    - 工具调用直接输出 JSON 对象，无需任何标签包裹"
                "\n        - 一次可调用一个或多个工具，但多个工具之间必须**互不依赖**"
                "（前者的结果/副作用不能作为后者的输入）；存在依赖时先调用被依赖的工具，等结果后再调下一个"
            )
            actions_line = f"- 可用操作：{action_handlers}{memory_prompts}{mode_hint}"

        addon_prompt = f"""
<system_prompt>
    先判断整个任务是否已完成：

    - 若已完成：
        {complete_prompt if complete_prompt else "- 说明完成原因并停止，不要再发起新的工具调用"}
    - 若未完成，继续推进下一步：
        - 写文件等大段内容时不要一次性写满，应分多次写入，以免被长度上限截断
        - 需求或信息不明确时，先向用户询问补充
        - 连续 5 次执行失败时，停止并向用户询问应如何继续
        {tool_lines}
        {actions_line}

    补充：若当前这阶段的任务已完成、之前上下文价值不大，可输出 {ot("!!!SUMMARY!!!")} 触发压缩并清空历史，以便开启新阶段。
</system_prompt>

请继续。
"""
        return addon_prompt
