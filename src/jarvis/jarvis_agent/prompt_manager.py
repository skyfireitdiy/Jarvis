# -*- coding: utf-8 -*-
"""
PromptManager: 统一管理 Agent 的系统提示词与附加提示词的构建逻辑。

设计目标（阶段一，最小变更）：
- 提供独立的提示构建类，不改变现有行为
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
# 任务列表管理工具使用之指南

**要：始理任之首步，先判应否建任列**

始执任前，先估任之繁。**强荐：凡需二步或以上之任，皆应用 `task_list_manager` 建任列**。纵任似简，用任列亦助进度之踪、果之记、调之便。

**宜豫规之任类（符任一情即应）：**
- **多步之任**：需二步或以上方竟之任（如：实完功能模、重构大库、改多文）
- **有依之任**：任间相依，须按序执（如：先设库表，再实API口）
- **可并之任**：可同行之独任（如：并开多功模）
- **须踪程之远任**：须分阶完、踪程之远项目
- **需异Agent类之任**：部任需代码Agent，部需通用Agent（如：码实 + 文撰）
- **需分阶验之任**：每阶竟后须验，再续下步（如：先实基功，测通后再添高特）

**🚨 强用之程：**
1. **首步：识是否需分** - 若任符上述之类，即用 `add_tasks` 建任列
2. **同分任** - 于 `add_tasks` 时并供 `main_goal` 与 `tasks_info`，一次建并添全子任
3. **强制备additional_info** - 每用 `execute_task` 前必备详之 additional_info 参
4. **执任** - 用 `execute_task` 逐任行之，系自建子 Agent

**核功：**
- 建任列并添任：用 `add_tasks` 操，可并供 `tasks_info` 一次建并添全任
- 管任执：经 `execute_task` 自建子 Agent 执任
- 踪任态：查任执程与果

**用议：**
- **键原**：始理任之首步即判应否分，若需则即建任列，免先执部步后悟需分
- **简任毋拆**：若任可于1-3步内竟、唯涉单文之改、或唯需单次工具调，绝不建任列，直由主Agent执
- **免过拆**：任拆当保合之度，免将简任拆成过多过细之子任，此增讯递担且或降效
- **评拆之要**：凡可于1-2步内竟之任，优先主Agent直执，勿建子Agent
- 荐于 `add_tasks` 时并供 `tasks_info`，一次建任列并添全任
- 任间之依可用任名引之（系自匹）
- 经任列可善组管任执程，确任按正序执
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
            str: 格式化的系统工具信息字符串，供AI助手了解可用工具
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
            f"- 若任已竟，唯出 {ot('!!!COMPLETE!!!')}，勿出他文。任结将于后交互中见询。"
            if need_complete and self.agent.auto_complete
            else ""
        )

        # 工具与记忆相关提示
        tool_registry = self.agent.get_tool_registry()
        memory_prompts = self.agent.memory_manager.add_memory_prompts_to_addon(
            "", tool_registry if isinstance(tool_registry, ToolRegistry) else None
        )

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

        addon_prompt = f"""
<system_prompt>
    请判任已竟否，若竟：
    {complete_prompt if complete_prompt else "- 直出竟之由，毋需再作新操"}
    若未竟，请行下步：
    - 唯含一操
    - 调工具时，忌一性写或执大内，写文应分写，以免为上下限所截
    - 若讯不明，请询用补
    - 若执中连败5次，请询用操
    - 操列：{action_handlers}{memory_prompts}{mode_hint}
</system_prompt>

请续。
"""
        return addon_prompt
