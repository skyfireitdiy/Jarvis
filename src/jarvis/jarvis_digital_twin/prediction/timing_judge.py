"""时机判断器模块

判断何时主动提供帮助，基于用户偏好和当前上下文进行决策。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from jarvis.jarvis_digital_twin.prediction import (
    PredictionContext,
    TimingDecision,
    TimingResult,
)

from jarvis.jarvis_utils.output import PrettyOutput


class JudgmentStrategy(Enum):
    """判断策略枚举"""

    CONSERVATIVE = "conservative"  # 保守策略（倾向于保持沉默）
    BALANCED = "balanced"  # 平衡策略（默认）
    PROACTIVE = "proactive"  # 主动策略（倾向于提供帮助）


class UserState(Enum):
    """用户状态枚举"""

    IDLE = "idle"  # 空闲
    BUSY = "busy"  # 忙碌
    STUCK = "stuck"  # 卡住
    EXPLORING = "exploring"  # 探索中
    FOCUSED = "focused"  # 专注中
    UNKNOWN = "unknown"  # 未知


class UrgencyLevel(Enum):
    """紧急程度枚举"""

    CRITICAL = "critical"  # 紧急（如错误、阻塞）
    HIGH = "high"  # 高（如即将超时）
    MEDIUM = "medium"  # 中等
    LOW = "low"  # 低
    NONE = "none"  # 无紧急性


@dataclass
class UserStateAnalysis:
    """用户状态分析结果"""

    state: UserState
    confidence: float
    indicators: List[str]


@dataclass
class UrgencyAnalysis:
    """紧急程度分析结果"""

    level: UrgencyLevel
    confidence: float
    reasons: List[str]


class RuleBasedJudge:
    """规则判断引擎

    基于预定义规则进行时机判断。
    """

    # 【优化】用户状态判断规则 - 扩展关键词库
    STATE_INDICATORS: Dict[UserState, Dict[str, List[str]]] = {
        UserState.STUCK: {
            "keywords": [
                "stuck",
                "help",
                "error",
                "fail",
                "cannot",
                "卡住",
                "帮助",
                "错误",
                # 新增：更多表达困惑和需要帮助的词汇
                "不知道",
                "不会",
                "不懂",
                "怎么办",
                "怎么",
                "how",
                "不知道怎么办",
                "搞不懂",
                "弄不明白",
                "不会做",
                "做不出来",
                "解决不了",
                "无法",
                "unable",
                "confused",
                "lost",
                "不懂怎么",
                "不会用",
                "不知道怎么",
                "不会弄",
            ],
            "patterns": ["repeated_attempts", "long_pause", "error_state"],
        },
        UserState.BUSY: {
            "keywords": [
                "working",
                "implementing",
                "coding",
                "正在",
                "实现",
                "编写",
                # 新增：更多表达正在工作的词汇
                "写代码",
                "开发中",
                "正在写",
                "正在做",
                "忙着",
                "开发",
                "implement",
                "developing",
                "writing",
                "正在开发",
            ],
            "patterns": ["frequent_edits", "active_coding", "multiple_files"],
        },
        UserState.EXPLORING: {
            "keywords": [
                "what",
                "how",
                "why",
                "explore",
                "什么",
                "如何",
                "为什么",
                # 新增：更多表达探索和询问的词汇
                "想知道",
                "想了解",
                "了解一下",
                "什么意思",
                "干嘛",
                "为什么",
                "怎么才能",
                "想问",
                "请问",
                "了解一下",
                "learn",
                "understand",
                "想知道怎么",
            ],
            "patterns": ["browsing_files", "reading_docs", "asking_questions"],
        },
        UserState.FOCUSED: {
            "keywords": [
                "focus",
                "concentrate",
                "deep",
                "专注",
                "集中",
                # 新增：更多表达专注的词汇
                "专心",
                "正在改",
                "改这个",
                "在弄",
                "在改",
                "专注在",
                "focusing",
                "修改中",
            ],
            "patterns": ["single_file_edit", "continuous_work", "no_questions"],
        },
        UserState.IDLE: {
            "keywords": [
                # 新增：表达空闲的词汇
                "等",
                "waiting",
                "等一下",
                "稍等",
            ],
            "patterns": ["no_activity", "long_idle", "session_start"],
        },
    }

    # 【优化】紧急程度判断规则 - 扩展关键词库
    URGENCY_INDICATORS: Dict[UrgencyLevel, Dict[str, Any]] = {
        UrgencyLevel.CRITICAL: {
            "keywords": [
                "critical",
                "urgent",
                "crash",
                "紧急",
                "崩溃",
                "严重",
                # 新增：更多表达紧急和严重的词汇
                "马上",
                "立刻",
                "赶紧",
                "急",
                "救命",
                "不行了",
                "完蛋",
                "立刻",
                "马上",
                "blocking",
                "blocked",
                "无法继续",
                "不能继续",
                "紧急",
                "严重错误",
            ],
            "conditions": ["has_errors", "build_failed", "tests_failing"],
        },
        UrgencyLevel.HIGH: {
            "keywords": [
                "important",
                "asap",
                "deadline",
                "重要",
                "尽快",
                # 新增：更多表达高优先级的词汇
                "优先",
                "先",
                "赶快",
                "快点",
                "希望",
                "想快点",
                "urgent",
                "priority",
                "重要的事情",
                "必须",
                "一定",
                "尽快完成",
            ],
            "conditions": ["approaching_deadline", "blocking_issue"],
        },
        UrgencyLevel.MEDIUM: {
            "keywords": [
                "should",
                "need",
                "want",
                "应该",
                "需要",
                "想要",
                # 新增：更多表达中等优先级的词汇
                "想",
                "要",
                "可以",
                "能不能",
                "是否可以",
                "try",
                "attempt",
                "希望可以",
                "想要实现",
                "需要做",
            ],
            "conditions": ["normal_development", "feature_request"],
        },
        UrgencyLevel.LOW: {
            "keywords": [
                "maybe",
                "later",
                "optional",
                "也许",
                "稍后",
                "可选",
                # 新增：更多表达低优先级的词汇
                "有空",
                "有时间",
                "不急",
                "不着急",
                "慢慢",
                "有时间再",
                "no rush",
                "when free",
                "不着急",
            ],
            "conditions": ["nice_to_have", "exploration"],
        },
    }

    # 【优化】帮助决策矩阵 - 调整置信度阈值以提高规则覆盖率
    # 策略：
    # 1. 对OFFER_HELP决策降低阈值要求（0.9→0.75），让规则更容易触发主动服务
    # 2. 对STAY_SILENT决策提高阈值要求（0.5→0.6），避免过度保守
    HELP_DECISION_MATRIX: Dict[tuple, tuple] = {
        # 卡住状态 - 用户明显需要帮助，积极提供
        (UserState.STUCK, UrgencyLevel.CRITICAL): (TimingDecision.OFFER_HELP, 0.95),
        (UserState.STUCK, UrgencyLevel.HIGH): (
            TimingDecision.OFFER_HELP,
            0.85,
        ),  # 降低0.9→0.85
        (UserState.STUCK, UrgencyLevel.MEDIUM): (
            TimingDecision.OFFER_HELP,
            0.75,
        ),  # 降低0.8→0.75
        (UserState.STUCK, UrgencyLevel.LOW): (
            TimingDecision.ASK_CONFIRMATION,
            0.65,
        ),  # 降低0.7→0.65
        (UserState.STUCK, UrgencyLevel.NONE): (TimingDecision.ASK_CONFIRMATION, 0.6),
        # 忙碌状态 - 谨慎打扰，但紧急情况除外
        (UserState.BUSY, UrgencyLevel.CRITICAL): (TimingDecision.OFFER_HELP, 0.85),
        (UserState.BUSY, UrgencyLevel.HIGH): (TimingDecision.ASK_CONFIRMATION, 0.7),
        (UserState.BUSY, UrgencyLevel.MEDIUM): (
            TimingDecision.STAY_SILENT,
            0.65,
        ),  # 提高0.6→0.65
        (UserState.BUSY, UrgencyLevel.LOW): (
            TimingDecision.STAY_SILENT,
            0.75,
        ),  # 提高0.7→0.75
        (UserState.BUSY, UrgencyLevel.NONE): (TimingDecision.STAY_SILENT, 0.8),
        # 探索状态 - 适时提供帮助
        (UserState.EXPLORING, UrgencyLevel.CRITICAL): (TimingDecision.OFFER_HELP, 0.9),
        (UserState.EXPLORING, UrgencyLevel.HIGH): (TimingDecision.OFFER_HELP, 0.75),
        (UserState.EXPLORING, UrgencyLevel.MEDIUM): (
            TimingDecision.ASK_CONFIRMATION,
            0.65,
        ),
        (UserState.EXPLORING, UrgencyLevel.LOW): (
            TimingDecision.WAIT_FOR_MORE_CONTEXT,
            0.6,
        ),
        (UserState.EXPLORING, UrgencyLevel.NONE): (
            TimingDecision.WAIT_FOR_MORE_CONTEXT,
            0.7,
        ),
        # 专注状态 - 避免打扰，除非紧急
        (UserState.FOCUSED, UrgencyLevel.CRITICAL): (TimingDecision.OFFER_HELP, 0.8),
        (UserState.FOCUSED, UrgencyLevel.HIGH): (TimingDecision.ASK_CONFIRMATION, 0.65),
        (UserState.FOCUSED, UrgencyLevel.MEDIUM): (TimingDecision.STAY_SILENT, 0.7),
        (UserState.FOCUSED, UrgencyLevel.LOW): (TimingDecision.STAY_SILENT, 0.8),
        (UserState.FOCUSED, UrgencyLevel.NONE): (TimingDecision.STAY_SILENT, 0.85),
        # 空闲状态 - 可以提供帮助
        (UserState.IDLE, UrgencyLevel.CRITICAL): (TimingDecision.OFFER_HELP, 0.9),
        (UserState.IDLE, UrgencyLevel.HIGH): (TimingDecision.OFFER_HELP, 0.8),
        (UserState.IDLE, UrgencyLevel.MEDIUM): (TimingDecision.OFFER_HELP, 0.7),
        (UserState.IDLE, UrgencyLevel.LOW): (TimingDecision.ASK_CONFIRMATION, 0.6),
        (UserState.IDLE, UrgencyLevel.NONE): (
            TimingDecision.WAIT_FOR_MORE_CONTEXT,
            0.5,
        ),
        # 未知状态 - 保守策略
        (UserState.UNKNOWN, UrgencyLevel.CRITICAL): (TimingDecision.OFFER_HELP, 0.85),
        (UserState.UNKNOWN, UrgencyLevel.HIGH): (TimingDecision.ASK_CONFIRMATION, 0.7),
        (UserState.UNKNOWN, UrgencyLevel.MEDIUM): (
            TimingDecision.WAIT_FOR_MORE_CONTEXT,
            0.6,
        ),
        (UserState.UNKNOWN, UrgencyLevel.LOW): (
            TimingDecision.WAIT_FOR_MORE_CONTEXT,
            0.55,  # 提高0.5→0.55
        ),
        (UserState.UNKNOWN, UrgencyLevel.NONE): (
            TimingDecision.STAY_SILENT,
            0.55,
        ),  # 提高0.5→0.55
    }

    def analyze_user_state(self, context: PredictionContext) -> UserStateAnalysis:
        """分析用户状态"""
        indicators: List[str] = []
        state_scores: Dict[UserState, float] = {state: 0.0 for state in UserState}

        # 分析当前消息
        message = context.current_message.lower() if context.current_message else ""
        for state, rules in self.STATE_INDICATORS.items():
            for keyword in rules.get("keywords", []):
                if keyword in message:
                    state_scores[state] += 0.3
                    indicators.append(f"关键词匹配: {keyword}")

        # 分析项目状态
        project_state = context.project_state
        if project_state:
            if project_state.get("has_errors", False):
                state_scores[UserState.STUCK] += 0.4
                indicators.append("检测到错误状态")
            if project_state.get("running_tests", False):
                state_scores[UserState.BUSY] += 0.3
                indicators.append("正在运行测试")
            if project_state.get("build_failed", False):
                state_scores[UserState.STUCK] += 0.5
                indicators.append("构建失败")

        # 分析代码上下文
        code_context = context.code_context
        if code_context:
            modified_files = code_context.get("modified_files", [])
            if len(modified_files) > 3:
                state_scores[UserState.BUSY] += 0.3
                indicators.append(f"修改了{len(modified_files)}个文件")
            elif len(modified_files) == 1:
                state_scores[UserState.FOCUSED] += 0.2
                indicators.append("专注于单个文件")

            last_action = code_context.get("last_action", "")
            if "debug" in last_action.lower():
                state_scores[UserState.STUCK] += 0.2
                indicators.append("正在调试")

        # 分析对话历史
        history = context.conversation_history
        if history:
            recent_questions = sum(
                1 for h in history[-5:] if "?" in h.get("content", "")
            )
            if recent_questions >= 3:
                state_scores[UserState.EXPLORING] += 0.3
                indicators.append(f"最近提出{recent_questions}个问题")

        # 如果没有活动，标记为空闲
        if not message and not code_context and not history:
            state_scores[UserState.IDLE] += 0.5
            indicators.append("无活动")

        # 选择最高分的状态
        best_state = max(state_scores, key=lambda x: state_scores[x])
        best_score = state_scores[best_state]

        # 如果所有分数都很低，标记为未知
        if best_score < 0.2:
            best_state = UserState.UNKNOWN
            best_score = 0.5

        return UserStateAnalysis(
            state=best_state,
            confidence=min(1.0, best_score),
            indicators=indicators,
        )

    def analyze_urgency(self, context: PredictionContext) -> UrgencyAnalysis:
        """分析紧急程度"""
        reasons: List[str] = []
        urgency_scores: Dict[UrgencyLevel, float] = {
            level: 0.0 for level in UrgencyLevel
        }

        # 分析当前消息
        message = context.current_message.lower() if context.current_message else ""
        for level, rules in self.URGENCY_INDICATORS.items():
            for keyword in rules.get("keywords", []):
                if keyword in message:
                    urgency_scores[level] += 0.4
                    reasons.append(f"关键词匹配: {keyword}")

        # 分析项目状态
        project_state = context.project_state
        if project_state:
            if project_state.get("has_errors", False):
                urgency_scores[UrgencyLevel.HIGH] += 0.3
                reasons.append("存在错误")
            if project_state.get("build_failed", False):
                urgency_scores[UrgencyLevel.CRITICAL] += 0.4
                reasons.append("构建失败")
            if project_state.get("tests_failing", False):
                urgency_scores[UrgencyLevel.HIGH] += 0.3
                reasons.append("测试失败")
            if project_state.get("deadline_approaching", False):
                urgency_scores[UrgencyLevel.HIGH] += 0.4
                reasons.append("截止日期临近")

        # 分析元数据
        metadata = context.metadata
        if metadata:
            if metadata.get("is_blocking", False):
                urgency_scores[UrgencyLevel.CRITICAL] += 0.5
                reasons.append("阻塞性问题")
            priority = metadata.get("priority", "")
            if priority == "high":
                urgency_scores[UrgencyLevel.HIGH] += 0.3
                reasons.append("高优先级")

        # 选择最高分的紧急程度
        best_level = max(urgency_scores, key=lambda x: urgency_scores[x])
        best_score = urgency_scores[best_level]

        # 如果所有分数都很低，标记为无紧急性
        if best_score < 0.2:
            best_level = UrgencyLevel.NONE
            best_score = 0.6

        return UrgencyAnalysis(
            level=best_level,
            confidence=min(1.0, best_score),
            reasons=reasons,
        )

    def judge_help_timing(
        self,
        user_state: UserStateAnalysis,
        urgency: UrgencyAnalysis,
    ) -> tuple:
        """判断帮助时机"""
        key = (user_state.state, urgency.level)
        decision, base_confidence = self.HELP_DECISION_MATRIX.get(
            key, (TimingDecision.WAIT_FOR_MORE_CONTEXT, 0.5)
        )

        # 综合置信度
        combined_confidence = (
            base_confidence * 0.5
            + user_state.confidence * 0.25
            + urgency.confidence * 0.25
        )

        reasoning = (
            f"用户状态: {user_state.state.value} (置信度: {user_state.confidence:.2f}), "
            f"紧急程度: {urgency.level.value} (置信度: {urgency.confidence:.2f})"
        )

        return decision, combined_confidence, reasoning

    def judge_silence_timing(
        self,
        context: PredictionContext,
        user_state: UserStateAnalysis,
    ) -> tuple:
        """判断沉默时机"""
        confidence = 0.5
        reasons: List[str] = []

        # 检查用户偏好
        user_profile = context.user_profile
        if user_profile:
            interaction_style = user_profile.get("preferences", {}).get(
                "interaction_style", {}
            )
            preferred_style = interaction_style.get("preferred_style", "")
            if preferred_style in ("minimal", "quiet", "non-intrusive"):
                confidence += 0.2
                reasons.append("用户偏好最小干扰")

            # 检查历史拒绝帮助的记录
            help_history = user_profile.get("help_history", {})
            declined_count = help_history.get("declined_count", 0)
            if declined_count > 3:
                confidence += 0.15
                reasons.append(f"用户曾{declined_count}次拒绝帮助")

        # 检查用户状态
        if user_state.state == UserState.FOCUSED:
            confidence += 0.2
            reasons.append("用户处于专注状态")
        elif user_state.state == UserState.BUSY:
            confidence += 0.15
            reasons.append("用户正在忙碌")

        # 检查是否有可操作的上下文
        if not context.current_message and not context.code_context:
            confidence += 0.1
            reasons.append("缺少可操作的上下文")

        reasoning = "; ".join(reasons) if reasons else "默认判断"
        return TimingDecision.STAY_SILENT, min(1.0, confidence), reasoning

    def judge_confirmation_timing(
        self,
        context: PredictionContext,
        action: str,
    ) -> tuple:
        """判断确认时机"""
        confidence = 0.5
        reasons: List[str] = []

        action_lower = action.lower()

        # 检查高风险操作
        high_risk_keywords = [
            "delete",
            "remove",
            "drop",
            "reset",
            "force",
            "删除",
            "移除",
            "重置",
            "强制",
        ]
        for keyword in high_risk_keywords:
            if keyword in action_lower:
                confidence += 0.3
                reasons.append(f"高风险操作: {keyword}")
                break

        # 检查不可逆操作
        irreversible_keywords = [
            "permanent",
            "irreversible",
            "cannot undo",
            "永久",
            "不可逆",
            "无法撤销",
        ]
        for keyword in irreversible_keywords:
            if keyword in action_lower:
                confidence += 0.35
                reasons.append(f"不可逆操作: {keyword}")
                break

        # 检查影响范围
        scope_keywords = [
            "all",
            "entire",
            "global",
            "production",
            "全部",
            "整个",
            "全局",
            "生产",
        ]
        for keyword in scope_keywords:
            if keyword in action_lower:
                confidence += 0.2
                reasons.append(f"大范围影响: {keyword}")
                break

        # 检查用户偏好
        user_profile = context.user_profile
        if user_profile:
            interaction_style = user_profile.get("preferences", {}).get(
                "interaction_style", {}
            )
            if interaction_style.get("prefers_confirmation", False):
                confidence += 0.15
                reasons.append("用户偏好确认")

        reasoning = "; ".join(reasons) if reasons else "默认判断"
        return TimingDecision.ASK_CONFIRMATION, min(1.0, confidence), reasoning


class TimingJudge:
    """时机判断器

    判断何时主动提供帮助，基于用户偏好和当前上下文进行决策。
    """

    # 建议行动模板
    SUGGESTED_ACTIONS: Dict[TimingDecision, Dict[str, str]] = {
        TimingDecision.OFFER_HELP: {
            "stuck": "主动提供解决方案或调试建议",
            "error": "解释错误原因并提供修复建议",
            "exploring": "提供相关文档或示例代码",
            "default": "提供相关帮助信息",
        },
        TimingDecision.STAY_SILENT: {
            "busy": "等待用户完成当前工作",
            "focused": "不打断用户的专注状态",
            "default": "保持沉默，等待用户主动请求",
        },
        TimingDecision.ASK_CONFIRMATION: {
            "risky": "确认用户是否要执行此操作",
            "ambiguous": "澄清用户的具体需求",
            "default": "请求用户确认后再执行",
        },
        TimingDecision.WAIT_FOR_MORE_CONTEXT: {
            "incomplete": "等待更多上下文信息",
            "unclear": "等待用户提供更多细节",
            "default": "收集更多信息后再决策",
        },
    }

    # 延迟时间配置（秒）
    DELAY_CONFIG: Dict[TimingDecision, Dict[str, float]] = {
        TimingDecision.OFFER_HELP: {
            "critical": 0.0,
            "high": 1.0,
            "medium": 3.0,
            "low": 5.0,
            "default": 2.0,
        },
        TimingDecision.STAY_SILENT: {
            "default": 0.0,
        },
        TimingDecision.ASK_CONFIRMATION: {
            "default": 0.5,
        },
        TimingDecision.WAIT_FOR_MORE_CONTEXT: {
            "default": 5.0,
        },
    }

    def __init__(
        self,
        strategy: JudgmentStrategy = JudgmentStrategy.BALANCED,
        llm_client=None,
    ) -> None:
        """初始化时机判断器

        Args:
            strategy: 判断策略
            llm_client: LLM客户端（可选，用于智能判断）
        """
        self._strategy = strategy
        self._rule_judge = RuleBasedJudge()
        self._llm_client = llm_client

    @property
    def strategy(self) -> JudgmentStrategy:
        """获取当前判断策略"""
        return self._strategy

    @strategy.setter
    def strategy(self, value: JudgmentStrategy) -> None:
        """设置判断策略"""
        self._strategy = value

    def _llm_judge_timing(self, context: PredictionContext) -> Optional[Dict[str, Any]]:
        """使用LLM进行时机判断

        Args:
            context: 预测上下文

        Returns:
            包含user_state、urgency_level、should_interact、reasoning、confidence的字典
            如果LLM调用失败，返回None
        """
        if not self._llm_client:
            return None

        try:
            # 构建LLM prompt
            user_input = context.current_message or ""
            project_info = ""
            if context.project_state:
                project_info = f"""项目状态:
- 有错误: {context.project_state.get("has_errors", False)}
- 构建失败: {context.project_state.get("build_failed", False)}
- 测试失败: {context.project_state.get("tests_failing", False)}
"""

            code_info = ""
            if context.code_context:
                modified_files = context.code_context.get("modified_files", [])
                code_info = f"代码上下文: 修改了{len(modified_files)}个文件"

            prompt = f"""你是一个用户状态分析专家。请分析用户当前的行为和上下文，判断服务时机。

用户输入：{user_input}
{project_info}
{code_info}

请返回JSON格式的判断结果：
{{
  "user_state": "stuck/busy/exploring/focused/idle",
  "urgency_level": "critical/high/medium/low/none",
  "should_interact": true/false,
  "reasoning": "判断依据",
  "confidence": 0.9
}}

只返回JSON，不要有其他内容。"""

            # 调用LLM
            response = self._llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
            )

            # 解析响应
            import json

            result: Dict[str, Any] = json.loads(response.content.strip())

            # 验证返回结果
            required_fields = [
                "user_state",
                "urgency_level",
                "should_interact",
                "reasoning",
                "confidence",
            ]
            if not all(field in result for field in required_fields):
                return None

            return result

        except Exception:
            # LLM调用失败，返回None触发降级
            return None

    def should_offer_help(self, context: PredictionContext) -> TimingResult:
        """判断是否应该主动提供帮助

        基于用户状态和紧急程度判断是否应该主动提供帮助。
        规则引擎优先，LLM作为兜底增强。

        Args:
            context: 预测上下文

        Returns:
            时机判断结果
        """
        # 【优化】优先使用规则引擎判断
        # 分析用户状态
        user_state = self._rule_judge.analyze_user_state(context)

        # 分析紧急程度
        urgency = self._rule_judge.analyze_urgency(context)

        # 获取基础判断
        decision, confidence, reasoning = self._rule_judge.judge_help_timing(
            user_state, urgency
        )

        # 应用策略调整
        decision, confidence = self._apply_strategy_adjustment(
            decision, confidence, "offer_help"
        )

        # 应用用户偏好调整
        decision, confidence = self._apply_user_preference_adjustment(
            context, decision, confidence
        )

        # 【优化】规则引擎置信度足够高时，直接返回（规则优先）
        RULE_CONFIDENCE_THRESHOLD = 0.6
        if confidence >= RULE_CONFIDENCE_THRESHOLD:
            # 生成建议行动
            suggested_action = self._get_suggested_action(
                decision, user_state.state, urgency.level
            )

            # 计算延迟时间
            delay = self._get_delay(decision, urgency.level)

            # 过程打印
            PrettyOutput.auto_print(
                f"⏰  时机判断: 用户状态={user_state.state.value}, 紧急度={urgency.level.value} "
                f"(模式: 规则, 置信度={confidence:.2f})"
            )

            return TimingResult(
                decision=decision,
                confidence_score=confidence,
                reasoning=reasoning,
                suggested_action=suggested_action,
                delay_seconds=delay,
            )

        # 【兜底】规则引擎置信度不足时，尝试LLM增强（如果可用）
        llm_result = self._llm_judge_timing(context)

        if llm_result:
            # LLM判断成功，使用LLM结果增强规则判断
            try:
                # 解析LLM结果
                # user_state_str = llm_result["user_state"]  # 保留规则引擎的user_state
                urgency_str = llm_result["urgency_level"]
                should_interact = llm_result["should_interact"]
                llm_reasoning = llm_result["reasoning"]
                llm_confidence = llm_result["confidence"]

                # 转换为枚举类型
                # llm_user_state = UserState(UserState[user_state_str.upper()])  # 保留规则引擎的user_state
                llm_urgency = UrgencyLevel(UrgencyLevel[urgency_str.upper()])

                # 根据should_interact决定决策
                if should_interact:
                    if llm_urgency in (UrgencyLevel.CRITICAL, UrgencyLevel.HIGH):
                        llm_decision = TimingDecision.OFFER_HELP
                    else:
                        llm_decision = TimingDecision.ASK_CONFIRMATION
                else:
                    llm_decision = TimingDecision.STAY_SILENT

                # 综合规则和LLM的判断（加权平均）
                # 给予规则结果更高权重（0.6），因为规则更稳定
                final_confidence = confidence * 0.6 + llm_confidence * 0.4

                # 如果LLM和规则决策一致，增强置信度
                if llm_decision == decision:
                    final_confidence = min(1.0, final_confidence + 0.1)
                    reasoning = f"{reasoning} | LLM增强: {llm_reasoning}"
                else:
                    # 如果不一致，保留规则的决策（更保守）
                    reasoning = (
                        f"{reasoning} | LLM建议: {llm_decision.value} ({llm_reasoning})"
                    )

                # 重新应用调整（使用综合后的置信度）
                decision, final_confidence = self._apply_strategy_adjustment(
                    decision, final_confidence, "offer_help"
                )

                # 生成建议行动
                suggested_action = self._get_suggested_action(
                    decision, user_state.state, urgency.level
                )

                # 计算延迟时间
                delay = self._get_delay(decision, urgency.level)

                # 过程打印
                PrettyOutput.auto_print(
                    f"⏰  时机判断: 用户状态={user_state.state.value}, 紧急度={urgency.level.value} "
                    f"(模式: 混合, 规则={confidence:.2f}, LLM={llm_confidence:.2f})"
                )

                return TimingResult(
                    decision=decision,
                    confidence_score=final_confidence,
                    reasoning=reasoning,
                    suggested_action=suggested_action,
                    delay_seconds=delay,
                )

            except Exception:
                # LLM结果解析失败，继续使用规则结果
                pass

        # LLM不可用或失败，直接使用规则结果
        # 【优化】在PROACTIVE策略下，提高规则结果的置信度，使其更容易达到阈值
        if self._strategy == JudgmentStrategy.PROACTIVE:
            # PROACTIVE策略：提高置信度，让规则更容易触发
            confidence = min(1.0, confidence + 0.15)
            # 如果是STAY_SILENT决策，尝试改为更主动的决策
            if decision == TimingDecision.STAY_SILENT:
                # 根据用户状态决定是否改为ASK_CONFIRMATION
                # PROACTIVE策略：除了FOCUSED状态外，其他状态都应该主动询问
                if user_state.state in (
                    UserState.EXPLORING,
                    UserState.IDLE,
                    UserState.UNKNOWN,
                    UserState.BUSY,  # 添加BUSY状态
                ):
                    decision = TimingDecision.ASK_CONFIRMATION
                    reasoning += " | PROACTIVE策略：主动询问确认"

        # 生成建议行动
        suggested_action = self._get_suggested_action(
            decision, user_state.state, urgency.level
        )

        # 计算延迟时间
        delay = self._get_delay(decision, urgency.level)

        # 过程打印
        PrettyOutput.auto_print(
            f"⏰  时机判断: 用户状态={user_state.state.value}, 紧急度={urgency.level.value} "
            f"(模式: 规则兜底, 置信度={confidence:.2f})"
        )

        return TimingResult(
            decision=decision,
            confidence_score=confidence,
            reasoning=reasoning,
            suggested_action=suggested_action,
            delay_seconds=delay,
        )

    def should_stay_silent(self, context: PredictionContext) -> TimingResult:
        """判断是否应该保持沉默

        基于用户状态和偏好判断是否应该保持沉默。

        Args:
            context: 预测上下文

        Returns:
            时机判断结果
        """
        # 分析用户状态
        user_state = self._rule_judge.analyze_user_state(context)

        # 获取基础判断
        decision, confidence, reasoning = self._rule_judge.judge_silence_timing(
            context, user_state
        )

        # 应用策略调整
        decision, confidence = self._apply_strategy_adjustment(
            decision, confidence, "stay_silent"
        )

        # 生成建议行动
        suggested_action = self._get_suggested_action(
            decision, user_state.state, UrgencyLevel.NONE
        )

        return TimingResult(
            decision=decision,
            confidence_score=confidence,
            reasoning=reasoning,
            suggested_action=suggested_action,
            delay_seconds=0.0,
        )

    def should_ask_confirmation(
        self,
        context: PredictionContext,
        action: str,
    ) -> TimingResult:
        """判断是否应该请求确认

        基于操作风险和用户偏好判断是否应该请求确认。

        Args:
            context: 预测上下文
            action: 待执行的操作描述

        Returns:
            时机判断结果
        """
        if not action:
            return TimingResult(
                decision=TimingDecision.WAIT_FOR_MORE_CONTEXT,
                confidence_score=0.5,
                reasoning="操作描述为空",
                suggested_action="等待操作描述",
                delay_seconds=0.0,
            )

        # 获取基础判断
        decision, confidence, reasoning = self._rule_judge.judge_confirmation_timing(
            context, action
        )

        # 应用策略调整
        decision, confidence = self._apply_strategy_adjustment(
            decision, confidence, "ask_confirmation"
        )

        # 生成建议行动
        suggested_action = self._get_suggested_action(
            decision, UserState.UNKNOWN, UrgencyLevel.MEDIUM
        )

        return TimingResult(
            decision=decision,
            confidence_score=confidence,
            reasoning=reasoning,
            suggested_action=suggested_action,
            delay_seconds=self.DELAY_CONFIG[TimingDecision.ASK_CONFIRMATION]["default"],
        )

    def _apply_strategy_adjustment(
        self,
        decision: TimingDecision,
        confidence: float,
        judgment_type: str,
    ) -> tuple:
        """应用策略调整"""
        if self._strategy == JudgmentStrategy.CONSERVATIVE:
            # 保守策略：倾向于保持沉默
            if judgment_type == "offer_help":
                if decision == TimingDecision.OFFER_HELP and confidence < 0.8:
                    decision = TimingDecision.ASK_CONFIRMATION
                    confidence *= 0.9
            elif judgment_type == "stay_silent":
                confidence = min(1.0, confidence * 1.1)

        elif self._strategy == JudgmentStrategy.PROACTIVE:
            # 主动策略：倾向于提供帮助
            if judgment_type == "offer_help":
                if decision == TimingDecision.ASK_CONFIRMATION:
                    decision = TimingDecision.OFFER_HELP
                    confidence *= 0.95
                elif decision == TimingDecision.WAIT_FOR_MORE_CONTEXT:
                    decision = TimingDecision.ASK_CONFIRMATION
                    confidence *= 0.9
            elif judgment_type == "stay_silent":
                confidence = max(0.3, confidence * 0.85)

        # BALANCED策略不做调整
        return decision, confidence

    def _apply_user_preference_adjustment(
        self,
        context: PredictionContext,
        decision: TimingDecision,
        confidence: float,
    ) -> tuple:
        """应用用户偏好调整"""
        user_profile = context.user_profile
        if not user_profile:
            return decision, confidence

        preferences = user_profile.get("preferences", {})
        interaction_style = preferences.get("interaction_style", {})

        # 检查用户偏好的交互风格
        preferred_style = interaction_style.get("preferred_style", "")
        if preferred_style in ("proactive", "helpful", "detailed"):
            # 用户喜欢主动帮助
            if decision == TimingDecision.STAY_SILENT:
                confidence *= 0.8
            elif decision == TimingDecision.OFFER_HELP:
                confidence = min(1.0, confidence * 1.1)
        elif preferred_style in ("minimal", "quiet", "non-intrusive"):
            # 用户喜欢最小干扰
            if decision == TimingDecision.OFFER_HELP:
                confidence *= 0.85
            elif decision == TimingDecision.STAY_SILENT:
                confidence = min(1.0, confidence * 1.1)

        # 检查帮助接受率
        help_history = user_profile.get("help_history", {})
        acceptance_rate = help_history.get("acceptance_rate", 0.5)
        if acceptance_rate < 0.3:
            # 用户经常拒绝帮助
            if decision == TimingDecision.OFFER_HELP:
                decision = TimingDecision.ASK_CONFIRMATION
                confidence *= 0.9
        elif acceptance_rate > 0.8:
            # 用户经常接受帮助
            if decision == TimingDecision.ASK_CONFIRMATION:
                confidence = min(1.0, confidence * 1.05)

        return decision, confidence

    def _get_suggested_action(
        self,
        decision: TimingDecision,
        user_state: UserState,
        urgency_level: UrgencyLevel,
    ) -> str:
        """获取建议行动"""
        action_templates = self.SUGGESTED_ACTIONS.get(decision, {})

        # 根据用户状态选择建议
        if user_state == UserState.STUCK:
            return action_templates.get("stuck", action_templates.get("default", ""))
        elif user_state == UserState.BUSY:
            return action_templates.get("busy", action_templates.get("default", ""))
        elif user_state == UserState.FOCUSED:
            return action_templates.get("focused", action_templates.get("default", ""))
        elif user_state == UserState.EXPLORING:
            return action_templates.get(
                "exploring", action_templates.get("default", "")
            )

        return action_templates.get("default", "")

    def _get_delay(
        self,
        decision: TimingDecision,
        urgency_level: UrgencyLevel,
    ) -> float:
        """获取延迟时间"""
        delay_config = self.DELAY_CONFIG.get(decision, {})

        # 根据紧急程度选择延迟
        urgency_key = urgency_level.value
        if urgency_key in delay_config:
            return delay_config[urgency_key]

        return delay_config.get("default", 0.0)
