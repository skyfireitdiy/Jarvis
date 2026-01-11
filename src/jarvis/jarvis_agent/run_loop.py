# -*- coding: utf-8 -*-
"""
AgentRunLoop: 承载 Agent 的主运行循环逻辑。

阶段一目标（最小变更）：
- 复制现有 _main_loop 逻辑到独立类，使用传入的 agent 实例进行委派调用
- 暂不变更外部调用入口，后续在 Agent._main_loop 中委派到该类
- 保持与现有异常处理、工具调用、用户交互完全一致
"""

import os
import re
from enum import Enum
from typing import TYPE_CHECKING
from typing import Any
from typing import Optional


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
        # 使用模型的平台特定配置，确保阈值计算与运行时检查使用相同的配置
        max_input_tokens = self.agent.model._get_platform_max_input_token_count()
        self.summary_remaining_token_threshold = int(max_input_tokens * 0.2)
        self.conversation_turn_threshold = get_conversation_turn_threshold()

        # Git diff相关属性
        self._git_diff: Optional[str] = None  # 缓存git diff内容

    def _filter_tool_calls_from_response(self, response: str) -> str:
        """从响应中过滤掉工具调用内容

        参数:
            response: 原始响应内容

        返回:
            str: 过滤后的响应内容（不包含工具调用部分）
        """
        from jarvis.jarvis_utils.tag import ct
        from jarvis.jarvis_utils.tag import ot

        # 如果</TOOL_CALL>出现在响应的末尾，但是前面没有换行符，自动插入一个换行符进行修复（忽略大小写）
        close_tag = ct("TOOL_CALL")
        close_tag_pattern = re.escape(close_tag)
        match = re.search(rf"{close_tag_pattern}$", response.rstrip(), re.IGNORECASE)
        if match:
            pos = match.start()
            if pos > 0 and response[pos - 1] not in ("\n", "\r"):
                response = response[:pos] + "\n" + response[pos:]

        # 如果有开始标签但没有结束标签，自动补全结束标签（与registry逻辑一致）
        has_open = (
            re.search(rf"(?mi)^{re.escape(ot('TOOL_CALL'))}", response) is not None
        )
        has_close = (
            re.search(rf"(?mi)^{re.escape(ct('TOOL_CALL'))}", response) is not None
        )
        if has_open and not has_close:
            response = response.strip() + f"\n{ct('TOOL_CALL')}"

        # 使用正则表达式移除所有工具调用块
        # 匹配起始标签（ot('TOOL_CALL')）和结束标签（ct('TOOL_CALL')）
        # 结束标签必须在行首（使用 ^ 锚点）
        # 使用多行模式和DOTALL标志
        pattern = rf"{re.escape(ot('TOOL_CALL'))}(.*?){re.escape(ct('TOOL_CALL'))}"

        # 移除所有工具调用块（包括标签本身）
        # 使用DOTALL标志使 . 匹配包括换行符在内的所有字符
        filtered = re.sub(pattern, "", response, flags=re.DOTALL | re.MULTILINE)

        # 清理可能留下的多余空行（超过2个连续换行符替换为2个）
        filtered = re.sub(r"\n{3,}", "\n\n", filtered)

        return filtered.strip()

    def _handle_interrupt_with_input(self) -> Optional[str]:
        """处理中断并获取用户补充信息

        返回:
            Optional[str]: 如果用户输入了补充信息，返回格式化字符串；否则返回 None
        """
        from jarvis.jarvis_utils.input import get_multiline_input
        from jarvis.jarvis_utils.input import get_single_line_input

        try:
            user_input = get_multiline_input(
                "⚠ 检测到中断，请输入补充信息（Ctrl+J/Ctrl+]确认，直接回车跳过）",
                print_on_empty=False,
            )
            if user_input and user_input.strip():
                return f"[用户中断] 补充信息：{user_input.strip()}"
        except (KeyboardInterrupt, EOFError):
            # 用户再次中断，询问是否要完全退出
            PrettyOutput.auto_print("\n🔄 再次检测到中断，请选择操作：")
            PrettyOutput.auto_print("  1. 跳过补充信息，继续执行")
            PrettyOutput.auto_print("  2. 完全退出程序")
            try:
                choice = get_single_line_input("请输入选项（1/2，直接回车默认跳过）：")
                if choice and choice.strip() == "2":
                    raise  # 重新抛出KeyboardInterrupt，让外层处理退出
            except (KeyboardInterrupt, EOFError):
                raise  # 用户再次中断，直接退出
        return None

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
                token_limit_triggered = (
                    remaining_tokens <= self.summary_remaining_token_threshold
                )
                turn_limit_triggered = current_round > self.conversation_turn_threshold
                should_summarize = token_limit_triggered or turn_limit_triggered

                # 如果是token限制触发，打印当前token数量
                if token_limit_triggered:
                    # 使用平台内部的实际token限制，而不是全局配置（考虑cheap/smart/normal等不同模型类型）
                    max_input_tokens = (
                        self.agent.model._get_platform_max_input_token_count()
                    )
                    PrettyOutput.auto_print(
                        f"🔍 Token限制触发自动总结，当前剩余token数量: {remaining_tokens}/{max_input_tokens} (剩余 {remaining_tokens / max_input_tokens * 100:.1f}%)"
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
                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        PrettyOutput.auto_print(f"⚠️ 获取git diff失败: {str(e)}")
                        self._git_diff = f"获取git diff失败: {str(e)}"

                    # 确定触发原因
                    if token_limit_triggered and turn_limit_triggered:
                        trigger_reason = "Token和轮次双重限制触发"
                    elif token_limit_triggered:
                        trigger_reason = "Token限制触发"
                    else:
                        trigger_reason = "对话轮次限制触发"

                    summary_text = self.agent._summarize_and_clear_history(
                        trigger_reason=trigger_reason
                    )
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
                try:
                    current_response = ag._call_model(
                        ag.session.prompt, True, run_input_handlers
                    )
                except KeyboardInterrupt:
                    # 获取用户补充信息并继续下一轮
                    addon_info = self._handle_interrupt_with_input()
                    if addon_info:
                        ag.session.addon_prompt = join_prompts(
                            [ag.session.addon_prompt, addon_info]
                        )
                    continue

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
                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        PrettyOutput.auto_print(f"⚠️ 获取git diff失败: {str(e)}")
                        self._git_diff = f"获取git diff失败: {str(e)}"
                    # 触发总结并清空历史
                    summary_text = ag._summarize_and_clear_history(
                        trigger_reason="手动触发"
                    )
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

                # 打印LLM输出（过滤掉工具调用内容）
                if current_response and current_response.strip():
                    # 过滤掉 <TOOL_CALL>...</TOOL_CALL> 标签及其内容
                    filtered_response = self._filter_tool_calls_from_response(
                        current_response
                    )
                    # 只有在过滤后仍有内容时才打印
                    if filtered_response:
                        import jarvis.jarvis_utils.globals as G
                        from jarvis.jarvis_utils.globals import console
                        from rich.panel import Panel
                        from rich import box

                        agent_name = ag.name if hasattr(ag, "name") else None
                        panel = Panel(
                            filtered_response,
                            title=f"[bold cyan]{(G.get_current_agent_name() + ' · ') if G.get_current_agent_name() else ''}{agent_name or 'LLM'}[/bold cyan]",
                            border_style="bright_blue",
                            box=box.ROUNDED,
                            expand=True,
                        )
                        console.print(panel)

                try:
                    need_return, tool_prompt = ag._call_tools(current_response)
                except KeyboardInterrupt:
                    # 获取用户补充信息并继续执行
                    addon_info = self._handle_interrupt_with_input()
                    if addon_info:
                        ag.session.addon_prompt = join_prompts(
                            [ag.session.addon_prompt, addon_info]
                        )
                    need_return = False
                    tool_prompt = ""

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

                    # 检查是否有代码修改（仅对CodeAgent）
                    should_auto_complete = True
                    try:
                        if hasattr(ag, "start_commit") and ag.start_commit:
                            from jarvis.jarvis_utils.git_utils import (
                                get_latest_commit_hash,
                            )

                            current_commit = get_latest_commit_hash()
                            if current_commit and ag.start_commit == current_commit:
                                # 没有代码修改，询问LLM是否应该结束
                                no_code_mod_prompt_parts = [
                                    "检测到本次任务没有产生任何代码修改。"
                                ]
                                no_code_mod_prompt_parts.append(
                                    "\n请确认是否要完成任务（自动完成）。"
                                )
                                no_code_mod_prompt_parts.append(
                                    "如果确认完成，请回复 <!!!YES!!!>"
                                )
                                no_code_mod_prompt_parts.append(
                                    "如果要继续执行任务，请回复 <!!!NO!!!>"
                                )

                                no_code_mod_prompt = "\n".join(no_code_mod_prompt_parts)

                                # 询问 LLM
                                try:
                                    llm_response = ag._call_model(
                                        no_code_mod_prompt, False, False
                                    )
                                except KeyboardInterrupt:
                                    # 获取用户补充信息并继续主循环下一轮
                                    addon_info = self._handle_interrupt_with_input()
                                    if addon_info:
                                        ag.session.addon_prompt = join_prompts(
                                            [ag.session.addon_prompt, addon_info]
                                        )
                                    should_auto_complete = False
                                    continue

                                # 解析响应
                                if "<!!!NO!!!>" in llm_response:
                                    should_auto_complete = False
                                    ag.set_addon_prompt(
                                        "本次任务没有代码修改，但LLM选择继续执行。"
                                    )
                                    PrettyOutput.auto_print(
                                        "📝 未检测到代码修改，将继续执行任务。"
                                    )
                                elif "<!!!YES!!!>" in llm_response:
                                    should_auto_complete = True
                                    PrettyOutput.auto_print(
                                        "✅ 确认完成当前任务，即使没有代码修改。"
                                    )
                                else:
                                    # 无法明确判断，默认不完成（安全优先）
                                    should_auto_complete = False
                                    ag.set_addon_prompt(
                                        "本次任务没有代码修改，请继续执行任务。"
                                    )
                                    PrettyOutput.auto_print(
                                        "⚠️ 未收到明确的完成确认，将继续执行任务。"
                                    )
                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        # 检查过程出错，默认继续原有流程
                        PrettyOutput.auto_print(
                            f"⚠️ 检查代码修改时出错: {str(e)}，继续原有流程。"
                        )
                        should_auto_complete = True

                    if should_auto_complete:
                        # 检查是否有未完成的任务
                        should_auto_complete = True
                        all_unfinished_tasks = []
                        try:
                            if (
                                hasattr(ag, "task_list_manager")
                                and ag.task_list_manager.task_lists
                            ):
                                for (
                                    task_list_id,
                                    task_list,
                                ) in ag.task_list_manager.task_lists.items():
                                    summary = (
                                        ag.task_list_manager.get_task_list_summary(
                                            task_list_id
                                        )
                                    )
                                    if summary:
                                        for task in summary.get("tasks", []):
                                            if task.get("status") in [
                                                "pending",
                                                "running",
                                            ]:
                                                all_unfinished_tasks.append(
                                                    {
                                                        "task_id": task.get("task_id"),
                                                        "task_name": task.get(
                                                            "task_name"
                                                        ),
                                                        "task_desc": task.get(
                                                            "task_desc", ""
                                                        )[:100]
                                                        + "..."
                                                        if len(
                                                            task.get("task_desc", "")
                                                        )
                                                        > 100
                                                        else task.get("task_desc", ""),
                                                        "status": task.get("status"),
                                                        "task_list_id": task_list_id,
                                                        "main_goal": summary.get(
                                                            "main_goal", ""
                                                        ),
                                                    }
                                                )

                            if all_unfinished_tasks:
                                # 构造任务提示
                                task_prompt_parts = [
                                    "检测到以下任务列表中还有未完成的任务：\n"
                                ]
                                for task_list_info in set(
                                    (t["task_list_id"], t["main_goal"])
                                    for t in all_unfinished_tasks
                                ):
                                    task_prompt_parts.append(
                                        f"任务列表 ID: {task_list_info[0]}"
                                    )
                                    task_prompt_parts.append(
                                        f"主目标: {task_list_info[1]}\n"
                                    )
                                    task_prompt_parts.append("未完成任务列表：")
                                    for task in [
                                        t
                                        for t in all_unfinished_tasks
                                        if t["task_list_id"] == task_list_info[0]
                                    ]:
                                        task_prompt_parts.append(
                                            f"  - 任务ID: {task['task_id']} | 名称: {task['task_name']} | 状态: {task['status']}"
                                        )
                                        task_prompt_parts.append(
                                            f"    描述: {task['task_desc']}"
                                        )

                                task_prompt_parts.append(
                                    "\n请确认是否要完成当前任务（自动完成）。"
                                )
                                task_prompt_parts.append(
                                    "如果确认完成，请回复 <!!!YES!!!>"
                                )
                                task_prompt_parts.append(
                                    "如果要继续执行上述未完成的任务，请回复 <!!!NO!!!>"
                                )

                                task_prompt = "\n".join(task_prompt_parts)

                                # 询问 LLM
                                try:
                                    llm_response = ag._call_model(
                                        task_prompt, False, False
                                    )
                                except KeyboardInterrupt:
                                    # 获取用户补充信息并继续主循环下一轮
                                    addon_info = self._handle_interrupt_with_input()
                                    if addon_info:
                                        ag.session.addon_prompt = join_prompts(
                                            [ag.session.addon_prompt, addon_info]
                                        )
                                    should_auto_complete = False
                                    continue

                                # 解析响应
                                if "<!!!NO!!!>" in llm_response:
                                    should_auto_complete = False
                                    ag.set_addon_prompt(
                                        "请继续执行未完成的任务列表中的任务。"
                                    )
                                    PrettyOutput.auto_print(
                                        "📋 检测到未完成任务，将继续执行任务列表。"
                                    )
                                elif "<!!!YES!!!>" in llm_response:
                                    should_auto_complete = True
                                    PrettyOutput.auto_print(
                                        "✅ 确认完成当前任务，忽略任务列表中的未完成任务。"
                                    )
                                else:
                                    # 无法明确判断，默认不完成（安全优先）
                                    should_auto_complete = False
                                    ag.set_addon_prompt(
                                        "请继续执行未完成的任务列表中的任务。"
                                    )
                                    PrettyOutput.auto_print(
                                        "⚠️ 未收到明确的完成确认，将继续执行任务列表。"
                                    )
                        except KeyboardInterrupt:
                            raise
                        except Exception as e:
                            # 检查过程出错，默认继续自动完成
                            PrettyOutput.auto_print(
                                f"⚠️ 检查任务列表时出错: {str(e)}，继续自动完成。"
                            )
                            should_auto_complete = True

                    if should_auto_complete:
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
                        # 如果连续5次没有工具调用，尝试使用大模型修复
                        if ag._no_tool_call_count >= 5:
                            from jarvis.jarvis_agent.utils import fix_tool_call_with_llm

                            error_msg = (
                                "连续5次对话没有工具调用，请使用工具来完成你的任务"
                            )
                            PrettyOutput.auto_print(f"⚠️ {error_msg}")

                            # 尝试使用大模型修复
                            fixed_content = fix_tool_call_with_llm(
                                current_response, ag, error_msg
                            )

                            if fixed_content:
                                # 修复成功，将修复后的内容加入prompt
                                ag.session.addon_prompt = join_prompts(
                                    [ag.session.addon_prompt, fixed_content]
                                )
                            else:
                                # 修复失败，发送工具使用提示
                                tool_usage_prompt = ag.get_tool_usage_prompt()
                                ag.set_addon_prompt(tool_usage_prompt)

                            # 重置计数器，避免重复添加
                            ag._no_tool_call_count = 0

                # 获取下一步用户输入
                try:
                    next_action = ag._get_next_user_action()
                except KeyboardInterrupt:
                    # 获取用户补充信息并继续下一轮
                    addon_info = self._handle_interrupt_with_input()
                    if addon_info:
                        ag.session.addon_prompt = join_prompts(
                            [ag.session.addon_prompt, addon_info]
                        )
                    continue
                action = normalize_next_action(next_action)
                if action == "continue":
                    run_input_handlers = True
                    continue
                elif action == "complete":
                    return ag._complete_task(auto_completed=False)

            except KeyboardInterrupt:
                # 获取用户补充信息并继续执行
                addon_info = self._handle_interrupt_with_input()
                if addon_info:
                    ag.session.addon_prompt = join_prompts(
                        [ag.session.addon_prompt, addon_info]
                    )
                continue
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
