# -*- coding: utf-8 -*-
"""Agent管理器模块，负责Agent的初始化和任务执行"""
from typing import Optional

import typer

from jarvis.jarvis_agent import (
    Agent,
    OutputType,
    PrettyOutput,
    get_multiline_input,
    origin_agent_system_prompt,
)
from jarvis.jarvis_agent.builtin_input_handler import builtin_input_handler
from jarvis.jarvis_agent.shell_input_handler import shell_input_handler
from jarvis.jarvis_agent.task_manager import TaskManager
from jarvis.jarvis_tools.registry import ToolRegistry


class AgentManager:
    """Agent管理器，负责Agent的生命周期管理"""

    def __init__(
        self,
        model_group: Optional[str] = None,
        tool_group: Optional[str] = None,
        restore_session: bool = False,
        use_methodology: Optional[bool] = None,
        use_analysis: Optional[bool] = None,
    ):
        self.model_group = model_group
        self.tool_group = tool_group
        self.restore_session = restore_session
        self.use_methodology = use_methodology
        self.use_analysis = use_analysis
        self.agent: Optional[Agent] = None

    def initialize(self) -> Agent:
        """初始化Agent"""
        # 如果提供了 tool_group 参数，设置到配置中
        if self.tool_group:
            from jarvis.jarvis_utils.config import set_config

            set_config("JARVIS_TOOL_GROUP", self.tool_group)

        self.agent = Agent(
            system_prompt=origin_agent_system_prompt,
            model_group=self.model_group,
            input_handler=[shell_input_handler, builtin_input_handler],
            output_handler=[ToolRegistry()],  # type: ignore
            need_summary=False,
            use_methodology=self.use_methodology,
            use_analysis=self.use_analysis,
        )

        # 尝试恢复会话
        if self.restore_session:
            if self.agent.restore_session():
                PrettyOutput.print("会话已成功恢复。", OutputType.SUCCESS)
            else:
                PrettyOutput.print("无法恢复会话。", OutputType.WARNING)

        return self.agent

    def run_task(self, task_content: Optional[str] = None) -> None:
        """运行任务"""
        if not self.agent:
            raise RuntimeError("Agent not initialized")

        # 优先处理命令行直接传入的任务
        if task_content:
            self.agent.run(task_content)
            raise typer.Exit(code=0)

        # 处理预定义任务
        if self.agent.first:
            task_manager = TaskManager()
            tasks = task_manager.load_tasks()
            if tasks and (selected_task := task_manager.select_task(tasks)):
                PrettyOutput.print(f"开始执行任务: \n{selected_task}", OutputType.INFO)
                self.agent.run(selected_task)
                raise typer.Exit(code=0)

        # 获取用户输入
        user_input = get_multiline_input("请输入你的任务（输入空行退出）:")
        if user_input:
            self.agent.run(user_input)
        raise typer.Exit(code=0)
