# -*- coding: utf-8 -*-
"""历史摘要/压缩职责模块

从 Agent 类中抽离的「历史摘要/压缩」职责簇。

设计说明：
- 遵循 jarvis_agent 包既有拆分范式（如 MemoryManager(self)、AgentRunLoop(agent)）：
  本模块持有 agent 引用，方法体内通过 self.agent.xxx 访问 Agent 的其它能力。
- Agent 侧保留同名薄委托方法，保证对外接口（含 run_loop / code_agent 的反向调用）完全不变。
- 循环依赖通过 TYPE_CHECKING 处理。
"""

from typing import TYPE_CHECKING
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from jarvis.jarvis_agent.events import AFTER_HISTORY_CLEAR
from jarvis.jarvis_agent.events import BEFORE_HISTORY_CLEAR
from jarvis.jarvis_agent.prompts import DEFAULT_SUMMARY_PROMPT
from jarvis.jarvis_agent.prompts import SUMMARY_REQUEST_PROMPT
from jarvis.jarvis_utils.exception_utils import save_exception
from jarvis.jarvis_utils.output import PrettyOutput

if TYPE_CHECKING:
    from jarvis.jarvis_agent import Agent


class HistoryCompressor:
    """历史摘要/压缩职责实现

    所有方法等价于原先 Agent 类上的同名方法，仅把 self.xxx 改为 self.agent.xxx。
    """

    def __init__(self, agent: "Agent") -> None:
        self.agent = agent
        # 摘要触发原因：原为 Agent 实例属性，随本簇迁入此处
        # （本对象与 Agent 一一对应，行为等价）
        self._summary_trigger_reason = "Token限制触发"

    def validate_summary(self, summary: str) -> tuple[bool, list[str]]:
        """检查摘要是否可接受。

        仅做基础长度检查，不再强制命中固定关键词，避免无谓的重写循环与额外推理成本。

        返回:
            tuple[bool, list[str]]: (是否通过, 问题列表)。仅当内容过短或为空时判定失败。
        """
        if not summary:
            return False, ["总结内容为空"]
        if len(summary.strip()) < 20:
            return False, ["总结内容过短"]
        return True, []

    def generate_summary(self, for_token_limit: bool = False) -> str:
        """生成对话历史摘要

        参数:
            for_token_limit: 如果为True，表示由于token限制触发的summary，使用SUMMARY_REQUEST_PROMPT
                            如果为False，表示任务完成时的summary，使用用户传入的summary_prompt

        返回:
            str: 包含对话摘要的字符串

        注意:
            仅生成摘要，不修改对话状态
        """

        try:
            if not self.agent.model:
                raise RuntimeError("Model not initialized")

            if for_token_limit:
                PrettyOutput.auto_print(
                    "🔍 开始生成对话历史摘要... (原因: Token限制触发)"
                )
            else:
                PrettyOutput.auto_print(
                    "🔍 开始生成对话历史摘要... (原因: 任务完成触发)"
                )

            if for_token_limit:
                # token限制触发的summary：使用SUMMARY_REQUEST_PROMPT进行上下文压缩
                # 对于多模态内容，只提取文本部分进行总结
                if isinstance(self.agent.session.prompt, list):
                    text_parts = [
                        b.get("text", "")
                        for b in self.agent.session.prompt
                        if b.get("type") == "text"
                    ]
                    prompt_text = "\n".join(text_parts)
                else:
                    prompt_text = self.agent.session.prompt
                prompt_to_use = prompt_text + "\n" + SUMMARY_REQUEST_PROMPT
            else:
                # 任务完成时的summary：使用用户传入的summary_prompt或DEFAULT_SUMMARY_PROMPT
                safe_summary_prompt = self.agent.summary_prompt or ""
                if (
                    isinstance(safe_summary_prompt, str)
                    and safe_summary_prompt.strip() != ""
                ):
                    prompt_to_use = safe_summary_prompt
                else:
                    prompt_to_use = DEFAULT_SUMMARY_PROMPT

            # 如果是CodeAgent且有start_commit，在prompt中追加提示，只总结该commit之后的目标
            if hasattr(self.agent, "start_commit") and self.agent.start_commit:
                start_commit_hint = (
                    f"\n\n<start_commit_context>\n"
                    f"本次任务之初始 Git Commit 为：`{self.agent.start_commit}`\n"
                    f"请仅总结该 commit 之后的任务目标、变更与进展，"
                    f"无需总结该 commit 之前的历史内容。\n"
                    f"</start_commit_context>"
                )
                prompt_to_use += start_commit_hint

            # 生成总结，最多重试 2 次
            max_retries = 2
            retry_count = 0
            summary = ""

            while retry_count <= max_retries:
                summary = self.agent.model.chat_until_success(prompt_to_use)
                # 防御：可能返回空响应 (None 或空字符串)，统一为空字符串并告警
                if not summary:
                    try:
                        PrettyOutput.auto_print("⚠️  模型返回空响应")
                    except Exception as e:
                        save_exception(
                            e,
                            module="jarvis_agent.__init__",
                            function="generate_summary",
                        )
                        pass
                    summary = ""
                    break  # 空响应不重试

                # 仅在 token 限制触发的总结时做基础长度校验
                if for_token_limit and retry_count < max_retries:
                    if not self.validate_summary(summary)[0]:
                        retry_count += 1
                        PrettyOutput.auto_print(
                            f"⚠️  总结为空或过短，第{retry_count}次重试"
                        )
                        continue  # 重新生成

                # 验证通过或达到最大重试次数，退出循环
                break

            if summary:
                # 使用 Rich Panel 打印总结内容
                try:
                    import jarvis.jarvis_utils.globals as G

                    title = f"[bold cyan]{(G.get_current_agent_name() + ' · ') if G.get_current_agent_name() else ''}{self.agent.model.model_name or 'LLM'} 对话总结[/bold cyan]"
                    PrettyOutput.print_markdown(
                        summary, title=title, border_style="cyan"
                    )
                except Exception:
                    # 如果 Rich Panel 打印失败，使用普通方式打印总结
                    try:
                        PrettyOutput.auto_print(f"📋 对话总结:\n{summary}")
                    except Exception:
                        # 如果普通打印也失败，至少打印一个提示
                        PrettyOutput.auto_print("⚠️  总结内容打印失败")
                        PrettyOutput.auto_print(
                            f"📋 总结内容（前 500 字符）: {summary[:500]}..."
                        )
            return summary
        except KeyboardInterrupt:
            raise  # 中断信号直接向上传播
        except Exception:
            # 检查是否为中断导致的异常
            from jarvis.jarvis_utils.utils import get_interrupt

            if get_interrupt() > 0:
                raise KeyboardInterrupt("用户中断")
            PrettyOutput.auto_print("❌ 总结对话历史失败")
            return ""

    def print_compression_summary(self, summary: str, compression_type: str) -> None:
        """使用 Panel 打印压缩摘要

        参数:
            summary: 压缩后的摘要内容
            compression_type: 压缩类型（如"滑动窗口压缩"、"重要性评分压缩"等）
        """
        try:
            import jarvis.jarvis_utils.globals as G

            title = f"[bold cyan]{(G.get_current_agent_name() + ' · ') if G.get_current_agent_name() else ''}{self.agent.model.model_name or 'LLM'} {compression_type}摘要[/bold cyan]"
            PrettyOutput.print_markdown(summary, title=title, border_style="cyan")
        except Exception:
            # 如果格式化输出失败，回退到简单打印
            PrettyOutput.auto_print(f"📋 {compression_type}摘要:\n{summary}")

    def sliding_window_compression(self, window_size: Optional[int] = None) -> bool:
        """滑动窗口压缩：保留最近的用户/工具消息2条和助手消息3条，压缩更早的对话

        参数:
            window_size: 滑动窗口大小（保留的消息总数，默认5条：用户/工具2条+助手3条），如果为None则使用配置值

        返回:
            bool: 如果成功执行压缩返回True，否则返回False

        注意:
            - 只压缩用户和助手消息，系统消息始终保留
            - 保留最近的用户/工具消息2条和助手消息3条（共5条，奇数以避免连续的同role消息）
            - 如果消息数量不足，不执行压缩
            - 压缩后的历史摘要会作为一条用户消息插入到历史中
        """
        from jarvis.jarvis_utils.config import get_sliding_window_size

        if window_size is None:
            window_size = get_sliding_window_size()

        # 用户/工具消息和助手消息保留奇数条（避免连续的同role消息）
        # 保留用户/工具消息2条，助手消息3条，共5条（奇数）
        # 注：实际保留数量由 window_size 参数控制

        try:
            # 获取对话历史
            history = self.agent.model.get_messages()
            if not history:
                return False

            # 找到系统消息的结束位置（系统消息通常在开头，需要保留）
            system_end_idx = 0
            for i, msg in enumerate(history):
                if msg.get("role", "").lower() != "system":
                    system_end_idx = i
                    break
            else:
                # 如果所有消息都是系统消息，无法压缩
                return False

            # 系统消息（需要保留）
            system_messages = history[:system_end_idx]
            # 非系统消息（需要压缩的部分）
            non_system_messages = history[system_end_idx:]

            # 只对非系统消息进行窗口压缩
            if len(non_system_messages) < window_size:
                return False

            # 截取最后window_size条非系统消息
            recent_messages = non_system_messages[-window_size:]

            # 如果非系统消息数量不足窗口大小的2倍，不需要压缩
            # （需要至少2倍，因为压缩后还需要保留窗口）
            if len(non_system_messages) <= window_size * 2:
                return False

            # 分离更早的非系统消息（不在保留列表中的消息）
            # 多截取一条，是因为 s u a u a u a u a u a u a
            old_messages = non_system_messages[: -window_size + 1]

            if not old_messages:
                return False

            # 压缩更早的消息
            try:
                # 创建临时模型，使用与当前会话相同的模型
                # （不传入系统提示词，因为会通过 set_messages 设置）
                temp_model = self.agent._create_temp_model()

                # 使用 set_messages 设置对话历史，包含系统消息和需要压缩的旧消息
                messages_to_set = system_messages + old_messages
                temp_model.set_messages(messages_to_set)

                # 使用 SUMMARY_REQUEST_PROMPT 进行压缩（避免污染当前对话）
                # 仅当摘要为空/过短时做有限重试，超限放弃本次压缩
                MAX_COMPRESS_RETRIES = 3
                compressed_summary = ""
                for retry_count in range(MAX_COMPRESS_RETRIES):
                    if retry_count == 0:
                        compressed_summary = temp_model.chat_until_success(
                            SUMMARY_REQUEST_PROMPT
                        )
                    else:
                        compressed_summary = temp_model.chat_until_success(
                            "上一条摘要为空或过短，请依据上述对话历史重新生成一份完整、可继续执行的摘要。"
                        )

                    if not compressed_summary or not compressed_summary.strip():
                        PrettyOutput.auto_print("⚠滑动窗口压缩：生成摘要失败，跳过压缩")
                        return False

                    # 仅做基础长度校验：通过即退出
                    if self.validate_summary(compressed_summary.strip())[0]:
                        break
                else:
                    PrettyOutput.auto_print(
                        f"⚠滑动窗口压缩：摘要过短已达最大重试次数({MAX_COMPRESS_RETRIES})，放弃本次压缩"
                    )
                    return False

                # 打印压缩摘要
                self.print_compression_summary(
                    compressed_summary.strip(), "滑动窗口压缩"
                )

                # 格式化压缩摘要，添加Pin、记忆、Git diff等额外信息
                formatted_summary = self.format_compressed_summary(
                    compressed_summary.strip()
                )

                # 构建压缩后的消息（作为用户消息插入）
                compressed_msg = {
                    "role": "user",
                    "content": formatted_summary,
                }

                # 重建消息列表：系统消息 + 压缩摘要 + 最近的非系统消息
                new_history = system_messages + [compressed_msg] + recent_messages

                # 更新模型的消息历史，使用 set_messages 方法确保正确更新 conversation_turn
                if hasattr(self.agent.model, "set_messages"):
                    self.agent.model.set_messages(new_history)
                    # 清理预压缩状态（防止残留过期状态影响后续压缩）
                    self.agent._pre_compressed_summary = None
                    self.agent._pre_compress_snapshot_count = 0
                    self.agent._pre_compressing = False
                    # 统计保留的消息类型
                    user_tool_count_kept = sum(
                        1
                        for msg in recent_messages
                        if msg.get("role", "").lower() in ["user", "tool"]
                    )
                    assistant_count_kept = sum(
                        1
                        for msg in recent_messages
                        if msg.get("role", "").lower() == "assistant"
                    )
                    PrettyOutput.auto_print(
                        f"✅ 滑动窗口压缩完成：压缩了 {len(old_messages)} 条消息，"
                        f"保留了最近 {user_tool_count_kept} 条用户/工具消息和 {assistant_count_kept} 条助手消息（共 {len(recent_messages)} 条）"
                    )
                    return True
                else:
                    # 模型不支持 set_messages 方法，压缩失败
                    return False

            except Exception as e:
                PrettyOutput.auto_print(
                    f"⚠️ 滑动窗口压缩失败: {str(e)}，将回退到完整摘要压缩"
                )
                return False

        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 滑动窗口压缩出错: {str(e)}")
            return False

    def start_background_pre_compression(self) -> None:
        """启动后台预压缩：在75%阈值时提前生成摘要，90%真正触发时直接使用。

        该方法快照当前消息，创建临时模型（静默模式），在后台线程中生成摘要。
        完成后将格式化摘要存入 _pre_compressed_summary，供真正压缩时使用。
        """
        import threading

        # 如果已在压缩中或已有预压缩结果，不重复启动
        if self.agent._pre_compressing or self.agent._pre_compressed_summary:
            return

        try:
            # 获取对话历史
            history = self.agent.model.get_messages()
            if not history:
                return

            # 找到系统消息的结束位置
            system_end_idx = 0
            for i, msg in enumerate(history):
                if msg.get("role", "").lower() != "system":
                    system_end_idx = i
                    break
            else:
                return  # 所有消息都是系统消息，无法压缩

            # 快照消息
            system_messages = history[:system_end_idx]
            non_system_messages = history[system_end_idx:]

            # 使用与 _sliding_window_compression 相同的窗口大小
            from jarvis.jarvis_utils.config import get_sliding_window_size

            window_size = get_sliding_window_size()

            # 如果非系统消息数量不足，不需要预压缩
            if len(non_system_messages) < window_size * 2:
                return
            # 分离需要压缩的部分（窗口大小之前的消息）
            old_messages = non_system_messages[: -window_size + 1]

            if not old_messages:
                return

            # 记录快照消息数量
            self.agent._pre_compress_snapshot_count = len(history)
            self.agent._pre_compressing = True

            def _background_compress() -> None:
                """后台线程执行压缩摘要生成"""
                try:
                    # 创建临时模型，静默模式
                    temp_model = self.agent._create_temp_model()
                    temp_model.set_suppress_output(True)

                    # 使用 set_messages 设置对话历史
                    messages_to_set = system_messages + old_messages
                    temp_model.set_messages(messages_to_set)

                    # 使用 SUMMARY_REQUEST_PROMPT 生成摘要
                    compressed_summary = temp_model.chat_until_success(
                        SUMMARY_REQUEST_PROMPT
                    )

                    if not compressed_summary or not compressed_summary.strip():
                        self.agent._pre_compressing = False
                        return

                    # 仅当摘要为空/过短时有限重试（无旧关键词补充模式）
                    for retry_count in range(3):
                        if retry_count > 0:
                            compressed_summary = temp_model.chat_until_success(
                                "上一条摘要为空或过短，请依据上述对话历史重新生成一份完整、可继续执行的摘要。"
                            )
                        if not compressed_summary or not compressed_summary.strip():
                            break
                        if self.validate_summary(compressed_summary.strip())[0]:
                            break

                    if not compressed_summary or not compressed_summary.strip():
                        self.agent._pre_compressing = False
                        return

                    # 格式化压缩摘要（静默，不打印）
                    formatted_summary = self.format_compressed_summary(
                        compressed_summary.strip()
                    )

                    # 存储预压缩结果前检查是否已被外部取消（如前台已自行压缩）
                    if self.agent._pre_compressing:
                        self.agent._pre_compressed_summary = formatted_summary
                except Exception:
                    pass
                finally:
                    self.agent._pre_compressing = False

            # 启动后台线程
            thread = threading.Thread(
                target=_background_compress,
                name="background-pre-compression",
                daemon=True,
            )
            thread.start()

        except Exception:
            # 预压缩失败不影响主流程
            self.agent._pre_compressing = False

    def check_and_use_pre_compressed_summary(self) -> bool:
        """检查并使用预压缩摘要重建会话。

        当90%真正触发压缩时调用此方法。若预压缩已完成，直接使用预生成摘要重建消息历史；
        若仍在压缩中，等待其完成后再使用。

        返回:
            bool: 如果成功使用预压缩摘要重建会话返回True，否则返回False
        """
        try:
            # 如果正在预压缩，等待完成（最多等待60秒）
            if self.agent._pre_compressing:
                import time

                wait_count = 0
                while self.agent._pre_compressing and wait_count < 120:  # 最多等60秒
                    time.sleep(0.5)
                    wait_count += 1

            # 检查是否有预压缩结果
            if not self.agent._pre_compressed_summary:
                # 清理预压缩状态（可能等待超时或后台压缩失败）
                self.agent._pre_compressed_summary = None
                self.agent._pre_compress_snapshot_count = 0
                self.agent._pre_compressing = False
                return False

            # 获取当前消息
            history = self.agent.model.get_messages()
            if not history:
                # 清理预压缩状态
                self.agent._pre_compressed_summary = None
                self.agent._pre_compress_snapshot_count = 0
                self.agent._pre_compressing = False
                return False

            # 找到系统消息的结束位置
            system_end_idx = 0
            for i, msg in enumerate(history):
                if msg.get("role", "").lower() != "system":
                    system_end_idx = i
                    break
            else:
                # 清理预压缩状态
                self.agent._pre_compressed_summary = None
                self.agent._pre_compress_snapshot_count = 0
                self.agent._pre_compressing = False
                return False

            system_messages = history[:system_end_idx]
            non_system_messages = history[system_end_idx:]

            # 使用与 _sliding_window_compression 相同的窗口大小
            from jarvis.jarvis_utils.config import get_sliding_window_size

            window_size = get_sliding_window_size()

            # 根据快照点划分消息：
            # 快照时记录的消息数量之前的非系统消息为"已压缩部分"（由预压缩摘要覆盖），
            # 快照之后新增的消息应保留为 recent_messages
            if self.agent._pre_compress_snapshot_count > 0:
                # 快照点 = 系统消息数 + 快照时非系统消息数
                snapshot_non_system_count = max(
                    0, self.agent._pre_compress_snapshot_count - system_end_idx
                )
                # 快照点之后新增的非系统消息
                recent_messages = non_system_messages[snapshot_non_system_count:]
                # 若快照后无新增消息，则保留最后 window_size 条作为上下文衔接
                if not recent_messages:
                    recent_messages = non_system_messages[-window_size:]
            else:
                # 无快照记录时，回退到滑动窗口逻辑
                recent_messages = non_system_messages[-window_size:]

            # 构建压缩后的消息
            compressed_msg = {
                "role": "user",
                "content": self.agent._pre_compressed_summary,
            }

            # 重建消息列表：系统消息 + 压缩摘要 + 快照后新增的消息
            new_history = system_messages + [compressed_msg] + recent_messages

            # 更新模型的消息历史
            if hasattr(self.agent.model, "set_messages"):
                self.agent.model.set_messages(new_history)
                # 清理预压缩状态
                self.agent._pre_compressed_summary = None
                self.agent._pre_compress_snapshot_count = 0
                self.agent._pre_compressing = False
                return True

            # 模型不支持 set_messages，清理预压缩状态
            self.agent._pre_compressed_summary = None
            self.agent._pre_compress_snapshot_count = 0
            self.agent._pre_compressing = False
            return False

        except Exception:
            # 异常时清理预压缩状态，避免残留过期状态
            self.agent._pre_compressed_summary = None
            self.agent._pre_compress_snapshot_count = 0
            self.agent._pre_compressing = False
            return False

    def format_compressed_summary(self, compressed_summary: str) -> str:
        """格式化压缩后的摘要，添加Pin、记忆、Git diff等额外信息

        参数:
            compressed_summary: 压缩后的摘要内容

        返回:
            str: 格式化后的完整摘要内容
        """
        formatted_summary = f"[历史摘要] {compressed_summary}"

        # 添加用户固定的重要内容
        user_fixed_content = []

        # 添加用户通过 <Pin> 标记固定的重要内容
        if self.agent.pin_content.strip():
            user_fixed_content.append(
                f"**用户固定内容**：\n{self.agent.pin_content.strip()}"
            )

        # 添加最近的记忆
        if hasattr(self.agent, "recent_memories") and self.agent.recent_memories:
            user_fixed_content.append(
                f"**最近记忆**：\n{chr(10).join(self.agent.recent_memories)}"
            )

        # 如果有任何固定内容，添加到摘要中（放在最前面，确保优先级）
        if user_fixed_content:
            pin_section = f"\n\n## 🎯 用户的原始需求和要求（必须始终牢记）\n{chr(10).join(user_fixed_content)}"
            formatted_summary = pin_section + "\n\n" + formatted_summary

        # 获取git diff统计信息
        git_diff_stat = ""
        git_view_command = ""
        try:
            from jarvis.jarvis_agent.run_loop import AgentRunLoop

            if hasattr(self.agent, "_agent_run_loop") and isinstance(
                self.agent._agent_run_loop, AgentRunLoop
            ):
                agent_run_loop = self.agent._agent_run_loop
                # 获取diff统计信息
                git_diff_stat = agent_run_loop.get_git_diff_stat()

                # 生成查看命令
                if hasattr(self.agent, "start_commit") and self.agent.start_commit:
                    git_view_command = f"git diff {self.agent.start_commit}..HEAD"
            # 若 _agent_run_loop 不存在（如后台线程中），跳过 git diff 统计
        except Exception:
            # 非关键流程，失败时不影响主要功能
            pass

        # 添加git diff统计信息到摘要中 - 只显示有效的代码变更统计
        is_valid_git_stat = (
            git_diff_stat
            and git_diff_stat.strip()
            and not git_diff_stat.startswith("获取git diff统计失败")
            and "没有检测到代码变更" not in git_diff_stat
        )

        if is_valid_git_stat:
            diff_section = f"\n\n## 代码变更统计\n```\n{git_diff_stat}\n```"
            if git_view_command:
                diff_section += f"\n\n查看完整差异：```bash\n{git_view_command}\n```"
            formatted_summary += diff_section

        # 获取任务列表信息
        task_list_info = ""
        try:
            # 获取所有任务列表的摘要信息
            task_lists_summary: List[Dict[str, Any]] = []
            for (
                task_list_id,
                task_list,
            ) in self.agent.task_list_manager.task_lists.items():
                summary_dict = self.agent.task_list_manager.get_task_list_summary(
                    task_list_id
                )
                if summary_dict and isinstance(summary_dict, dict):
                    task_lists_summary.append(summary_dict)

            if task_lists_summary:
                task_list_info = "\n\n## 任务列表状态\n"
                for summary_dict in task_lists_summary:
                    task_list_info += (
                        f"\n- 目标: {summary_dict.get('main_goal', '未知')}"
                    )
                    task_list_info += (
                        f"\n- 总任务数: {summary_dict.get('total_tasks', 0)}"
                    )
                    task_list_info += f"\n- 待执行: {summary_dict.get('pending', 0)}"
                    task_list_info += f"\n- 执行中: {summary_dict.get('running', 0)}"
                    task_list_info += f"\n- 已完成: {summary_dict.get('completed', 0)}"
                    task_list_info += f"\n- 失败: {summary_dict.get('failed', 0)}"
                    task_list_info += (
                        f"\n- 已放弃: {summary_dict.get('abandoned', 0)}\n"
                    )
        except Exception:
            # 非关键流程，失败时不影响主要功能
            pass

        # 将任务列表信息添加到摘要中
        if task_list_info:
            formatted_summary += task_list_info

        # 获取初始 commit 信息（仅对 CodeAgent）
        initial_commit_info = ""
        try:
            if hasattr(self.agent, "start_commit") and self.agent.start_commit:
                initial_commit_info = f"\n\n**🔖 初始 Git Commit（安全回退点）**：\n本次任务开始时的初始 commit 是：`{self.agent.start_commit}`\n\n**⚠️ 重要提示**：如果文件被破坏得很严重无法恢复，可以使用以下命令重置到这个初始 commit：\n```bash\ngit reset --hard {self.agent.start_commit}\n```\n这将丢弃所有未提交的更改，将工作区恢复到任务开始时的状态。请谨慎使用此命令，确保这是你真正想要的操作。"
        except Exception:
            # 非关键流程，失败时不影响主要功能
            pass

        if initial_commit_info:
            formatted_summary += initial_commit_info

        return formatted_summary

    def adaptive_compression(self) -> bool:
        """自适应压缩：使用滑动窗口压缩策略

        返回:
            bool: 如果成功执行压缩返回True，否则返回False
        """
        try:
            # 先尝试使用预压缩摘要（后台预压缩在75%时已启动）
            if self.agent._check_and_use_pre_compressed_summary():
                PrettyOutput.auto_print("✅ 使用后台预压缩摘要完成上下文压缩")
                return True

            # 预压缩不可用（等待超时或后台压缩失败），清理预压缩状态后回退到滑动窗口压缩
            self.agent._pre_compressed_summary = None
            self.agent._pre_compress_snapshot_count = 0
            self.agent._pre_compressing = False
            return self.agent._sliding_window_compression()
        except Exception:
            # 异常时清理预压缩状态，避免残留过期状态
            self.agent._pre_compressed_summary = None
            self.agent._pre_compress_snapshot_count = 0
            self.agent._pre_compressing = False
            PrettyOutput.auto_print("⚠ 自适应压缩失败，回退到滑动窗口压缩")
            return False

    def summarize_and_clear_history(self, trigger_reason: str = "Token限制触发") -> str:
        """总结当前对话并清理历史记录

        该方法将:
        1. 提示用户保存重要记忆
        2. 调用 generate_summary 生成摘要
        3. 清除对话历史
        4. 保留系统消息
        5. 添加摘要作为新上下文
        6. 重置对话长度计数器

        参数:
            trigger_reason: 触发摘要的原因

        返回:
            str: 包含对话摘要的字符串

        注意:
            当上下文长度超过最大值时使用
        """
        # 保存触发原因到实例变量，供后续方法使用
        self._summary_trigger_reason = trigger_reason

        # 不再支持文件上传，直接使用摘要方式处理历史
        return self.handle_history_with_summary()

    def handle_history_with_summary(self) -> str:
        """使用摘要方式处理历史"""
        # 使用保存的触发原因
        trigger_reason = self._summary_trigger_reason
        # 根据触发原因决定是否为token限制触发
        is_for_token_limit = trigger_reason in [
            "Token限制触发",
            "对话轮次限制触发",
            "其他限制触发",
        ]
        summary = self.generate_summary(for_token_limit=is_for_token_limit)

        # 获取git diff统计信息
        git_diff_stat = ""
        git_view_command = ""
        try:
            from jarvis.jarvis_agent.run_loop import AgentRunLoop

            if hasattr(self.agent, "_agent_run_loop") and isinstance(
                self.agent._agent_run_loop, AgentRunLoop
            ):
                agent_run_loop = self.agent._agent_run_loop
            else:
                # 创建临时 AgentRunLoop 实例来获取 git diff
                agent_run_loop = AgentRunLoop(self.agent)

            # 获取diff统计信息
            git_diff_stat = agent_run_loop.get_git_diff_stat()

            # 生成查看命令
            if hasattr(self.agent, "start_commit") and self.agent.start_commit:
                git_view_command = f"git diff {self.agent.start_commit}..HEAD"
        except Exception as e:
            git_diff_stat = f"获取git diff统计失败: {str(e)}"

        # 先获取格式化的摘要消息
        formatted_summary = ""
        if summary:
            formatted_summary = self.format_summary_message(summary)

        # 添加git diff统计信息到摘要中 - 只显示有效的代码变更统计
        is_valid_git_stat = (
            git_diff_stat
            and git_diff_stat.strip()
            and
            # 过滤错误信息（获取失败等）
            not git_diff_stat.startswith("获取git diff统计失败")
            and
            # 过滤无变更提示
            "没有检测到代码变更" not in git_diff_stat
        )

        if is_valid_git_stat:
            diff_section = f"\n\n## 代码变更统计\n```\n{git_diff_stat}\n```"
            if git_view_command:
                diff_section += f"\n\n查看完整差异：```bash\n{git_view_command}\n```"
            formatted_summary += diff_section

        # 关键流程：直接调用 memory_manager 确保记忆提示
        try:
            self.agent.memory_manager._ensure_memory_prompt(agent=self.agent)
        except Exception as e:
            save_exception(
                e,
                module="jarvis_agent.__init__",
                function="_handle_history_with_summary",
            )
            pass

            # 非关键流程：广播清理历史前事件（用于日志、监控等）
            try:
                self.agent.event_bus.emit(BEFORE_HISTORY_CLEAR, agent=self.agent)
            except Exception as e:
                save_exception(
                    e,
                    module="jarvis_agent.__init__",
                    function="_handle_history_with_summary",
                )
                pass

        # 清理历史（但不清理prompt，因为prompt会在builtin_input_handler中设置）
        if self.agent.model:
            self.agent.model.reset()
            # 重置后重新设置系统提示词，确保系统约束仍然生效
            self.agent._setup_system_prompt()
        # 清理预压缩状态（前台总结已清理历史，预压缩摘要基于旧快照已过期）
        self.agent._pre_compressed_summary = None
        self.agent._pre_compress_snapshot_count = 0
        self.agent._pre_compressing = False
        # 重置会话
        self.agent.session.clear_history()
        # 重置 addon_prompt 跳过轮数计数器
        self.agent._addon_prompt_skip_rounds = 0
        # 重置没有工具调用的计数器
        self.agent._no_tool_call_count = 0
        # 打开input handler开关，让下一轮可以处理pin_content中的特殊标记
        self.agent.run_input_handlers_next_turn = True

        # 获取任务列表信息（用于历史记录）
        task_list_info = ""
        try:
            # 获取所有任务列表的摘要信息
            task_lists_summary: List[Dict[str, Any]] = []
            for (
                task_list_id,
                task_list,
            ) in self.agent.task_list_manager.task_lists.items():
                summary_dict = self.agent.task_list_manager.get_task_list_summary(
                    task_list_id
                )
                if summary_dict and isinstance(summary_dict, dict):
                    task_lists_summary.append(summary_dict)

            if task_lists_summary:
                task_list_info = "\\n\\n## 任务列表状态\\n"
                for summary_dict in task_lists_summary:
                    task_list_info += (
                        f"\\n- 目标: {summary_dict.get('main_goal', '未知')}"
                    )
                    task_list_info += (
                        f"\\n- 总任务数: {summary_dict.get('total_tasks', 0)}"
                    )
                    task_list_info += f"\\n- 待执行: {summary_dict.get('pending', 0)}"
                    task_list_info += f"\\n- 执行中: {summary_dict.get('running', 0)}"
                    task_list_info += f"\\n- 已完成: {summary_dict.get('completed', 0)}"
                    task_list_info += f"\\n- 失败: {summary_dict.get('failed', 0)}"
                    task_list_info += (
                        f"\\n- 已放弃: {summary_dict.get('abandoned', 0)}\\n"
                    )
        except Exception:
            # 非关键流程，失败时不影响主要功能
            pass

        # 非关键流程：广播清理历史后的事件（用于日志、监控等）
        try:
            self.agent.event_bus.emit(AFTER_HISTORY_CLEAR, agent=self.agent)
        except Exception as e:
            save_exception(
                e,
                module="jarvis_agent.__init__",
                function="_handle_history_with_summary",
            )
            pass

        # 将任务列表信息添加到摘要中
        if task_list_info:
            formatted_summary += task_list_info

        # 添加用户固定的重要内容
        user_fixed_content = []

        # 添加用户通过 <Pin> 标记固定的其他重要内容
        # pin_content 可能包含用户通过 <Pin> 标记追加的内容，这些内容作为补充
        if self.agent.pin_content.strip():
            pin_content_stripped = self.agent.pin_content.strip()
            user_fixed_content.append(f"**用户固定内容**：\n{pin_content_stripped}")

        # 添加最近的记忆
        if hasattr(self.agent, "recent_memories") and self.agent.recent_memories:
            user_fixed_content.append(
                f"**最近记忆**：\n{chr(10).join(self.agent.recent_memories)}"
            )

        # 如果有任何固定内容，添加到摘要中（放在最前面，确保优先级）
        if user_fixed_content:
            pin_section = f"\n\n## 🎯 用户的原始需求和要求（必须始终牢记）\n{chr(10).join(user_fixed_content)}"
            # 将固定内容放在最前面，确保最高优先级
            formatted_summary = pin_section + formatted_summary

        return formatted_summary

    def format_summary_message(self, summary: str) -> str:
        """格式化摘要消息"""
        # 获取任务列表信息
        task_list_info = self.agent._get_task_list_info()

        # 获取已加载的规则信息（文件路径和描述）
        rules_section = ""
        loaded_rule_infos = []
        for rule_name in sorted(self.agent.rules_manager.loaded_rules):
            rule_path = self.agent.rules_manager.get_rule_file_path(rule_name)
            description = self.agent.rules_manager._extract_rule_description(rule_path)
            if description:
                loaded_rule_infos.append(
                    f"- {rule_name}: {description} (路径: {rule_path})"
                )
            else:
                loaded_rule_infos.append(f"- {rule_name} (路径: {rule_path})")

        if loaded_rule_infos:
            rules_info = "\n".join(loaded_rule_infos)
            rules_section = f"\n\n\n**📋 当前已加载的规则列表：**\n\n{rules_info}\n\n提示：如需查看规则的详细内容，用 `load_rule` 工具加载对应的规则文件。\n\n"

        # 获取会话文件路径信息
        session_file_info = ""
        try:
            from jarvis.jarvis_utils.dialogue_recorder import get_global_recorder
            from pathlib import Path

            recorder = get_global_recorder()
            session_file_path = recorder.get_session_file_path()
            if Path(session_file_path).exists():
                session_file_info = f"\n\n**📁 完整对话历史文件**：\n完整的对话历史已保存在下面这个文件中，需要查更详细的上下文时可以直接读取：\n`{session_file_path}`\n\n该文件包含先前所有对话的完整记录（JSONL 格式），每行一条消息，含时间戳、角色与内容。"
        except Exception:
            # 非关键流程，失败时不影响主要功能
            pass

        # 获取初始 commit 信息（仅对 CodeAgent）
        initial_commit_info = ""
        try:
            if hasattr(self.agent, "start_commit") and self.agent.start_commit:
                initial_commit_info = f"\n\n**🔖 初始 Git Commit（安全回退点）**：\n本次任务开始时的初始 commit 是：`{self.agent.start_commit}`\n\n**⚠️ 重要提示**：如果文件被破坏得很严重无法恢复，可以使用以下命令重置到这个初始 commit：\n```bash\ngit reset --hard {self.agent.start_commit}\n```\n这将丢弃所有未提交的更改，将工作区恢复到任务开始时的状态。请谨慎使用此命令，确保这是你真正想要的操作。"
        except Exception:
            # 非关键流程，失败时不影响主要功能
            pass

        formatted_message = f"""
    以下是从先前对话提取的要点摘要：

    <content>
    {summary}
    </content>{rules_section}

    **重要约束**：
    - 一切操作依据工具实际返回的结果，禁止推测、假设或虚构；每个结论都要有验证依据。
    - 工具调用：一次可调用一个或多个**互不依赖**的工具；存在依赖时先执行被依赖的工具，等待结果后再继续。
    - 需要编译/构建/测试验证的代码改动，必须验证通过后才能视为完成；不要因为"代码写了"就宣称任务完成。

    **🎯 核心任务目标提醒**：
    请始终牢记用户的最新任务目标（见上方"用户原始需求与要求"部分）。所有操作都围绕该目标进行；若当前进度偏离最新目标，请及时调整方向。注意：用户的目标可能在对话过程中变化，请以最新表述为准。

    请基于以上信息继续推进任务。注意：这是先前对话的摘要，上下文因超限已重置。请直接继续，无需重复已完成步骤；如需更多信息，可询问用户。{session_file_info}{initial_commit_info}
        """

        # 如果有任务列表信息，添加到消息后面
        if task_list_info:
            formatted_message += f"\n\n{task_list_info}"

        return formatted_message
