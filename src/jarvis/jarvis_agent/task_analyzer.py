# -*- coding: utf-8 -*-
"""
任务分析器模块
负责处理任务分析和方法论生成功能
"""

from typing import Any, Dict, List

from jarvis.jarvis_agent.events import AFTER_TOOL_CALL
from jarvis.jarvis_agent.events import BEFORE_SUMMARY
from jarvis.jarvis_agent.events import BEFORE_TOOL_CALL
from jarvis.jarvis_agent.events import TASK_COMPLETED
from jarvis.jarvis_agent.prompts import get_task_analysis_prompt
from jarvis.jarvis_agent.utils import join_prompts
from jarvis.jarvis_utils.config import is_enable_auto_methodology_extraction
from jarvis.jarvis_utils.globals import get_interrupt
from jarvis.jarvis_utils.globals import set_interrupt
from jarvis.jarvis_utils.output import PrettyOutput


class TaskAnalyzer:
    """任务分析器，负责任务分析和满意度反馈处理"""

    def __init__(self, agent: Any) -> None:
        """
        初始化任务分析器

        参数:
            agent: Agent实例
        """
        self.agent: Any = agent
        self._analysis_done: bool = False
        self._methodology_extraction_done: bool = False
        # 收集任务执行过程中的信息，用于方法论提取
        self._execution_steps: List[str] = []
        self._tool_calls: List[str] = []
        # 旁路集成事件订阅，失败不影响主流程
        try:
            self._subscribe_events()
        except Exception:
            pass

    def analysis_task(self, satisfaction_feedback: str = "") -> None:
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
            PrettyOutput.auto_print("❌ 分析失败")
        finally:
            # 标记已完成一次分析，避免事件回调重复执行
            self._analysis_done = True
            try:
                self.agent.set_user_data("__task_analysis_done__", True)
            except Exception:
                pass

    def _prepare_analysis_prompt(self, satisfaction_feedback: str) -> str:
        """准备分析提示"""
        # 检查是否有 save_memory 工具（工具可用性）
        has_save_memory = False
        # 检查是否有 meta_agent 工具（原 generate_new_tool，自举式工具生成器）
        has_generate_new_tool = False
        try:
            tool_registry = self.agent.get_tool_registry()
            if tool_registry:
                # 检查 save_memory 工具
                save_memory_tool = tool_registry.get_tool("save_memory")
                has_save_memory = save_memory_tool is not None

                # 检查 meta_agent 工具
                generate_tool = tool_registry.get_tool("meta_agent")
                has_generate_new_tool = generate_tool is not None
        except Exception:
            pass

        # 根据配置获取相应的提示词
        analysis_prompt = get_task_analysis_prompt(
            has_save_memory=has_save_memory, has_generate_new_tool=has_generate_new_tool
        )

        return join_prompts([analysis_prompt, satisfaction_feedback])

    def _process_analysis_loop(self) -> None:
        """处理分析循环"""
        while True:
            response = self.agent.model.chat_until_success(self.agent.session.prompt)
            self.agent.session.prompt = ""

            # 处理用户中断
            if get_interrupt():
                if not self._handle_analysis_interrupt(response):
                    break

            # 执行工具调用（补充事件：before_tool_call/after_tool_call）
            try:
                self.agent.event_bus.emit(
                    BEFORE_TOOL_CALL,
                    agent=self.agent,
                    current_response=response,
                )
            except Exception:
                pass
            need_return, tool_prompt = self.agent._call_tools(response)
            self.agent.session.prompt = tool_prompt
            try:
                self.agent.event_bus.emit(
                    AFTER_TOOL_CALL,
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
            "分析任务期间被中断，请输入用户干预信息", False
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
        if self.agent.confirm_callback(
            "检测到有工具调用，是否继续处理工具调用？", False
        ):
            return join_prompts(
                [f"被用户中断，用户补充信息为：{user_input}", "用户同意继续工具调用。"]
            )
        else:
            return join_prompts(
                [
                    f"被用户中断，用户补充信息为：{user_input}",
                    "检测到有工具调用，但被用户拒绝执行。请根据用户的补充信息重新考虑下一步操作。",
                ]
            )

    def collect_satisfaction_feedback(self, auto_completed: bool) -> str:
        """收集满意度反馈"""
        satisfaction_feedback: str = ""

        # 如果当前是 CodeAgent，跳过满意度收集
        if self.agent.agent_type() == "code_agent":
            return ""

        if not auto_completed and self.agent.use_analysis:
            if self.agent.confirm_callback("您对本次任务的完成是否满意？", True):
                satisfaction_feedback = "用户对本次任务的完成表示满意。"
            else:
                feedback = self.agent._multiline_input(
                    "请提供您的反馈意见（可留空直接回车）", False
                )
                if feedback:
                    satisfaction_feedback = (
                        f"用户对本次任务的完成不满意，反馈意见如下：\n{feedback}"
                    )
                else:
                    satisfaction_feedback = (
                        "用户对本次任务的完成不满意，未提供具体反馈意见。"
                    )
        elif auto_completed and self.agent.use_analysis:
            # 自动完成模式下，仍然执行分析，但不收集用户反馈
            satisfaction_feedback = "任务已自动完成，无需用户反馈。"

        return satisfaction_feedback

    # -----------------------
    # 事件订阅与处理（旁路）
    # -----------------------
    def _subscribe_events(self) -> None:
        bus = self.agent.get_event_bus()
        # 在生成总结前触发（保持与原顺序一致）
        bus.subscribe(BEFORE_SUMMARY, self._on_before_summary)
        # 当无需总结时，作为兜底触发分析
        bus.subscribe(TASK_COMPLETED, self._on_task_completed)

    def _on_before_summary(self, **payload: Any) -> None:
        if self._analysis_done:
            return
        # 避免与直接调用重复
        try:
            if bool(self.agent.get_user_data("__task_analysis_done__")):
                self._analysis_done = True
                return
        except Exception:
            pass

        # 检查是否启用了任务分析
        if not getattr(self.agent, "use_analysis", False):
            self._analysis_done = True
            return

        # 交互模式：询问用户是否执行任务分析（默认True）
        if not self.agent.confirm_callback(
            "任务已完成，是否进行任务分析（保存记忆、生成方法论等）？",
            True if self.agent.non_interactive else False,
        ):
            self._analysis_done = True
            return

        # 非交互模式或用户确认后执行任务分析
        auto_completed = bool(payload.get("auto_completed", False))
        try:
            feedback = self.collect_satisfaction_feedback(auto_completed)
            self.analysis_task(feedback)
        except Exception:
            # 忽略事件处理异常，保证主流程
            self._analysis_done = True

    def _on_task_completed(self, **payload: Any) -> None:
        # 当未在 before_summary 阶段执行过时，作为兜底
        if self._analysis_done:
            return
        try:
            if bool(self.agent.get_user_data("__task_analysis_done__")):
                self._analysis_done = True
                return
        except Exception:
            pass

        # 检查是否启用了任务分析
        if not getattr(self.agent, "use_analysis", False):
            self._analysis_done = True
            return

        # 交互模式：询问用户是否执行任务分析（默认True）
        if not self.agent.confirm_callback(
            "任务已完成，是否进行任务分析（保存记忆、生成方法论等）？",
            True if self.agent.non_interactive else False,
        ):
            self._analysis_done = True
            return

        # 非交互模式或用户确认后执行任务分析
        auto_completed = bool(payload.get("auto_completed", False))
        try:
            feedback = self.collect_satisfaction_feedback(auto_completed)
            self.analysis_task(feedback)
        except Exception:
            self._analysis_done = True

        # 尝试自动提取方法论（旁路逻辑，不影响主流程）
        self._try_extract_methodology()

    def _try_extract_methodology(self) -> None:
        """尝试从任务执行过程中自动提取方法论

        此方法为旁路逻辑，任何异常都不会影响主流程。
        仅在启用 auto_methodology_extraction 配置时执行。
        """
        # 检查是否已经执行过
        if self._methodology_extraction_done:
            return
        self._methodology_extraction_done = True

        # 检查是否启用了方法论自动提取
        if not is_enable_auto_methodology_extraction():
            return

        try:
            self._extract_and_save_methodology()
        except Exception as e:
            # 旁路逻辑，静默失败
            try:
                PrettyOutput.auto_print(f"⚠️ 方法论自动提取失败: {str(e)}")
            except Exception:
                pass

    def _extract_and_save_methodology(self) -> None:
        """执行方法论提取和保存"""
        from jarvis.jarvis_methodology_generator import (
            MethodologyGenerator,
            TaskContext,
        )

        # 获取任务描述
        task_description = getattr(self.agent, "original_user_input", "") or ""
        if not task_description:
            return

        # 收集执行步骤（从对话历史中提取）
        execution_steps = self._collect_execution_steps()
        if len(execution_steps) < 3:
            # 步骤太少，不值得提取方法论
            return

        # 构建任务上下文
        task_context = TaskContext(
            task_description=task_description,
            execution_steps=execution_steps,
            tool_calls=self._collect_tool_calls_as_dicts(),
            decisions=[],  # 决策点需要从对话中提取，暂时留空
            verification_steps=[],  # 验证步骤暂时留空
            actual_output="",
            success=True,  # 任务完成即视为成功
        )

        # 获取现有方法论列表用于去重
        existing_methodologies = self._get_existing_methodologies()

        # 创建生成器并提取方法论
        generator = MethodologyGenerator(existing_methodologies=existing_methodologies)
        result = generator.extract_methodology_from_task(task_context)

        if result:
            self._save_methodology(result)

    def _collect_execution_steps(self) -> List[str]:
        """从对话历史中收集执行步骤"""
        steps: List[str] = []
        try:
            # 尝试从模型的对话历史中提取
            if hasattr(self.agent, "model") and self.agent.model:
                history = getattr(self.agent.model, "_history", [])
                for msg in history:
                    if isinstance(msg, dict):
                        role = msg.get("role", "")
                        content = msg.get("content", "")
                        if role == "assistant" and content:
                            # 提取关键步骤（简化处理）
                            lines = content.split("\n")
                            for line in lines:
                                line = line.strip()
                                # 识别步骤标记
                                if line and (
                                    line.startswith(("1.", "2.", "3.", "4.", "5."))
                                    or line.startswith(("-", "*", "•"))
                                    or "步骤" in line
                                    or "执行" in line
                                ):
                                    if len(line) > 10 and len(line) < 200:
                                        steps.append(line)
        except Exception:
            pass
        return steps[:20]  # 限制步骤数量

    def _collect_tool_calls_as_dicts(self) -> List[Dict[str, Any]]:
        """收集工具调用记录（返回字典列表）"""
        tool_calls: List[Dict[str, Any]] = []
        seen_names: set = set()
        try:
            # 尝试从模型的对话历史中提取工具调用
            if hasattr(self.agent, "model") and self.agent.model:
                history = getattr(self.agent.model, "_history", [])
                for msg in history:
                    if isinstance(msg, dict):
                        content = msg.get("content", "")
                        if "<TOOL_CALL>" in content or "tool_call" in content.lower():
                            # 提取工具名称
                            if '"name":' in content:
                                import re

                                matches = re.findall(r'"name"\s*:\s*"([^"]+)"', content)
                                for name in matches:
                                    if name not in seen_names:
                                        seen_names.add(name)
                                        tool_calls.append({"name": name})
        except Exception:
            pass
        return tool_calls

    def _get_existing_methodologies(self) -> List[str]:
        """获取现有方法论列表"""
        methodologies: List[str] = []
        try:
            from jarvis.jarvis_utils.methodology import _load_all_methodologies

            all_methods = _load_all_methodologies()
            # _load_all_methodologies 返回 List[Tuple[str, str]]，第一个元素是 problem_type
            methodologies = [m[0] for m in all_methods if m[0]]
        except Exception:
            pass
        return methodologies

    def _save_methodology(self, result: dict) -> None:
        """保存提取的方法论"""
        try:
            from jarvis.jarvis_tools.methodology import MethodologyTool

            problem_type = result.get("problem_type", "")
            content = result.get("content", "")
            quality_score = result.get("quality_score", 0)

            if problem_type and content:
                # 使用 MethodologyTool 保存为项目级方法论
                tool = MethodologyTool()
                save_result = tool.execute(
                    {
                        "operation": "add",
                        "problem_type": problem_type,
                        "content": content,
                        "scope": "project",
                    }
                )
                if save_result.get("success"):
                    PrettyOutput.auto_print(
                        f"✅ 已自动提取方法论: {problem_type} (质量分: {quality_score})"
                    )
                else:
                    PrettyOutput.auto_print(
                        f"⚠️ 保存方法论失败: {save_result.get('stderr', '未知错误')}"
                    )
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 保存方法论失败: {str(e)}")
