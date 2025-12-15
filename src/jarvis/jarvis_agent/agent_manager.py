# -*- coding: utf-8 -*-
"""Agent管理器模块，负责Agent的初始化和任务执行"""

from typing import Callable
from typing import Optional

import typer

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_agent import get_multiline_input
from jarvis.jarvis_agent import origin_agent_system_prompt
from jarvis.jarvis_agent.task_manager import TaskManager
from jarvis.jarvis_utils.config import is_non_interactive
from jarvis.jarvis_utils.config import is_skip_predefined_tasks
from jarvis.jarvis_utils.output import PrettyOutput


class AgentManager:
    """Agent管理器，负责Agent的生命周期管理"""

    def __init__(
        self,
        model_group: Optional[str] = None,
        tool_group: Optional[str] = None,
        restore_session: bool = False,
        use_methodology: Optional[bool] = None,
        use_analysis: Optional[bool] = None,
        multiline_inputer: Optional[Callable[[str], str]] = None,
        confirm_callback: Optional[Callable[[str, bool], bool]] = None,
        non_interactive: Optional[bool] = None,
    ):
        self.model_group = model_group
        self.tool_group = tool_group
        self.restore_session = restore_session
        self.use_methodology = use_methodology
        self.use_analysis = use_analysis
        self.agent: Optional[Agent] = None
        # 可选：注入输入与确认回调，用于Web模式等前端替代交互
        self.multiline_inputer = multiline_inputer
        self.confirm_callback = confirm_callback
        self.non_interactive = non_interactive

    def initialize(self) -> Agent:
        """初始化Agent"""
        # 如果提供了 tool_group 参数，设置到配置中
        if self.tool_group:
            from jarvis.jarvis_utils.config import set_config

            set_config("tool_group", self.tool_group)

        self.agent = Agent(
            system_prompt=origin_agent_system_prompt,
            model_group=self.model_group,
            need_summary=False,
            use_methodology=self.use_methodology,
            use_analysis=self.use_analysis,
            multiline_inputer=self.multiline_inputer,
            confirm_callback=self.confirm_callback,
            non_interactive=self.non_interactive,
        )

        # 尝试恢复会话
        if self.restore_session:
            if self.agent.restore_session():
                PrettyOutput.auto_print("✅ 会话已成功恢复。")
            else:
                PrettyOutput.auto_print("⚠️ 无法恢复会话。")

        return self.agent

    def run_task(self, task_content: Optional[str] = None) -> None:
        """运行任务"""
        if not self.agent:
            raise RuntimeError("Agent not initialized")

        # 优先处理命令行直接传入的任务
        if task_content:
            self.agent.run(task_content)
            raise typer.Exit(code=0)

        # 处理预定义任务（非交互模式下跳过；支持配置跳过加载；命令行指定任务时跳过）
        if (
            not is_non_interactive()
            and not is_skip_predefined_tasks()
            and not task_content
            and self.agent.first
        ):
            task_manager = TaskManager()
            tasks = task_manager.load_tasks()
            if tasks and (selected_task := task_manager.select_task(tasks)):
                PrettyOutput.auto_print(f"ℹ️ 开始执行任务: \n{selected_task}")
                self.agent.run(selected_task)
                raise typer.Exit(code=0)

        # 获取用户输入
        user_input = get_multiline_input("请输入你的任务（输入空行退出）:")
        if user_input:
            self.agent.run(user_input)
        raise typer.Exit(code=0)
