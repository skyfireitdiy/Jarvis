# -*- coding: utf-8 -*-
"""
PromptManager: 统一管理 Agent 的系统提示词与附加提示词的构建逻辑。

设计目标（阶段一，最小变更）：
- 提供独立的提示构建类，不改变现有行为
- 先行落地构建逻辑，后续在 Agent 中逐步委派使用
- 保持与现有工具/记忆系统兼容
"""

import shutil
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
    注意：该类不直接访问模型，只负责拼装字符串。
    """

    def __init__(self, agent: "Agent"):
        self.agent = agent

    # ----------------------------
    # 系统提示词构建
    # ----------------------------
    def build_system_prompt(self, agent_: Any) -> str:
        """
        构建系统提示词，复用现有的工具使用提示生成逻辑，保持行为一致。
        """
        from jarvis.jarvis_code_agent.code_agent import CodeAgent

        rules_prompt = ""
        if isinstance(agent_, CodeAgent):
            code_agent: CodeAgent = agent_
            rules_prompt = code_agent.get_rules_prompt()

        action_prompt = self.agent.get_tool_usage_prompt()

        # 检查 task_list_manager 工具是否可用
        task_list_manager_note = ""
        tool_registry = self.agent.get_tool_registry()
        if isinstance(tool_registry, ToolRegistry):
            task_list_tool = tool_registry.get_tool("task_list_manager")
            if task_list_tool:
                task_list_manager_note = """

<task_list_manager_guide>
# 任务列表管理工具使用指南

**重要：在开始处理任务的第一步，先判断是否需要创建任务列表**

在开始执行任务之前，首先评估任务复杂度。**强烈建议：对于任何需要2个或以上步骤的任务，都应该使用 `task_list_manager` 创建任务列表**。即使任务看似简单，使用任务列表也有助于跟踪进度、记录结果和便于调试。

**适合提前规划的任务类型（符合任一情况即应使用）：**
- **多步骤任务**：需要2个或以上步骤才能完成的任务（如：实现完整功能模块、重构大型代码库、修改多个文件）
- **有依赖关系的任务**：任务之间存在依赖，需要按顺序执行（如：先设计数据库表，再实现API接口）
- **需要并行执行的任务**：可以同时进行的独立任务（如：同时开发多个功能模块）
- **需要跟踪进度的长期任务**：需要分阶段完成、跟踪进度的长期项目
- **需要不同Agent类型的任务**：部分任务需要代码Agent，部分需要通用Agent（如：代码实现 + 文档编写）
- **需要分阶段验证的任务**：每个阶段完成后需要验证，再继续下一步（如：先实现基础功能，测试通过后再添加高级特性）

**🚨 强制使用流程：**
1. **第一步：识别是否需要拆分** - 如果任务符合上述类型，立即使用 `add_tasks` 创建任务列表
2. **同时拆分任务** - 在 `add_tasks` 时同时提供 `main_goal` 和 `tasks_info`，一次性创建并添加所有子任务
3. **强制准备additional_info** - 每次使用 `execute_task` 前必须准备详细的 additional_info 参数
4. **执行任务** - 使用 `execute_task` 逐个执行任务，系统会自动创建子 Agent

**核心功能：**
- 创建任务列表并添加任务：使用 `add_tasks` 操作，可同时提供 `tasks_info` 一次性创建并添加所有任务
- 管理任务执行：通过 `execute_task` 自动创建子 Agent 执行任务
- 跟踪任务状态：查看任务执行进度和结果

**使用建议：**
- **关键原则**：在开始执行任务的第一步就判断是否需要拆分，如果需要则立即创建任务列表，避免先执行部分步骤再意识到需要拆分
- **简单任务无需拆分**：如果任务可以在1-3步内完成、只涉及单个文件修改、或只需要单次工具调用，绝对不要创建任务列表，直接由主Agent执行
- **避免过度拆分**：任务拆分应该保持合理粒度，避免将简单任务拆分成过多过细的子任务，这会增加信息传递负担并可能降低执行效率
- **评估拆分必要性**：对于可以在1-2步内完成的任务，优先考虑由主Agent直接执行，而不是创建子Agent
- 推荐在 `add_tasks` 时同时提供 `tasks_info`，一次性创建任务列表并添加所有任务
- 任务之间的依赖关系可以使用任务名称引用（系统会自动匹配）
- 通过任务列表可以更好地组织和管理任务执行流程，确保任务按正确顺序执行
</task_list_manager_guide>
"""

        system_tools_info = self._get_system_tools_info()

        return f"""
{self.agent.system_prompt}

{action_prompt}

{task_list_manager_note}

{system_tools_info}

{rules_prompt}
"""

    # ----------------------------
    # 系统工具信息
    # ----------------------------
    def _get_system_tools_info(self) -> str:
        """
        检测并返回rg和fd命令的安装状态信息。

        返回:
            str: 格式化的系统工具信息字符串，供AI助手了解可用工具
        """
        tools = []

        # 检测rg命令
        rg_installed = shutil.which("rg") is not None
        tools.append(f"rg_available: {rg_installed}")

        # 检测fd命令
        fd_installed = shutil.which("fd") is not None
        tools.append(f"fd_available: {fd_installed}")

        import os

        current_work_dir = os.getcwd()

        return (
            """
<system_info>
可用工具:
"""
            + "\n".join(f"- {tool}" for tool in tools)
            + f"""
- rg: 递归快速搜索文件内容（ripgrep）
- fd: 快速查找文件（fd-find）
- 当前工作目录: {current_work_dir}
</system_info>"""
        )

    # ----------------------------
    # 附加提示词构建
    # ----------------------------
    def _format_token_metadata(self) -> str:
        """
        格式化token元数据信息，包括已用token和剩余token。

        返回:
            str: 格式化的token元数据字符串，如果无法获取则返回空字符串
        """
        try:
            used_tokens = self.agent.session.conversation_length
            remaining_tokens = self.agent.get_remaining_token_count()

            # 如果无法获取有效数据，返回空字符串
            if used_tokens == 0 and remaining_tokens == 0:
                return ""

            return f"[Agent元数据] 已用token: {used_tokens} | 剩余token: {remaining_tokens}"
        except Exception:
            return ""

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
            f"- 如果任务已完成，只输出 {ot('!!!COMPLETE!!!')}，不要输出其他任何内容。任务总结将会在后面的交互中被询问。"
            if need_complete and self.agent.auto_complete
            else ""
        )

        # 工具与记忆相关提示
        tool_registry = self.agent.get_tool_registry()
        memory_prompts = self.agent.memory_manager.add_memory_prompts_to_addon(
            "", tool_registry if isinstance(tool_registry, ToolRegistry) else None
        )

        # 获取token元数据
        token_metadata = self._format_token_metadata()
        token_metadata_prompt = f"{token_metadata}\n" if token_metadata else ""

        addon_prompt = f"""
<system_prompt>
{token_metadata_prompt}    请判断是否已经完成任务，如果已经完成：
    {complete_prompt if complete_prompt else f"- 直接输出完成原因，不需要再有新的操作，不要输出{ot('TOOL_CALL')}标签"}
    如果没有完成，请进行下一步操作：
    - 仅包含一个操作
    - 如果信息不明确，请请求用户补充
    - 如果执行过程中连续失败5次，请请求用户操作
    - 操作列表：{action_handlers}{memory_prompts}
</system_prompt>

请继续。
"""
        return addon_prompt
