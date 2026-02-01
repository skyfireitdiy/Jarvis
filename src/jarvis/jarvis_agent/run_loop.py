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
from jarvis.jarvis_utils.config import is_enable_autonomous
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.tag import ot
from jarvis.jarvis_utils.utils import get_context_token_count

if TYPE_CHECKING:
    # 仅用于类型标注，避免运行时循环依赖
    from . import Agent
    from jarvis.jarvis_autonomous.interaction import DialogueManager
    from jarvis.jarvis_autonomous.interaction import AmbiguityResolver
    from jarvis.jarvis_autonomous.interaction import ProactiveAssistant
    from jarvis.jarvis_autonomous.empathy import EmotionRecognizer
    from jarvis.jarvis_autonomous.empathy import NeedPredictor
    from jarvis.jarvis_autonomous.empathy import PersonalityAdapter
    from jarvis.jarvis_digital_twin.proactive_service import ProactiveServiceManager
    from jarvis.jarvis_digital_twin.continuous_learning import ContinuousLearningManager
    from jarvis.jarvis_autonomous.manager import AutonomousManager


class AgentRunLoop:
    def __init__(self, agent: "Agent") -> None:
        self.agent = agent
        self.tool_reminder_rounds = int(os.environ.get("tool_reminder_rounds", 20))
        # 基于剩余token数量的自动总结阈值：当剩余token低于输入窗口的25%时触发
        # 使用模型的平台特定配置，确保阈值计算与运行时检查使用相同的配置
        max_input_tokens = self.agent.model._get_platform_max_input_token_count()
        self.summary_remaining_token_threshold = int(max_input_tokens * 0.25)
        self.conversation_turn_threshold = get_conversation_turn_threshold()

        # Git diff相关属性
        self._git_diff: Optional[str] = None  # 缓存git diff内容

        # 智能增强组件（可选启用）
        self._autonomous_enabled = is_enable_autonomous()
        self._dialogue_manager: Optional["DialogueManager"] = None
        self._emotion_recognizer: Optional["EmotionRecognizer"] = None
        self._need_predictor: Optional["NeedPredictor"] = None
        self._personality_adapter: Optional["PersonalityAdapter"] = None
        self._proactive_assistant: Optional["ProactiveAssistant"] = None
        self._ambiguity_resolver: Optional["AmbiguityResolver"] = None
        self._proactive_service_manager: Optional["ProactiveServiceManager"] = None
        self._continuous_learning_manager: Optional["ContinuousLearningManager"] = None
        self._autonomous_manager: Optional["AutonomousManager"] = None
        if self._autonomous_enabled:
            self._init_autonomous_components()

    def _init_autonomous_components(self) -> None:
        """初始化智能增强组件（仅在启用时调用）"""
        # 为每个组件创建独立的LLM实例，避免共享实例导致的上下文问题
        # 每个组件调用 registry.get_cheap_platform() 都会创建新的独立实例
        try:
            from jarvis.jarvis_platform.registry import PlatformRegistry
            from jarvis.jarvis_autonomous.interaction import DialogueManager
            from jarvis.jarvis_autonomous.interaction import AmbiguityResolver
            from jarvis.jarvis_autonomous.interaction import ProactiveAssistant
            from jarvis.jarvis_autonomous.empathy import EmotionRecognizer
            from jarvis.jarvis_autonomous.empathy import NeedPredictor
            from jarvis.jarvis_autonomous.empathy import PersonalityAdapter

            registry = PlatformRegistry.get_global_platform_registry()

            # 为每个组件创建独立的LLM实例，确保完全隔离
            self._dialogue_manager = DialogueManager()
            self._emotion_recognizer = EmotionRecognizer(
                llm_client=registry.get_cheap_platform()
            )
            self._need_predictor = NeedPredictor(
                llm_client=registry.get_cheap_platform()
            )
            self._personality_adapter = PersonalityAdapter(
                llm_client=registry.get_cheap_platform()
            )
            self._proactive_assistant = ProactiveAssistant(
                llm_client=registry.get_cheap_platform()
            )
            self._ambiguity_resolver = AmbiguityResolver(
                llm_client=registry.get_cheap_platform()
            )

            PrettyOutput.auto_print(
                "✅ 智能增强组件已启用（9个组件，每个使用独立LLM实例）"
            )
        except ImportError as e:
            PrettyOutput.auto_print(f"⚠️ 智能增强组件加载失败: {e}")
            self._autonomous_enabled = False
        except ImportError as e:
            PrettyOutput.auto_print(f"⚠️ 智能增强组件加载失败: {e}")
            self._autonomous_enabled = False

        # 初始化主动服务管理器（集成阶段5.1和5.2组件）
        try:
            from jarvis.jarvis_digital_twin.proactive_service import (
                ProactiveServiceManager,
            )
            from jarvis.jarvis_digital_twin.prediction import (
                NeedInferrer,
                TimingJudge,
            )
            from jarvis.jarvis_digital_twin.user_profile import (
                PreferenceLearner,
            )

            # 初始化阶段5.1和5.2组件，每个使用独立的LLM实例
            timing_judge = TimingJudge(llm_client=registry.get_cheap_platform())
            need_inferrer = NeedInferrer(llm_client=registry.get_cheap_platform())
            preference_learner = PreferenceLearner(
                llm_client=registry.get_cheap_platform()
            )

            # 将组件注入到主动服务管理器
            self._proactive_service_manager = ProactiveServiceManager(
                timing_judge=timing_judge,
                need_inferrer=need_inferrer,
                preference_learner=preference_learner,
            )
        except ImportError:
            pass  # 主动服务管理器加载失败不影响其他功能

        # 初始化持续学习管理器，为所有子组件注入独立的LLM实例
        try:
            from jarvis.jarvis_digital_twin.continuous_learning import (
                ContinuousLearningManager,
            )
            from jarvis.jarvis_digital_twin.continuous_learning.knowledge_acquirer import (
                KnowledgeAcquirer,
            )
            from jarvis.jarvis_digital_twin.continuous_learning.skill_learner import (
                SkillLearner,
            )
            from jarvis.jarvis_digital_twin.continuous_learning.experience_accumulator import (
                ExperienceAccumulator,
            )
            from jarvis.jarvis_digital_twin.continuous_learning.adaptive_engine import (
                AdaptiveEngine,
            )

            self._continuous_learning_manager = ContinuousLearningManager(
                knowledge_acquirer=KnowledgeAcquirer(
                    llm_client=registry.get_cheap_platform()
                ),
                skill_learner=SkillLearner(llm_client=registry.get_cheap_platform()),
                experience_accumulator=ExperienceAccumulator(
                    llm_client=registry.get_cheap_platform()
                ),
                adaptive_engine=AdaptiveEngine(
                    llm_client=registry.get_cheap_platform()
                ),
            )
        except ImportError:
            pass  # 持续学习管理器加载失败不影响其他功能

        # 初始化自主能力管理器（整合阶段4.1和4.2组件）
        try:
            from jarvis.jarvis_autonomous.manager import AutonomousManager

            self._autonomous_manager = AutonomousManager()
        except ImportError:
            pass  # 自主能力管理器加载失败不影响其他功能

    def _preprocess_user_input(self, user_input: str) -> str:
        """预处理用户输入（智能增强）

        Args:
            user_input: 原始用户输入

        Returns:
            处理后的用户输入（可能包含增强信息）
        """
        if not self._autonomous_enabled:
            return user_input

        enhanced_input = user_input

        # 1. 记录对话轮次
        if self._dialogue_manager:
            self._dialogue_manager.add_turn("default", "user", user_input)

        # 2. 情绪识别
        if self._emotion_recognizer:
            try:
                emotion_result = self._emotion_recognizer.recognize(user_input)
                if emotion_result:
                    if emotion_result.emotion_type.value not in ("neutral", "unknown"):
                        # 将情绪信息作为上下文提示
                        emotion_hint = f"[用户情绪: {emotion_result.emotion_type.value}, 置信度: {emotion_result.confidence:.2f}]"
                        enhanced_input = f"{emotion_hint}\n{user_input}"
            except Exception:
                pass  # 情绪识别失败不影响主流程

        # 3. 歧义检测
        if self._ambiguity_resolver:
            try:
                ambiguity_result = self._ambiguity_resolver.detect_ambiguity(user_input)
                if ambiguity_result and ambiguity_result.has_ambiguity:
                    # 提示存在歧义
                    ambiguity_hint = (
                        f"[检测到歧义: {ambiguity_result.ambiguity_type.value}]"
                    )
                    enhanced_input = f"{ambiguity_hint}\n{enhanced_input}"
            except Exception:
                pass  # 歧义检测失败不影响主流程

        # 4. 主动服务处理
        if self._proactive_service_manager:
            try:
                from jarvis.jarvis_digital_twin.proactive_service import ServiceStatus

                # 获取对话历史
                conversation_history = []
                if self._dialogue_manager:
                    context = self._dialogue_manager.get_context("default")
                    if context:
                        conversation_history = [
                            {"role": turn.role, "content": turn.content}
                            for turn in context.turns
                        ]

                results = self._proactive_service_manager.process_context(
                    user_input,
                    conversation_history=conversation_history,
                )
                # 将服务结果添加到增强输入
                service_count = 0
                for result in results:
                    if result.status == ServiceStatus.COMPLETED:
                        enhanced_input = (
                            f"[主动服务: {result.message}]\n{enhanced_input}"
                        )
                        service_count += 1
            except Exception:
                pass  # 主动服务失败不影响主流程

        # 5. 持续学习知识应用
        if self._continuous_learning_manager:
            try:
                knowledge_hints = []
                total_chars = 0
                MAX_TOTAL_CHARS = 300  # 总字符数硬限制，保护LLM上下文
                MIN_CONFIDENCE = 0.7  # 最低置信度阈值

                # 获取相关知识（只取高置信度的）
                relevant_knowledge = (
                    self._continuous_learning_manager.get_relevant_knowledge(
                        context=user_input,
                        limit=3,
                    )
                )
                if relevant_knowledge.get("knowledge"):
                    for k in relevant_knowledge["knowledge"][:2]:
                        if k.get("confidence", 0) >= MIN_CONFIDENCE:
                            hint = f"知识({k['type']}): {k['content'][:80]}"
                            if total_chars + len(hint) <= MAX_TOTAL_CHARS:
                                knowledge_hints.append(hint)
                                total_chars += len(hint)

                # 获取相似经验（仅在还有空间时）
                if total_chars < MAX_TOTAL_CHARS - 50:
                    similar_experiences = (
                        self._continuous_learning_manager.get_similar_experiences(
                            context=user_input,
                            limit=2,
                        )
                    )
                    if similar_experiences:
                        for exp in similar_experiences[:1]:
                            if exp.get("outcome"):
                                hint = f"经验: {exp['outcome'][:60]}"
                                if total_chars + len(hint) <= MAX_TOTAL_CHARS:
                                    knowledge_hints.append(hint)
                                    total_chars += len(hint)

                # 将知识提示添加到增强输入
                if knowledge_hints:
                    hints_text = "; ".join(knowledge_hints)
                    enhanced_input = f"[学习知识: {hints_text}]\n{enhanced_input}"
            except Exception:
                pass  # 知识应用失败不影响主流程

        return enhanced_input

    def _postprocess_response(self, response: str) -> str:
        """后处理响应（智能增强）

        Args:
            response: 原始响应

        Returns:
            处理后的响应
        """
        if not self._autonomous_enabled:
            return response

        # 记录助手响应
        if self._dialogue_manager:
            self._dialogue_manager.add_turn("default", "assistant", response)

        # 检查是否需要主动交互（暂不修改响应，仅记录）
        if self._proactive_assistant:
            try:
                # 获取对话历史用于分析
                if self._dialogue_manager:
                    context = self._dialogue_manager.summarize_context("default")
                    self._proactive_assistant.analyze_for_proactive_action(
                        {"context": context}
                    )
            except Exception:
                pass  # 主动交互分析失败不影响主流程

        # 持续学习：从交互中学习
        if self._continuous_learning_manager:
            try:
                # 获取最近的用户输入（从对话管理器）
                last_user_input = ""
                if self._dialogue_manager:
                    dialogue_context = self._dialogue_manager.get_context("default")
                    if dialogue_context and dialogue_context.turns:
                        # 获取最近的用户输入
                        for turn in reversed(dialogue_context.turns):
                            if turn.role == "user":
                                last_user_input = turn.content
                                break
                if last_user_input:
                    self._continuous_learning_manager.learn_from_interaction(
                        user_input=last_user_input,
                        assistant_response=response,
                    )
            except Exception:
                pass  # 持续学习失败不影响主流程

        return response

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
        # 与registry.py的检测逻辑保持一致：
        # 1. 先尝试标准模式：结束标签必须在行首（使用 ^ 锚点）
        # 2. 再尝试宽松模式：结束标签不一定在行首
        # 使用 (?msi) 标志：多行、DOTALL、忽略大小写
        filtered = response

        # 标准模式：结束标签必须在行首（与registry.py第855行的标准提取模式一致）
        standard_pattern = (
            rf"(?msi){re.escape(ot('TOOL_CALL'))}(.*?)^{re.escape(ct('TOOL_CALL'))}"
        )
        filtered = re.sub(standard_pattern, "", filtered)

        # 宽松模式：结束标签不一定在行首（与registry.py第910行的宽松提取模式一致）
        # 用于匹配标准模式可能遗漏的情况
        lenient_pattern = (
            rf"(?msi){re.escape(ot('TOOL_CALL'))}(.*?){re.escape(ct('TOOL_CALL'))}"
        )
        filtered = re.sub(lenient_pattern, "", filtered)

        # 清理可能留下的多余空行（超过2个连续换行符替换为2个）
        filtered = re.sub(r"\n{3,}", "\n\n", filtered)

        # 过滤掉 [MODE:xxx] 模式标记
        filtered = re.sub(r"\[MODE:[^\]]+\]", "", filtered)

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

    def check_and_compress_context(
        self,
        model_instance,
        current_message_tokens: int = 0,
    ) -> None:
        """检查并压缩对话上下文

        自动压缩触发检查：在调用模型前检查（基于剩余token数量或对话轮次）

        Args:
            model_instance: 平台模型实例（BasePlatform子类实例）
            current_message_tokens: 当前消息的token数
        """
        conversation_turn = model_instance.get_conversation_turn()
        try:
            # 获取剩余token数量
            remaining_tokens = model_instance.get_remaining_token_count()
            max_input_tokens = model_instance._get_platform_max_input_token_count()

            # 从剩余token中减去当前消息的token数
            remaining_tokens -= current_message_tokens

            # 检查是否满足压缩触发条件
            # 条件1：剩余token低于25%（即已使用超过75%）
            token_limit_triggered = max_input_tokens > 0 and remaining_tokens <= int(
                max_input_tokens * 0.25
            )

            # 条件2：对话轮次超过阈值（检查当前轮次+1，因为本次调用会增加一轮）
            conversation_turn_threshold = get_conversation_turn_threshold()
            turn_limit_triggered = (conversation_turn + 1) > conversation_turn_threshold

            should_compress = token_limit_triggered or turn_limit_triggered

            if should_compress:
                # 确定触发原因
                if token_limit_triggered and turn_limit_triggered:
                    trigger_reason = "Token和轮次双重限制触发"
                elif token_limit_triggered:
                    trigger_reason = "Token限制触发"
                else:
                    trigger_reason = "对话轮次限制触发"

                # 打印触发信息
                if token_limit_triggered:
                    PrettyOutput.auto_print(
                        f"🔍 {trigger_reason}，当前剩余token: {remaining_tokens}/{max_input_tokens} (剩余 {remaining_tokens / max_input_tokens * 100:.1f}%)"
                    )
                else:
                    PrettyOutput.auto_print(
                        f"🔍 {trigger_reason}，当前对话轮次: {conversation_turn + 1}/{conversation_turn_threshold}"
                    )

                try:
                    # 使用自适应压缩：根据任务类型动态选择压缩策略
                    compression_success = self.agent._adaptive_compression()

                    if compression_success:
                        # 自适应压缩成功，摘要已作为消息插入到历史中
                        PrettyOutput.auto_print("✅ 自适应压缩完成，对话上下文已更新")
                    else:
                        # 自适应压缩失败，回退到完整摘要压缩
                        PrettyOutput.auto_print("⚠️ 自适应压缩失败，回退到完整摘要压缩")
                        summary_text = self.agent._summarize_and_clear_history(
                            trigger_reason=trigger_reason
                        )

                        if summary_text:
                            # 将摘要加入addon_prompt，维持上下文连续性
                            self.agent.session.addon_prompt = join_prompts(
                                [self.agent.session.addon_prompt, summary_text]
                            )

                        PrettyOutput.auto_print("✅ 完整摘要压缩完成，对话上下文已更新")
                except Exception as e:
                    # 压缩失败不影响对话流程
                    PrettyOutput.auto_print(f"⚠️ 自动压缩失败: {str(e)}")
        except Exception as e:
            # 压缩检查失败不影响对话流程
            PrettyOutput.auto_print(f"⚠️ 压缩检查失败: {str(e)}")

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

                ag = self.agent

                # 更新输入处理器标志
                if ag.run_input_handlers_next_turn:
                    run_input_handlers = True
                    ag.run_input_handlers_next_turn = False

                # 首次运行初始化
                if ag.first:
                    ag._first_run()

                # 在调用模型前检查并执行压缩
                # 计算当前消息的token数
                current_message_tokens = (
                    get_context_token_count(ag.session.prompt)
                    if ag.session.prompt
                    else 0
                )
                self.check_and_compress_context(
                    model_instance=ag.model,
                    current_message_tokens=current_message_tokens,
                )

                # 智能增强：预处理用户输入
                processed_prompt = (
                    self._preprocess_user_input(ag.session.prompt)
                    if ag.session.prompt
                    else ag.session.prompt
                )

                # 调用模型获取响应
                try:
                    current_response = ag._call_model(
                        processed_prompt, True, run_input_handlers
                    )
                except KeyboardInterrupt:
                    # 获取用户补充信息并继续下一轮
                    addon_info = self._handle_interrupt_with_input()
                    if addon_info:
                        ag.session.addon_prompt = join_prompts(
                            [ag.session.addon_prompt, addon_info]
                        )
                    # 在中断后，设置标志以在下一轮执行input handler
                    ag.run_input_handlers_next_turn = True
                    continue

                ag.session.prompt = ""
                run_input_handlers = False

                # 智能增强：后处理响应
                current_response = self._postprocess_response(current_response)

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
                    # 直接使用全量总结
                    summary_text = ag._summarize_and_clear_history(
                        trigger_reason="手动触发"
                    )
                    if summary_text:
                        # 将摘要作为下一轮的附加提示加入，从而维持上下文连续性
                        ag.session.addon_prompt = join_prompts(
                            [ag.session.addon_prompt, summary_text]
                        )
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

                        # 获取模型名称：优先使用model.get_model_name()，如果不存在则回退到'LLM'
                        model_name = ag.model.model_name
                        title = f"[bold cyan]{(G.get_current_agent_name() + ' · ') if G.get_current_agent_name() else ''}{model_name}[/bold cyan]"
                        PrettyOutput.print_markdown(
                            filtered_response, title=title, border_style="bright_blue"
                        )

                try:
                    need_return, tool_prompt = ag._call_tools(current_response)
                except KeyboardInterrupt:
                    # 获取用户补充信息并继续执行
                    addon_info = self._handle_interrupt_with_input()
                    if addon_info:
                        ag.session.addon_prompt = join_prompts(
                            [ag.session.addon_prompt, addon_info]
                        )
                    # 在中断后，设置标志以在下一轮执行input handler
                    ag.run_input_handlers_next_turn = True
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
                                    # 在中断后，设置标志以在下一轮执行input handler
                                    ag.run_input_handlers_next_turn = True
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
                                    # 在中断后，设置标志以在下一轮执行input handler
                                    ag.run_input_handlers_next_turn = True
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

                # 保存当前响应内容供用户手动修复工具调用
                ag._last_response_content = current_response

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

                            # 保存最近一次失败的工具调用内容（供手动修复使用）
                            # ag._last_failed_tool_call_content = current_response  # 暂时注释掉，因为Agent类未定义此属性

                            # 尝试使用大模型修复
                            fixed_content = fix_tool_call_with_llm(
                                current_response, ag, error_msg
                            )

                            if fixed_content:
                                # 修复成功，直接重新解析并执行工具调用
                                need_return, tool_prompt = ag._call_tools(fixed_content)

                                # 如果工具要求立即返回结果（例如 SEND_MESSAGE 需要将字典返回给上层），直接返回该结果
                                if need_return:
                                    ag._no_tool_call_count = 0
                                    return tool_prompt

                                # 将上一个提示和工具提示安全地拼接起来（仅当工具结果为字符串时）
                                safe_tool_prompt = (
                                    tool_prompt if isinstance(tool_prompt, str) else ""
                                )

                                ag.session.prompt = join_prompts(
                                    [ag.session.prompt, safe_tool_prompt]
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
                    # 在中断后，设置标志以在下一轮执行input handler
                    ag.run_input_handlers_next_turn = True
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
                # 在中断后，设置标志以在下一轮执行input handler
                ag.run_input_handlers_next_turn = True
                continue
            except Exception as e:
                PrettyOutput.auto_print(f"❌ 任务失败: {str(e)}")
                return f"Task failed: {str(e)}"

    def get_git_diff_stat(self) -> str:
        """获取从起始commit到当前commit的git diff统计信息

        返回:
            str: git diff统计信息，如果无法获取则返回错误信息
        """
        try:
            from jarvis.jarvis_utils.git_utils import get_diff_stat_between_commits
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
                return "没有检测到代码变更"

            # 获取diff统计
            stat_content = get_diff_stat_between_commits(start_commit, current_commit)
            return stat_content

        except Exception as e:
            return f"获取git diff统计失败: {str(e)}"

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

            return self._check_diff_token_limit(diff_content)

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

    def _check_diff_token_limit(self, diff_content: str) -> str:
        """检查diff内容的token限制并返回适当的diff内容

        参数:
            diff_content: 原始的diff内容

        返回:
            str: 处理后的diff内容（可能是原始内容或截断后的内容）
        """
        from jarvis.jarvis_utils.embedding import get_context_token_count

        # 检查token数量限制
        max_input_tokens = get_max_input_token_count()
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
