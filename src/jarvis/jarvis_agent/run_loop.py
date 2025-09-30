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

from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_agent.events import BEFORE_TOOL_CALL, AFTER_TOOL_CALL
from jarvis.jarvis_agent.utils import join_prompts, is_auto_complete, normalize_next_action

if TYPE_CHECKING:
    # 仅用于类型标注，避免运行时循环依赖
    from . import Agent  # noqa: F401


class AgentRunLoop:
    def __init__(self, agent: "Agent") -> None:
        self.agent = agent
        self.conversation_rounds = 0
        self.tool_reminder_rounds = int(os.environ.get("JARVIS_TOOL_REMINDER_ROUNDS", 20))

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

                # 将上一个提示和工具提示安全地拼接起来
                ag.session.prompt = join_prompts([ag.session.prompt, tool_prompt])

                if need_return:
                    return ag.session.prompt


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
                    continue

                # 检查自动完成
                if ag.auto_complete and is_auto_complete(current_response):
                    return ag._complete_task(auto_completed=True)

                # 获取下一步用户输入
                next_action = ag._get_next_user_action()
                action = normalize_next_action(next_action)
                if action == "continue":
                    run_input_handlers = True
                    continue
                elif action == "complete":
                    return ag._complete_task(auto_completed=False)

            except Exception as e:
                PrettyOutput.print(f"任务失败: {str(e)}", OutputType.ERROR)
                return f"Task failed: {str(e)}"
