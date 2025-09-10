# -*- coding: utf-8 -*-
"""
任务分析器模块
负责处理任务分析和方法论生成功能
"""

from jarvis.jarvis_utils.globals import get_interrupt, set_interrupt

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
        self._analysis_done = False
        # 旁路集成事件订阅，失败不影响主流程
        try:
            self._subscribe_events()
        except Exception:
            pass

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

        except Exception:
            PrettyOutput.print("分析失败", OutputType.ERROR)
        finally:
            # 标记已完成一次分析，避免事件回调重复执行
            self._analysis_done = True
            try:
                self.agent.set_user_data("__task_analysis_done__", True)
            except Exception:
                pass

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

            # 执行工具调用（补充事件：before_tool_call/after_tool_call）
            try:
                self.agent.event_bus.emit(
                    "before_tool_call",
                    agent=self.agent,
                    current_response=response,
                )
            except Exception:
                pass
            need_return, tool_prompt = self.agent._call_tools(response)
            self.agent.session.prompt = tool_prompt
            try:
                self.agent.event_bus.emit(
                    "after_tool_call",
                    agent=self.agent,
                    current_response=response,
                    need_return=need_return,
                    tool_prompt=tool_prompt,
                )
            except Exception:
                pass

            # 如果没有工具调用或者没有新的提示，退出循环
            if not self.agent.session.prompt:
                break

    def _handle_analysis_interrupt(self, response: str) -> bool:
        """处理分析过程中的用户中断

        返回:
            bool: True 继续分析，False 退出分析
        """
        set_interrupt(False)
        user_input = self.agent._multiline_input(
            "分析任务期间被中断，请输入用户干预信息：", False
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
        if self.agent.user_confirm("检测到有工具调用，是否继续处理工具调用？", True):
            return f"被用户中断，用户补充信息为：{user_input}\n\n用户同意继续工具调用。"
        else:
            return f"被用户中断，用户补充信息为：{user_input}\n\n检测到有工具调用，但被用户拒绝执行。请根据用户的补充信息重新考虑下一步操作。"

    def collect_satisfaction_feedback(self, auto_completed: bool) -> str:
        """收集满意度反馈"""
        satisfaction_feedback = ""

        if not auto_completed and self.agent.use_analysis:
            if self.agent.user_confirm("您对本次任务的完成是否满意？", True):
                satisfaction_feedback = "\n\n用户对本次任务的完成表示满意。"
            else:
                feedback = self.agent._multiline_input(
                    "请提供您的反馈意见（可留空直接回车）:", False
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

    # -----------------------
    # 事件订阅与处理（旁路）
    # -----------------------
    def _subscribe_events(self) -> None:
        bus = self.agent.get_event_bus()  # type: ignore[attr-defined]
        # 在生成总结前触发（保持与原顺序一致）
        bus.subscribe("before_summary", self._on_before_summary)
        # 当无需总结时，作为兜底触发分析
        bus.subscribe("task_completed", self._on_task_completed)

    def _on_before_summary(self, **payload) -> None:
        if self._analysis_done:
            return
        # 避免与直接调用重复
        try:
            if bool(self.agent.get_user_data("__task_analysis_done__")):
                self._analysis_done = True
                return
        except Exception:
            pass
        auto_completed = bool(payload.get("auto_completed", False))
        try:
            feedback = self.collect_satisfaction_feedback(auto_completed)
            if getattr(self.agent, "use_analysis", False):
                self.analysis_task(feedback)
        except Exception:
            # 忽略事件处理异常，保证主流程
            self._analysis_done = True

    def _on_task_completed(self, **payload) -> None:
        # 当未在 before_summary 阶段执行过时，作为兜底
        if self._analysis_done:
            return
        try:
            if bool(self.agent.get_user_data("__task_analysis_done__")):
                self._analysis_done = True
                return
        except Exception:
            pass
        auto_completed = bool(payload.get("auto_completed", False))
        try:
            feedback = self.collect_satisfaction_feedback(auto_completed)
            if getattr(self.agent, "use_analysis", False):
                self.analysis_task(feedback)
        except Exception:
            self._analysis_done = True
