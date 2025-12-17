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
from typing import TYPE_CHECKING
from typing import Any
from typing import Optional

from rich import box
from rich.panel import Panel

from jarvis.jarvis_agent.events import AFTER_TOOL_CALL
from jarvis.jarvis_agent.events import BEFORE_TOOL_CALL
from jarvis.jarvis_agent.utils import is_auto_complete
from jarvis.jarvis_agent.utils import join_prompts
from jarvis.jarvis_agent.utils import normalize_next_action
from jarvis.jarvis_utils.config import get_conversation_turn_threshold
from jarvis.jarvis_utils.config import get_max_input_token_count
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.tag import ot

if TYPE_CHECKING:
    # 仅用于类型标注，避免运行时循环依赖
    from . import Agent


class AgentRunLoop:
    def __init__(self, agent: "Agent") -> None:
        self.agent = agent
        self.tool_reminder_rounds = int(os.environ.get("tool_reminder_rounds", 20))
        # 基于剩余token数量的自动总结阈值：当剩余token低于输入窗口的20%时触发
        max_input_tokens = get_max_input_token_count(self.agent.model_group)
        self.summary_remaining_token_threshold = int(max_input_tokens * 0.2)
        self.conversation_turn_threshold = get_conversation_turn_threshold()

        # Git diff相关属性
        self._git_diff: Optional[str] = None  # 缓存git diff内容

    def _check_can_complete_task(self) -> tuple[bool, str]:
        """检查agent是否可以完成任务（需要检查任务列表状态）

        返回:
            tuple[bool, str]: (是否可以完成, 错误信息)
        """
        try:
            # 检查agent是否有task_list_manager
            if not hasattr(self.agent, "task_list_manager"):
                return True, ""

            task_list_manager = self.agent.task_list_manager
            if not task_list_manager:
                return True, ""

            # 获取当前agent的task_list_id
            task_list_id = None
            try:
                task_list_id = self.agent.get_user_data("__task_list_id__")
            except Exception:
                return True, ""

            if not task_list_id:
                return True, ""

            # 获取任务列表
            task_list = task_list_manager.get_task_list(task_list_id)
            if not task_list:
                return True, ""

            # 检查是否有pending或running状态的任务
            pending_tasks = []
            running_tasks = []

            for task in task_list.tasks.values():
                if task.status.value == "pending":
                    pending_tasks.append(task)
                elif task.status.value == "running":
                    running_tasks.append(task)

            # 如果有未完成的任务，返回详细信息
            if pending_tasks or running_tasks:
                error_parts = []
                error_parts.append("❌ 无法完成任务：检测到任务列表中还有未完成的任务")
                error_parts.append("")

                if running_tasks:
                    error_parts.append(f"🔄 运行中的任务 ({len(running_tasks)} 个)：")
                    for task in running_tasks[:5]:  # 最多显示5个
                        error_parts.append(f"  - [{task.task_id}] {task.task_name}")
                    if len(running_tasks) > 5:
                        error_parts.append(
                            f"  ... 还有 {len(running_tasks) - 5} 个运行中的任务"
                        )
                    error_parts.append("")

                if pending_tasks:
                    error_parts.append(f"⏳ 待执行的任务 ({len(pending_tasks)} 个)：")
                    for task in pending_tasks[:5]:  # 最多显示5个
                        error_parts.append(f"  - [{task.task_id}] {task.task_name}")
                    if len(pending_tasks) > 5:
                        error_parts.append(
                            f"  ... 还有 {len(pending_tasks) - 5} 个待执行的任务"
                        )
                    error_parts.append("")

                error_parts.append("💡 建议：")
                error_parts.append("  1. 使用 task_list_manager 工具完成所有任务")
                error_parts.append("  2. 或者将不需要的任务状态更新为 abandoned")
                error_parts.append(
                    "  3. 确保所有任务都是 completed、failed 或 abandoned 状态后再完成"
                )

                error_message = "\n".join(error_parts)
                return False, error_message

            return True, ""

        except Exception as e:
            # 如果检查失败，记录警告但允许完成（避免阻塞正常流程）
            PrettyOutput.auto_print(f"⚠️ 检查任务列表状态时发生异常: {str(e)}")
            return True, ""

    def run(self) -> Any:
        """主运行循环（委派到传入的 agent 实例的方法与属性）"""
        run_input_handlers = True

        while True:
            try:
                current_round = self.agent.model.get_conversation_turn()
                if current_round % self.tool_reminder_rounds == 0:
                    self.agent.session.addon_prompt = join_prompts(
                        [
                            self.agent.session.addon_prompt,
                            self.agent.get_tool_usage_prompt(),
                        ]
                    )
                # 基于剩余token数量或对话轮次的自动总结判断
                remaining_tokens = self.agent.model.get_remaining_token_count()
                should_summarize = (
                    remaining_tokens <= self.summary_remaining_token_threshold
                    or current_round > self.conversation_turn_threshold
                )
                if should_summarize:
                    # 在总结前获取git diff（仅对CodeAgent类型）
                    try:
                        if (
                            hasattr(self.agent, "start_commit")
                            and self.agent.start_commit
                        ):
                            self._git_diff = self.get_git_diff()
                        else:
                            self._git_diff = None
                    except Exception as e:
                        PrettyOutput.auto_print(f"⚠️ 获取git diff失败: {str(e)}")
                        self._git_diff = f"获取git diff失败: {str(e)}"

                    summary_text = self.agent._summarize_and_clear_history()
                    if summary_text:
                        # 将摘要作为下一轮的附加提示加入，从而维持上下文连续性
                        self.agent.session.addon_prompt = join_prompts(
                            [self.agent.session.addon_prompt, summary_text]
                        )
                    # 重置对话长度计数器（用于摘要触发），开始新一轮周期
                    # 注意：对话轮次由模型内部管理，这里不需要重置
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

                if ot("!!!SUMMARY!!!") in current_response:
                    PrettyOutput.auto_print(
                        f"ℹ️ 检测到 {ot('!!!SUMMARY!!!')} 标记，正在触发总结并清空历史..."
                    )
                    # 移除标记，避免在后续处理中出现
                    current_response = current_response.replace(
                        ot("!!!SUMMARY!!!"), ""
                    ).strip()
                    # 在总结前获取git diff（仅对CodeAgent类型）
                    try:
                        if hasattr(ag, "start_commit") and ag.start_commit:
                            self._git_diff = self.get_git_diff()
                        else:
                            self._git_diff = None
                    except Exception as e:
                        PrettyOutput.auto_print(f"⚠️ 获取git diff失败: {str(e)}")
                        self._git_diff = f"获取git diff失败: {str(e)}"
                    # 触发总结并清空历史
                    summary_text = ag._summarize_and_clear_history()
                    if summary_text:
                        # 将摘要作为下一轮的附加提示加入，从而维持上下文连续性
                        ag.session.addon_prompt = join_prompts(
                            [ag.session.addon_prompt, summary_text]
                        )
                    # 重置对话长度计数器（用于摘要触发），开始新一轮周期
                    # 注意：对话轮次由模型内部管理，这里不需要重置
                    ag.session.conversation_length = 0
                    # 如果响应中还有其他内容，继续处理；否则继续下一轮
                    if not current_response:
                        continue

                # 处理中断
                interrupt_result = ag._handle_run_interrupt(current_response)
                if (
                    isinstance(interrupt_result, Enum)
                    and getattr(interrupt_result, "value", None) == "skip_turn"
                ):
                    # 中断处理器请求跳过本轮剩余部分，直接开始下一次循环
                    continue
                elif interrupt_result is not None and not isinstance(
                    interrupt_result, Enum
                ):
                    # 中断处理器返回了最终结果，任务结束
                    return interrupt_result

                # 处理工具调用
                # 非关键流程：广播工具调用前事件（用于日志、监控等）
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

                # 关键流程：直接调用 after_tool_call 回调函数
                try:
                    # 获取所有订阅了 AFTER_TOOL_CALL 事件的回调
                    listeners = ag.event_bus._listeners.get(AFTER_TOOL_CALL, [])
                    for listener_tuple in listeners:
                        try:
                            # listener_tuple 是 (priority, order, callback)
                            _, _, callback = listener_tuple
                            callback(
                                agent=ag,
                                current_response=current_response,
                                need_return=need_return,
                                tool_prompt=tool_prompt,
                            )
                        except Exception:
                            pass
                except Exception:
                    pass

                # 非关键流程：广播工具调用后的事件（用于日志、监控等）
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

                    # 检查是否可以完成任务（需要检查任务列表状态）
                    can_complete, error_message = self._check_can_complete_task()
                    if not can_complete:
                        # 无法完成任务，将错误信息作为提示返回给agent
                        PrettyOutput.auto_print(error_message)
                        ag.set_addon_prompt(error_message)
                        # 重置计数器，继续执行
                        ag._no_tool_call_count = 0
                        continue

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
                        # 如果连续3次没有工具调用，发送工具使用提示
                        if ag._no_tool_call_count >= 3:
                            tool_usage_prompt = ag.get_tool_usage_prompt()
                            ag.set_addon_prompt(tool_usage_prompt)
                            # 重置计数器，避免重复添加
                            ag._no_tool_call_count = 0

                # 如果没有工具调用，显示完整响应
                if not has_tool_call and current_response and current_response.strip():
                    import jarvis.jarvis_utils.globals as G
                    from jarvis.jarvis_utils.globals import console

                    agent_name = ag.name if hasattr(ag, "name") else None
                    panel = Panel(
                        current_response,
                        title=f"[bold cyan]{(G.get_current_agent_name() + ' · ') if G.get_current_agent_name() else ''}{agent_name or 'LLM'}[/bold cyan]",
                        border_style="bright_blue",
                        box=box.ROUNDED,
                        expand=True,
                    )
                    console.print(panel)

                # 获取下一步用户输入
                next_action = ag._get_next_user_action()
                action = normalize_next_action(next_action)
                if action == "continue":
                    run_input_handlers = True
                    continue
                elif action == "complete":
                    # 检查是否可以完成任务（需要检查任务列表状态）
                    can_complete, error_message = self._check_can_complete_task()
                    if not can_complete:
                        # 无法完成任务，显示错误信息并继续
                        PrettyOutput.auto_print(error_message)
                        ag.set_addon_prompt(error_message)
                        run_input_handlers = True
                        continue

                    return ag._complete_task(auto_completed=False)

            except Exception as e:
                PrettyOutput.auto_print(f"❌ 任务失败: {str(e)}")
                return f"Task failed: {str(e)}"

    def get_git_diff(self) -> str:
        """获取从起始commit到当前commit的git diff

        返回:
            str: git diff内容，如果无法获取则返回错误信息
        """
        try:
            from jarvis.jarvis_utils.git_utils import get_diff_between_commits
            from jarvis.jarvis_utils.git_utils import get_latest_commit_hash

            # 获取agent实例
            agent = self.agent

            # 检查agent是否有start_commit属性
            if not hasattr(agent, "start_commit") or not agent.start_commit:
                return "无法获取起始commit哈希值"

            start_commit = agent.start_commit
            current_commit = get_latest_commit_hash()

            if not current_commit:
                return "无法获取当前commit哈希值"

            if start_commit == current_commit:
                return (
                    "# 没有检测到代码变更\n\n起始commit和当前commit相同，没有代码变更。"
                )

            # 获取diff
            diff_content = get_diff_between_commits(start_commit, current_commit)

            # 检查并处理token数量限制
            model_group = agent.model_group
            return self._check_diff_token_limit(diff_content, model_group)

        except Exception as e:
            return f"获取git diff失败: {str(e)}"

    def get_cached_git_diff(self) -> Optional[str]:
        """获取已缓存的git diff信息

        返回:
            Optional[str]: 已缓存的git diff内容，如果尚未获取则返回None
        """
        return self._git_diff

    def has_git_diff(self) -> bool:
        """检查是否有可用的git diff信息

        返回:
            bool: 如果有可用的git diff信息返回True，否则返回False
        """
        return self._git_diff is not None and bool(self._git_diff.strip())

    def _check_diff_token_limit(
        self, diff_content: str, model_group: Optional[str]
    ) -> str:
        """检查diff内容的token限制并返回适当的diff内容

        参数:
            diff_content: 原始的diff内容
            model_group: 模型组名称，可为空

        返回:
            str: 处理后的diff内容（可能是原始内容或截断后的内容）
        """
        from jarvis.jarvis_utils.embedding import get_context_token_count

        # 检查token数量限制
        max_input_tokens = get_max_input_token_count(model_group)
        # 预留一部分token用于其他内容，使用10%作为diff的限制
        max_diff_tokens = int(max_input_tokens * 0.1)

        diff_token_count = get_context_token_count(diff_content)

        if diff_token_count <= max_diff_tokens:
            return diff_content

        # 如果diff内容太大，进行截断
        lines = diff_content.split("\n")
        truncated_lines = []
        current_tokens = 0

        for line in lines:
            line_tokens = get_context_token_count(line)
            if current_tokens + line_tokens > max_diff_tokens:
                # 添加截断提示
                truncated_lines.append("")
                truncated_lines.append("# ⚠️ diff内容过大，已截断显示")
                truncated_lines.append(
                    f"# 原始diff共 {len(lines)} 行，{diff_token_count} tokens"
                )
                truncated_lines.append(
                    f"# 显示前 {len(truncated_lines)} 行，约 {current_tokens} tokens"
                )
                break

            truncated_lines.append(line)
            current_tokens += line_tokens

        return "\n".join(truncated_lines)
