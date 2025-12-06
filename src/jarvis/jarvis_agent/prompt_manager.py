# -*- coding: utf-8 -*-
"""
PromptManager: 统一管理 Agent 的系统提示词与附加提示词的构建逻辑。

设计目标（阶段一，最小变更）：
- 提供独立的提示构建类，不改变现有行为
- 先行落地构建逻辑，后续在 Agent 中逐步委派使用
- 保持与现有工具/记忆系统兼容
"""

from typing import TYPE_CHECKING

from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.tag import ot

if TYPE_CHECKING:
    # 避免运行时循环依赖，仅用于类型标注
    from . import Agent  # noqa: F401


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
    def build_system_prompt(self) -> str:
        """
        构建系统提示词，复用现有的工具使用提示生成逻辑，保持行为一致。
        """
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
在 **PLAN（规划）模式**中，你可以使用 `task_list_manager` 工具来：
- 创建任务列表：将复杂任务分解为多个子任务，建立清晰的任务结构
- 批量添加任务：使用 `add_tasks` 操作一次性添加多个任务（推荐在 PLAN 阶段使用）
- 添加单个任务：使用 `add_task` 操作逐个添加任务（适用于后续补充任务）
- 管理任务状态：跟踪任务执行进度，确保任务按计划完成

使用建议：
- 当任务较为复杂，需要分解为多个步骤时，建议在 PLAN 模式中使用 task_list_manager 创建任务列表
- **推荐使用 `add_tasks` 批量添加任务**：在 PLAN 阶段一次性拆分并创建所有子任务，而不是逐个添加
- 批量添加时，任务之间的依赖关系可以引用本次批次中的任务ID
- 通过任务列表可以更好地组织和管理任务执行流程
- 任务列表支持依赖关系，确保任务按正确顺序执行
</task_list_manager_guide>
"""

        return f"""
{self.agent.system_prompt}

{action_prompt}{task_list_manager_note}
"""

    # ----------------------------
    # 附加提示词构建
    # ----------------------------
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
            f"- 输出{ot('!!!COMPLETE!!!')}"
            if need_complete and self.agent.auto_complete
            else ""
        )

        # 工具与记忆相关提示
        tool_registry = self.agent.get_tool_registry()
        memory_prompts = self.agent.memory_manager.add_memory_prompts_to_addon(
            "", tool_registry if isinstance(tool_registry, ToolRegistry) else None
        )

        addon_prompt = f"""
<system_prompt>
    请判断是否已经完成任务，如果已经完成：
    - 直接输出完成原因，不需要再有新的操作，不要输出{ot("TOOL_CALL")}标签
    {complete_prompt}
    如果没有完成，请进行下一步操作：
    - 仅包含一个操作
    - 如果信息不明确，请请求用户补充
    - 如果执行过程中连续失败5次，请请求用户操作
    - 操作列表：{action_handlers}{memory_prompts}
</system_prompt>

请继续。
"""
        return addon_prompt
