# -*- coding: utf-8 -*-
"""
任务分析器模块
负责处理任务分析和方法论生成功能
"""
from typing import Optional

from jarvis.jarvis_utils.globals import get_interrupt, set_interrupt
from jarvis.jarvis_utils.input import user_confirm
from jarvis.jarvis_agent.prompts import TASK_ANALYSIS_PROMPT
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class TaskAnalyzer:
    """任务分析器，负责任务分析和满意度反馈处理"""

    def __init__(self, agent):
        """
        初始化任务分析器

        参数:
            agent: Agent实例
        """
        self.agent = agent

    def analysis_task(self, satisfaction_feedback: str = ""):
        """分析任务并生成方法论"""

        try:
            # 准备分析提示
            self.agent.session.prompt = self._prepare_analysis_prompt(
                satisfaction_feedback
            )

            if not self.agent.model:
                raise RuntimeError("Model not initialized")

            # 循环处理工具调用，直到没有工具调用为止
            self._process_analysis_loop()

        except Exception as e:
            PrettyOutput.print("分析失败", OutputType.ERROR)

    def _prepare_analysis_prompt(self, satisfaction_feedback: str) -> str:
        """准备分析提示"""
        analysis_prompt = TASK_ANALYSIS_PROMPT
        if satisfaction_feedback:
            analysis_prompt += satisfaction_feedback
        return analysis_prompt

    def _process_analysis_loop(self):
        """处理分析循环"""
        while True:
            response = self.agent.model.chat_until_success(self.agent.session.prompt)  # type: ignore
            self.agent.session.prompt = ""

            # 处理用户中断
            if get_interrupt():
                if not self._handle_analysis_interrupt(response):
                    break

            # 执行工具调用
            need_return, self.agent.session.prompt = self.agent._call_tools(response)

            # 如果没有工具调用或者没有新的提示，退出循环
            if not self.agent.session.prompt:
                break

    def _handle_analysis_interrupt(self, response: str) -> bool:
        """处理分析过程中的用户中断

        返回:
            bool: True 继续分析，False 退出分析
        """
        set_interrupt(False)
        user_input = self.agent.multiline_inputer(
            f"分析任务期间被中断，请输入用户干预信息："
        )

        if not user_input:
            # 用户输入为空，退出分析
            return False

        if self._has_tool_calls(response):
            self.agent.session.prompt = self._handle_interrupt_with_tool_calls(
                user_input
            )
        else:
            self.agent.session.prompt = f"被用户中断，用户补充信息为：{user_input}"

        return True

    def _has_tool_calls(self, response: str) -> bool:
        """检查响应中是否有工具调用"""
        return any(
            handler.can_handle(response) for handler in self.agent.output_handler
        )

    def _handle_interrupt_with_tool_calls(self, user_input: str) -> str:
        """处理有工具调用时的中断"""
        if user_confirm("检测到有工具调用，是否继续处理工具调用？", True):
            return f"被用户中断，用户补充信息为：{user_input}\n\n用户同意继续工具调用。"
        else:
            return f"被用户中断，用户补充信息为：{user_input}\n\n检测到有工具调用，但被用户拒绝执行。请根据用户的补充信息重新考虑下一步操作。"

    def collect_satisfaction_feedback(self, auto_completed: bool) -> str:
        """收集满意度反馈"""
        satisfaction_feedback = ""

        if not auto_completed and self.agent.use_analysis:
            if user_confirm("您对本次任务的完成是否满意？", True):
                satisfaction_feedback = "\n\n用户对本次任务的完成表示满意。"
            else:
                feedback = self.agent.multiline_inputer(
                    "请提供您的反馈意见（可留空直接回车）:"
                )
                if feedback:
                    satisfaction_feedback = (
                        f"\n\n用户对本次任务的完成不满意，反馈意见如下：\n{feedback}"
                    )
                else:
                    satisfaction_feedback = (
                        "\n\n用户对本次任务的完成不满意，未提供具体反馈意见。"
                    )

        return satisfaction_feedback
