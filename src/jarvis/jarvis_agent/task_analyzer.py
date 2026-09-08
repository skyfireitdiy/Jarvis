# -*- coding: utf-8 -*-
"""
任务分析器模块
负责处理任务分析和方法论生成功能
"""

from typing import Any, List

from jarvis.jarvis_agent.events import AFTER_TOOL_CALL
from jarvis.jarvis_agent.events import BEFORE_TOOL_CALL
from jarvis.jarvis_agent.prompts import get_task_analysis_prompt
from jarvis.jarvis_agent.utils import join_prompts
from jarvis.jarvis_utils.globals import get_interrupt
from jarvis.jarvis_utils.globals import set_interrupt
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.exception_utils import save_exception

# 原生 function calling 激活时的任务分析提示：保留原决策逻辑，仅改现代白话、去文本 JSON
_NATIVE_TASK_ANALYSIS_PROMPT = """对刚结束的任务做一次复盘。需要操作时**直接调用工具**，不要输出 JSON 文本。按以下顺序判断：

1. **记忆沉淀**：用 memory(action=save) 保存值得长期留存的信息：
   - project_long_term：项目相关（架构决策、关键约定、重要实现）
   - global_long_term：通用经验、用户偏好、方法技巧
   没有值得存的就不存。
2. **现有能力评估**：先判断当前已有工具/方法论是否已能覆盖本任务解法——
   - 若能覆盖：直接说明用哪个即可，不需要新建。
   - 若不能、且该任务确实值得沉淀：
     a) 若是一个**可复用、成体系的解法/流程**：用 methodology 新增或更新
        （operation add/update；scope：项目相关用 project、通用用 global；
        content 按 rule 文档结构组织：规则简介、必须遵守的原则、必须执行的操作、
        实践指导/自检，便于后续复用与检索）。
     b) 若缺的是一个**自动化工具**：用 meta_agent 生成
        （function_description 写清目标功能与预期行为；工具须含参数定义与错误处理）。
3. **规则建议（可选）**：仅当现有规则确有明显缺口时才简述建议；没有就不提。
4. 最后用一句话总结本次复盘结论。

规则：以事实为准、不编造；宁缺毋滥；methodology/meta_agent 仅在真正值得时用，不为了生成而生成。"""


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
            PrettyOutput.auto_print("❌ 析败")
        finally:
            # 标记已完成一次分析，避免事件回调重复执行
            self._analysis_done = True
            try:
                self.agent.set_user_data("__task_analysis_done__", True)
            except Exception as e:
                save_exception(
                    e, module="jarvis_agent.task_analyzer", function="analysis_task"
                )
                pass

    def _prepare_analysis_prompt(self, satisfaction_feedback: str) -> str:
        """准备分析提示"""
        # 检查是否有 memory 工具（工具可用性）
        has_memory_tool = False
        # 检查是否有 meta_agent 工具（原 generate_new_tool，自举式工具生成器）
        has_generate_new_tool = False
        try:
            tool_registry = self.agent.get_tool_registry()
            if tool_registry:
                # 检查 memory 工具
                memory_tool = tool_registry.get_tool("memory")
                has_memory_tool = memory_tool is not None

                # 检查 meta_agent 工具
                generate_tool = tool_registry.get_tool("meta_agent")
                has_generate_new_tool = generate_tool is not None
        except Exception as e:
            save_exception(
                e,
                module="jarvis_agent.task_analyzer",
                function="_prepare_analysis_prompt",
            )
            pass

        # 原生 function calling 激活时用简洁现代提示（工具直接调用，不走文本 JSON）
        if self.agent._native_active():
            analysis_prompt = _NATIVE_TASK_ANALYSIS_PROMPT
        else:
            # 文本协议路径：使用带 JSON 调用格式说明的历史提示词
            analysis_prompt = get_task_analysis_prompt(
                has_memory_tool=has_memory_tool,
                has_generate_new_tool=has_generate_new_tool,
            )

        return join_prompts([analysis_prompt, satisfaction_feedback])

    def _process_analysis_loop(self) -> None:
        """处理分析循环"""
        while True:
            # 原生 function calling 激活时，走 Agent._invoke_model 的原生通道：
            # 工具（memory/methodology/meta_agent 等）由内部原生循环执行并触发 AFTER_TOOL_CALL，
            # 不再用文本 JSON 解析。
            if (
                self.agent._native_active()
                and isinstance(self.agent.session.prompt, str)
                and self.agent.session.prompt.strip()
            ):
                try:
                    self.agent._invoke_model(self.agent.session.prompt)
                finally:
                    self.agent.session.prompt = ""
                return

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
            except Exception as e:
                save_exception(
                    e,
                    module="jarvis_agent.task_analyzer",
                    function="_process_analysis_loop",
                )
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
            except Exception as e:
                save_exception(
                    e,
                    module="jarvis_agent.task_analyzer",
                    function="_process_analysis_loop",
                )
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
        user_input = self.agent._multiline_input("分析期间被中断，请输入干预信息", False)

        if not user_input:
            # 用户输入为空，退出分析
            return False

        if self._has_tool_calls(response):
            self.agent.session.prompt = self._handle_interrupt_with_tool_calls(
                user_input
            )
        else:
            self.agent.session.prompt = f"任务被用户中断，用户补充信息为：{user_input}"

        return True

    def _has_tool_calls(self, response: str) -> bool:
        """检查响应中是否有工具调用"""
        return any(
            handler.can_handle(response) for handler in self.agent.output_handler
        )

    def _handle_interrupt_with_tool_calls(self, user_input: str) -> str:
        """处理有工具调用时的中断"""
        if self.agent.confirm_callback("检测到工具调用，是否继续执行？", False):
            return join_prompts(
                [
                    f"任务被用户中断，用户补充信息为：{user_input}",
                    "用户允许继续工具调用。",
                ]
            )
        else:
            return join_prompts(
                [
                    f"任务被用户中断，用户补充信息为：{user_input}",
                    "检测到工具调用，但被用户拒绝。请根据用户的补充信息重新考虑下一步操作。",
                ]
            )

    def collect_satisfaction_feedback(self, auto_completed: bool) -> str:
        """收集满意度反馈"""
        satisfaction_feedback: str = ""

        # 如果当前是 CodeAgent，跳过满意度收集
        if self.agent.agent_type() == "code_agent":
            return ""

        if not auto_completed and self.agent.use_analysis:
            if self.agent.confirm_callback("本次任务完成，您是否满意？", True):
                satisfaction_feedback = "用户对本次任务的完成表示满意。"
            else:
                feedback = self.agent._multiline_input(
                    "请提供改进反馈（可直接回车跳过）", False
                )
                if feedback:
                    satisfaction_feedback = (
                        f"用户对本次任务的完成不满意，反馈如下：\n{feedback}"
                    )
                else:
                    satisfaction_feedback = "用户对本次任务的完成不满意，未提供具体反馈。"
        elif auto_completed and self.agent.use_analysis:
            # 自动完成模式下，仍然执行分析，但不收集用户反馈
            satisfaction_feedback = "任务已自动完成，无需用户反馈。"

        return satisfaction_feedback

    def trigger_task_analysis(self, auto_completed: bool = False) -> None:
        """触发任务分析和满意度收集

        该方法将替代原有的事件驱动机制，直接由Agent调用

        参数:
            auto_completed: 是否为自动完成模式
        """
        if self._analysis_done:
            return
        # 避免重复执行
        try:
            if bool(self.agent.get_user_data("__task_analysis_done__")):
                self._analysis_done = True
                return
        except Exception as e:
            save_exception(
                e, module="jarvis_agent.task_analyzer", function="trigger_task_analysis"
            )
            pass

        # 任务完成后统一默认启用任务分析（默认True），不再区分场景
        if not self.agent.confirm_callback(
            "任务已完成，是否进行任务分析（保存记忆、生成方法论等）？",
            True,
        ):
            self._analysis_done = True
            return

        # 非交互模式或用户确认后执行任务分析
        try:
            feedback = self.collect_satisfaction_feedback(auto_completed)
            self.analysis_task(feedback)
        except Exception:
            # 忽略异常，保证主流程
            self._analysis_done = True

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
        except Exception as e:
            save_exception(
                e,
                module="jarvis_agent.task_analyzer",
                function="_collect_execution_steps",
            )
            pass
        return steps[:20]  # 限制步骤数量
