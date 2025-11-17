# -*- coding: utf-8 -*-
"""
AgentRunLoop: 承载 Agent 的主运行循环逻辑。

阶段一目标（最小变更）：
- 复制现有 _main_loop 逻辑到独立类，使用传入的 agent 实例进行委派调用
- 暂不变更外部调用入口，后续在 Agent._main_loop 中委派到该类
- 保持与现有异常处理、工具调用、用户交互完全一致
"""
import os
from enum import Enum
from typing import Any, TYPE_CHECKING

from jarvis.jarvis_agent.events import BEFORE_TOOL_CALL, AFTER_TOOL_CALL
from jarvis.jarvis_agent.utils import join_prompts, is_auto_complete, normalize_next_action
from jarvis.jarvis_utils.config import get_auto_summary_rounds

if TYPE_CHECKING:
    # 仅用于类型标注，避免运行时循环依赖
    from . import Agent  # noqa: F401


class AgentRunLoop:
    def __init__(self, agent: "Agent") -> None:
        self.agent = agent
        self.conversation_rounds = 0
        self.tool_reminder_rounds = int(os.environ.get("JARVIS_TOOL_REMINDER_ROUNDS", 20))
        # 基于轮次的自动总结阈值：优先使用 Agent 入参，否则回落到全局配置（默认20轮）
        self.auto_summary_rounds = (
            self.agent.auto_summary_rounds
            if getattr(self.agent, "auto_summary_rounds", None) is not None
            else get_auto_summary_rounds()
        )

    def run(self) -> Any:
        """主运行循环（委派到传入的 agent 实例的方法与属性）"""
        run_input_handlers = True

        while True:
            try:
                self.conversation_rounds += 1
                if self.conversation_rounds % self.tool_reminder_rounds == 0:
                    self.agent.session.addon_prompt = join_prompts(
                        [self.agent.session.addon_prompt, self.agent.get_tool_usage_prompt()]
                    )
                # 基于轮次的自动总结判断：达到阈值后执行一次总结与历史清理
                if self.conversation_rounds >= self.auto_summary_rounds:
                    summary_text = self.agent._summarize_and_clear_history()
                    if summary_text:
                        # 将摘要作为下一轮的附加提示加入，从而维持上下文连续性
                        self.agent.session.addon_prompt = join_prompts(
                            [self.agent.session.addon_prompt, summary_text]
                        )
                    # 重置轮次计数与对话长度计数器，开始新一轮周期
                    self.conversation_rounds = 0
                    self.agent.session.conversation_length = 0

                ag = self.agent

                # 更新输入处理器标志
                if ag.run_input_handlers_next_turn:
                    run_input_handlers = True
                    ag.run_input_handlers_next_turn = False

                # 首次运行初始化
                if ag.first:
                    ag._first_run()

                # 调用模型获取响应
                current_response = ag._call_model(
                    ag.session.prompt, True, run_input_handlers
                )

                ag.session.prompt = ""
                run_input_handlers = False

                # 处理中断
                interrupt_result = ag._handle_run_interrupt(current_response)
                if (
                    isinstance(interrupt_result, Enum)
                    and getattr(interrupt_result, "value", None) == "skip_turn"
                ):
                    # 中断处理器请求跳过本轮剩余部分，直接开始下一次循环
                    continue
                elif interrupt_result is not None and not isinstance(interrupt_result, Enum):
                    # 中断处理器返回了最终结果，任务结束
                    return interrupt_result

                # 处理工具调用
                # 广播工具调用前事件（不影响主流程）
                try:
                    ag.event_bus.emit(
                        BEFORE_TOOL_CALL,
                        agent=ag,
                        current_response=current_response,
                    )
                except Exception:
                    pass
                need_return, tool_prompt = ag._call_tools(current_response)

                # 如果工具要求立即返回结果（例如 SEND_MESSAGE 需要将字典返回给上层），直接返回该结果
                if need_return:
                    ag._no_tool_call_count = 0
                    return tool_prompt

                # 将上一个提示和工具提示安全地拼接起来（仅当工具结果为字符串时）
                safe_tool_prompt = tool_prompt if isinstance(tool_prompt, str) else ""
                
                ag.session.prompt = join_prompts([ag.session.prompt, safe_tool_prompt])

                # 广播工具调用后的事件（不影响主流程）
                try:
                    ag.event_bus.emit(
                        AFTER_TOOL_CALL,
                        agent=ag,
                        current_response=current_response,
                        need_return=need_return,
                        tool_prompt=tool_prompt,
                    )
                except Exception:
                    pass

                # 检查是否需要继续
                if ag.session.prompt or ag.session.addon_prompt:
                    ag._no_tool_call_count = 0
                    continue

                # 检查自动完成
                if ag.auto_complete and is_auto_complete(current_response):
                    ag._no_tool_call_count = 0
                    # 先运行_complete_task，触发记忆整理/事件等副作用，再决定返回值
                    result = ag._complete_task(auto_completed=True)
                    # 若不需要summary，则将最后一条LLM输出作为返回值
                    if not getattr(ag, "need_summary", True):
                        return current_response
                    return result

                
                # 检查是否有工具调用：如果tool_prompt不为空，说明有工具被调用
                has_tool_call = bool(safe_tool_prompt and safe_tool_prompt.strip())
                
                # 在非交互模式下，跟踪连续没有工具调用的次数
                if ag.non_interactive:
                    if has_tool_call:
                        # 有工具调用，重置计数器
                        ag._no_tool_call_count = 0
                    else:
                        # 没有工具调用，增加计数器
                        ag._no_tool_call_count += 1
                        # 如果连续5次没有工具调用，添加工具使用提示
                        if ag._no_tool_call_count >= 5:
                            tool_usage_prompt = ag.get_tool_usage_prompt()
                            ag.session.addon_prompt = join_prompts(
                                [ag.session.addon_prompt, tool_usage_prompt]
                            )
                            # 重置计数器，避免重复添加
                            ag._no_tool_call_count = 0

                # 获取下一步用户输入
                next_action = ag._get_next_user_action()
                action = normalize_next_action(next_action)
                if action == "continue":
                    run_input_handlers = True
                    continue
                elif action == "complete":
                    return ag._complete_task(auto_completed=False)

            except Exception as e:
                print(f"❌ 任务失败: {str(e)}")
                return f"Task failed: {str(e)}"
