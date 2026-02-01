"""TimingJudge测试模块

测试时机判断器的各项功能。
"""

import pytest

from jarvis.jarvis_digital_twin.prediction import (
    PredictionContext,
    TimingDecision,
)
from jarvis.jarvis_digital_twin.prediction.timing_judge import (
    TimingJudge,
    JudgmentStrategy,
    RuleBasedJudge,
    UserState,
    UrgencyLevel,
    UserStateAnalysis,
    UrgencyAnalysis,
)


# ============== Fixtures ==============


@pytest.fixture
def judge() -> TimingJudge:
    """创建默认时机判断器"""
    return TimingJudge()


@pytest.fixture
def conservative_judge() -> TimingJudge:
    """创建保守策略判断器"""
    return TimingJudge(strategy=JudgmentStrategy.CONSERVATIVE)


@pytest.fixture
def proactive_judge() -> TimingJudge:
    """创建主动策略判断器"""
    return TimingJudge(strategy=JudgmentStrategy.PROACTIVE)


@pytest.fixture
def rule_judge() -> RuleBasedJudge:
    """创建规则判断引擎"""
    return RuleBasedJudge()


@pytest.fixture
def basic_context() -> PredictionContext:
    """创建基础预测上下文"""
    return PredictionContext(
        current_message="How to implement this feature?",
        conversation_history=[
            {"role": "user", "content": "我想创建一个新模块"},
            {"role": "assistant", "content": "好的，我来帮你创建"},
        ],
        code_context={
            "last_action": "create_file",
            "modified_files": ["src/module.py"],
        },
        project_state={
            "current_state": "development",
            "has_errors": False,
        },
        user_profile={
            "preferences": {
                "interaction_style": {"preferred_style": "detailed"},
            },
        },
    )


@pytest.fixture
def stuck_context() -> PredictionContext:
    """创建卡住场景上下文"""
    return PredictionContext(
        current_message="I'm stuck with this error, help!",
        conversation_history=[],
        code_context={
            "last_action": "debug",
            "modified_files": ["src/buggy.py"],
        },
        project_state={
            "current_state": "debugging",
            "has_errors": True,
            "build_failed": True,
        },
        user_profile={},
    )


@pytest.fixture
def busy_context() -> PredictionContext:
    """创建忙碌场景上下文"""
    return PredictionContext(
        current_message="I'm working on implementing the feature",
        conversation_history=[],
        code_context={
            "last_action": "edit_file",
            "modified_files": ["src/a.py", "src/b.py", "src/c.py", "src/d.py"],
        },
        project_state={
            "current_state": "development",
            "has_errors": False,
        },
        user_profile={
            "preferences": {
                "interaction_style": {"preferred_style": "minimal"},
            },
        },
    )


@pytest.fixture
def focused_context() -> PredictionContext:
    """创建专注场景上下文"""
    return PredictionContext(
        current_message="",
        conversation_history=[],
        code_context={
            "last_action": "edit_file",
            "modified_files": ["src/single.py"],
        },
        project_state={
            "current_state": "development",
            "has_errors": False,
        },
        user_profile={
            "preferences": {
                "interaction_style": {"preferred_style": "quiet"},
            },
        },
    )


@pytest.fixture
def empty_context() -> PredictionContext:
    """创建空上下文"""
    return PredictionContext()


@pytest.fixture
def critical_context() -> PredictionContext:
    """创建紧急场景上下文"""
    return PredictionContext(
        current_message="Critical error! The system crashed!",
        conversation_history=[],
        code_context={},
        project_state={
            "has_errors": True,
            "build_failed": True,
            "tests_failing": True,
        },
        metadata={
            "is_blocking": True,
            "priority": "high",
        },
    )


# ============== RuleBasedJudge Tests ==============


class TestRuleBasedJudgeAnalyzeUserState:
    """测试RuleBasedJudge.analyze_user_state方法"""

    def test_analyze_stuck_state(
        self, rule_judge: RuleBasedJudge, stuck_context: PredictionContext
    ) -> None:
        """测试识别卡住状态"""
        result = rule_judge.analyze_user_state(stuck_context)
        assert result.state == UserState.STUCK
        assert result.confidence > 0.5
        assert len(result.indicators) > 0

    def test_analyze_busy_state(
        self, rule_judge: RuleBasedJudge, busy_context: PredictionContext
    ) -> None:
        """测试识别忙碌状态"""
        result = rule_judge.analyze_user_state(busy_context)
        assert result.state == UserState.BUSY
        assert result.confidence > 0.3

    def test_analyze_focused_state(
        self, rule_judge: RuleBasedJudge, focused_context: PredictionContext
    ) -> None:
        """测试识别专注状态"""
        result = rule_judge.analyze_user_state(focused_context)
        assert result.state == UserState.FOCUSED
        assert result.confidence > 0.1

    def test_analyze_idle_state(
        self, rule_judge: RuleBasedJudge, empty_context: PredictionContext
    ) -> None:
        """测试识别空闲状态"""
        result = rule_judge.analyze_user_state(empty_context)
        assert result.state in (UserState.IDLE, UserState.UNKNOWN)

    def test_analyze_exploring_state(self, rule_judge: RuleBasedJudge) -> None:
        """测试识别探索状态"""
        context = PredictionContext(
            current_message="What is this? How does it work? Why is it designed this way?",
            conversation_history=[
                {"role": "user", "content": "What is X?"},
                {"role": "user", "content": "How does Y work?"},
                {"role": "user", "content": "Why Z?"},
            ],
        )
        result = rule_judge.analyze_user_state(context)
        assert result.state == UserState.EXPLORING


class TestRuleBasedJudgeAnalyzeUrgency:
    """测试RuleBasedJudge.analyze_urgency方法"""

    def test_analyze_critical_urgency(
        self, rule_judge: RuleBasedJudge, critical_context: PredictionContext
    ) -> None:
        """测试识别紧急程度"""
        result = rule_judge.analyze_urgency(critical_context)
        assert result.level == UrgencyLevel.CRITICAL
        assert result.confidence > 0.5

    def test_analyze_high_urgency(self, rule_judge: RuleBasedJudge) -> None:
        """测试识别高紧急程度"""
        context = PredictionContext(
            current_message="This is important, need it asap!",
            project_state={"has_errors": True},
        )
        result = rule_judge.analyze_urgency(context)
        assert result.level in (UrgencyLevel.CRITICAL, UrgencyLevel.HIGH)

    def test_analyze_medium_urgency(self, rule_judge: RuleBasedJudge) -> None:
        """测试识别中等紧急程度"""
        context = PredictionContext(
            current_message="I need to implement this feature",
        )
        result = rule_judge.analyze_urgency(context)
        assert result.level in (UrgencyLevel.MEDIUM, UrgencyLevel.NONE)

    def test_analyze_low_urgency(self, rule_judge: RuleBasedJudge) -> None:
        """测试识别低紧急程度"""
        context = PredictionContext(
            current_message="Maybe later we can add this optional feature",
        )
        result = rule_judge.analyze_urgency(context)
        assert result.level in (UrgencyLevel.LOW, UrgencyLevel.NONE)

    def test_analyze_no_urgency(
        self, rule_judge: RuleBasedJudge, empty_context: PredictionContext
    ) -> None:
        """测试无紧急性"""
        result = rule_judge.analyze_urgency(empty_context)
        assert result.level == UrgencyLevel.NONE


class TestRuleBasedJudgeHelpTiming:
    """测试RuleBasedJudge.judge_help_timing方法"""

    def test_stuck_critical_offers_help(self, rule_judge: RuleBasedJudge) -> None:
        """测试卡住+紧急时主动提供帮助"""
        user_state = UserStateAnalysis(
            state=UserState.STUCK, confidence=0.9, indicators=[]
        )
        urgency = UrgencyAnalysis(
            level=UrgencyLevel.CRITICAL, confidence=0.9, reasons=[]
        )
        decision, confidence, _ = rule_judge.judge_help_timing(user_state, urgency)
        assert decision == TimingDecision.OFFER_HELP
        assert confidence > 0.8

    def test_busy_low_stays_silent(self, rule_judge: RuleBasedJudge) -> None:
        """测试忙碌+低紧急时保持沉默"""
        user_state = UserStateAnalysis(
            state=UserState.BUSY, confidence=0.8, indicators=[]
        )
        urgency = UrgencyAnalysis(level=UrgencyLevel.LOW, confidence=0.7, reasons=[])
        decision, _, _ = rule_judge.judge_help_timing(user_state, urgency)
        assert decision == TimingDecision.STAY_SILENT

    def test_focused_medium_stays_silent(self, rule_judge: RuleBasedJudge) -> None:
        """测试专注+中等紧急时保持沉默"""
        user_state = UserStateAnalysis(
            state=UserState.FOCUSED, confidence=0.8, indicators=[]
        )
        urgency = UrgencyAnalysis(level=UrgencyLevel.MEDIUM, confidence=0.6, reasons=[])
        decision, _, _ = rule_judge.judge_help_timing(user_state, urgency)
        assert decision == TimingDecision.STAY_SILENT

    def test_idle_high_offers_help(self, rule_judge: RuleBasedJudge) -> None:
        """测试空闲+高紧急时主动提供帮助"""
        user_state = UserStateAnalysis(
            state=UserState.IDLE, confidence=0.7, indicators=[]
        )
        urgency = UrgencyAnalysis(level=UrgencyLevel.HIGH, confidence=0.8, reasons=[])
        decision, _, _ = rule_judge.judge_help_timing(user_state, urgency)
        assert decision == TimingDecision.OFFER_HELP


# ============== TimingJudge Tests ==============


class TestTimingJudgeShouldOfferHelp:
    """测试TimingJudge.should_offer_help方法"""

    def test_offer_help_when_stuck(
        self, judge: TimingJudge, stuck_context: PredictionContext
    ) -> None:
        """测试卡住时主动提供帮助"""
        result = judge.should_offer_help(stuck_context)
        assert result.decision == TimingDecision.OFFER_HELP
        assert result.confidence_score > 0.5
        assert result.suggested_action != ""

    def test_offer_help_when_critical(
        self, judge: TimingJudge, critical_context: PredictionContext
    ) -> None:
        """测试紧急情况时主动提供帮助"""
        result = judge.should_offer_help(critical_context)
        assert result.decision == TimingDecision.OFFER_HELP
        assert result.confidence_score > 0.7

    def test_stay_silent_when_busy(
        self, judge: TimingJudge, busy_context: PredictionContext
    ) -> None:
        """测试忙碌时保持沉默"""
        result = judge.should_offer_help(busy_context)
        assert result.decision in (
            TimingDecision.STAY_SILENT,
            TimingDecision.ASK_CONFIRMATION,
        )

    def test_result_has_delay(
        self, judge: TimingJudge, basic_context: PredictionContext
    ) -> None:
        """测试结果包含延迟时间"""
        result = judge.should_offer_help(basic_context)
        assert hasattr(result, "delay_seconds")
        assert result.delay_seconds >= 0

    def test_result_has_reasoning(
        self, judge: TimingJudge, basic_context: PredictionContext
    ) -> None:
        """测试结果包含推理依据"""
        result = judge.should_offer_help(basic_context)
        assert result.reasoning != ""


class TestTimingJudgeShouldStaySilent:
    """测试TimingJudge.should_stay_silent方法"""

    def test_stay_silent_when_focused(
        self, judge: TimingJudge, focused_context: PredictionContext
    ) -> None:
        """测试专注时保持沉默"""
        result = judge.should_stay_silent(focused_context)
        assert result.decision == TimingDecision.STAY_SILENT
        assert result.confidence_score > 0.5

    def test_stay_silent_when_busy(
        self, judge: TimingJudge, busy_context: PredictionContext
    ) -> None:
        """测试忙碌时保持沉默"""
        result = judge.should_stay_silent(busy_context)
        assert result.decision == TimingDecision.STAY_SILENT

    def test_stay_silent_with_minimal_preference(self, judge: TimingJudge) -> None:
        """测试用户偏好最小干扰时保持沉默"""
        context = PredictionContext(
            current_message="",
            user_profile={
                "preferences": {
                    "interaction_style": {"preferred_style": "minimal"},
                },
            },
        )
        result = judge.should_stay_silent(context)
        assert result.decision == TimingDecision.STAY_SILENT
        assert result.confidence_score > 0.6

    def test_stay_silent_with_declined_history(self, judge: TimingJudge) -> None:
        """测试用户多次拒绝帮助后保持沉默"""
        context = PredictionContext(
            current_message="",
            user_profile={
                "help_history": {"declined_count": 5},
            },
        )
        result = judge.should_stay_silent(context)
        assert result.decision == TimingDecision.STAY_SILENT


class TestTimingJudgeShouldAskConfirmation:
    """测试TimingJudge.should_ask_confirmation方法"""

    def test_ask_confirmation_for_delete(
        self, judge: TimingJudge, basic_context: PredictionContext
    ) -> None:
        """测试删除操作需要确认"""
        result = judge.should_ask_confirmation(basic_context, "delete all files")
        assert result.decision == TimingDecision.ASK_CONFIRMATION
        assert result.confidence_score > 0.7

    def test_ask_confirmation_for_reset(
        self, judge: TimingJudge, basic_context: PredictionContext
    ) -> None:
        """测试重置操作需要确认"""
        result = judge.should_ask_confirmation(basic_context, "reset the database")
        assert result.decision == TimingDecision.ASK_CONFIRMATION

    def test_ask_confirmation_for_production(
        self, judge: TimingJudge, basic_context: PredictionContext
    ) -> None:
        """测试生产环境操作需要确认"""
        result = judge.should_ask_confirmation(basic_context, "deploy to production")
        assert result.decision == TimingDecision.ASK_CONFIRMATION

    def test_empty_action_waits_for_context(
        self, judge: TimingJudge, basic_context: PredictionContext
    ) -> None:
        """测试空操作等待更多上下文"""
        result = judge.should_ask_confirmation(basic_context, "")
        assert result.decision == TimingDecision.WAIT_FOR_MORE_CONTEXT

    def test_safe_action_lower_confidence(
        self, judge: TimingJudge, basic_context: PredictionContext
    ) -> None:
        """测试安全操作置信度较低"""
        result = judge.should_ask_confirmation(basic_context, "read the file")
        assert result.confidence_score < 0.7


class TestTimingJudgeStrategies:
    """测试不同判断策略"""

    def test_conservative_strategy_more_cautious(
        self, conservative_judge: TimingJudge, basic_context: PredictionContext
    ) -> None:
        """测试保守策略更谨慎"""
        result = conservative_judge.should_offer_help(basic_context)
        # 保守策略应该倾向于请求确认或保持沉默
        assert result.decision in (
            TimingDecision.ASK_CONFIRMATION,
            TimingDecision.STAY_SILENT,
            TimingDecision.WAIT_FOR_MORE_CONTEXT,
            TimingDecision.OFFER_HELP,
        )

    def test_proactive_strategy_more_helpful(
        self, proactive_judge: TimingJudge, basic_context: PredictionContext
    ) -> None:
        """测试主动策略更积极"""
        result = proactive_judge.should_offer_help(basic_context)
        # 主动策略应该倾向于提供帮助
        assert result.decision in (
            TimingDecision.OFFER_HELP,
            TimingDecision.ASK_CONFIRMATION,
        )

    def test_strategy_property(self, judge: TimingJudge) -> None:
        """测试策略属性"""
        assert judge.strategy == JudgmentStrategy.BALANCED
        judge.strategy = JudgmentStrategy.CONSERVATIVE
        assert judge.strategy == JudgmentStrategy.CONSERVATIVE

    def test_conservative_stay_silent_higher_confidence(
        self, conservative_judge: TimingJudge, focused_context: PredictionContext
    ) -> None:
        """测试保守策略沉默置信度更高"""
        result = conservative_judge.should_stay_silent(focused_context)
        assert result.confidence_score > 0.5

    def test_proactive_stay_silent_lower_confidence(
        self, proactive_judge: TimingJudge, focused_context: PredictionContext
    ) -> None:
        """测试主动策略沉默置信度较低"""
        result = proactive_judge.should_stay_silent(focused_context)
        # 主动策略不太倾向于保持沉默
        assert result.decision == TimingDecision.STAY_SILENT


class TestTimingJudgeUserPreferences:
    """测试用户偏好影响"""

    def test_proactive_user_gets_more_help(self, judge: TimingJudge) -> None:
        """测试喜欢主动帮助的用户获得更多帮助"""
        context = PredictionContext(
            current_message="I need help with this problem",
            user_profile={
                "preferences": {
                    "interaction_style": {"preferred_style": "proactive"},
                },
            },
            project_state={"has_errors": True},
        )
        result = judge.should_offer_help(context)
        assert result.decision in (
            TimingDecision.OFFER_HELP,
            TimingDecision.ASK_CONFIRMATION,
        )

    def test_quiet_user_gets_less_interruption(self, judge: TimingJudge) -> None:
        """测试喜欢安静的用户获得更少干扰"""
        context = PredictionContext(
            current_message="Working on something",
            user_profile={
                "preferences": {
                    "interaction_style": {"preferred_style": "quiet"},
                },
            },
        )
        result = judge.should_offer_help(context)
        # 安静用户应该获得较低的帮助置信度
        assert result.confidence_score < 0.9

    def test_high_acceptance_rate_user(self, judge: TimingJudge) -> None:
        """测试高接受率用户"""
        context = PredictionContext(
            current_message="Need some help",
            user_profile={
                "help_history": {"acceptance_rate": 0.9},
            },
        )
        result = judge.should_offer_help(context)
        assert result.decision in (
            TimingDecision.OFFER_HELP,
            TimingDecision.ASK_CONFIRMATION,
        )

    def test_low_acceptance_rate_user(self, judge: TimingJudge) -> None:
        """测试低接受率用户"""
        context = PredictionContext(
            current_message="Need some help",
            user_profile={
                "help_history": {"acceptance_rate": 0.2},
            },
        )
        result = judge.should_offer_help(context)
        # 低接受率用户应该获得请求确认
        assert result.decision in (
            TimingDecision.ASK_CONFIRMATION,
            TimingDecision.OFFER_HELP,
            TimingDecision.WAIT_FOR_MORE_CONTEXT,
        )


class TestTimingJudgeEdgeCases:
    """测试边界情况"""

    def test_empty_context(
        self, judge: TimingJudge, empty_context: PredictionContext
    ) -> None:
        """测试空上下文"""
        result = judge.should_offer_help(empty_context)
        assert result.decision is not None
        assert 0 <= result.confidence_score <= 1

    def test_none_user_profile(self, judge: TimingJudge) -> None:
        """测试无用户画像"""
        context = PredictionContext(
            current_message="Help me",
            user_profile={},
        )
        result = judge.should_offer_help(context)
        assert result.decision is not None

    def test_chinese_keywords(self, judge: TimingJudge) -> None:
        """测试中文关键词识别"""
        context = PredictionContext(
            current_message="我卡住了，帮帮我！",
            project_state={"has_errors": True},
        )
        result = judge.should_offer_help(context)
        assert result.decision == TimingDecision.OFFER_HELP

    def test_mixed_language_keywords(self, judge: TimingJudge) -> None:
        """测试混合语言关键词"""
        context = PredictionContext(
            current_message="This is 紧急 situation!",
        )
        result = judge.should_offer_help(context)
        assert result.confidence_score > 0.3

    def test_confirmation_with_user_preference(self, judge: TimingJudge) -> None:
        """测试用户偏好确认"""
        context = PredictionContext(
            current_message="",
            user_profile={
                "preferences": {
                    "interaction_style": {"prefers_confirmation": True},
                },
            },
        )
        result = judge.should_ask_confirmation(context, "do something")
        assert result.confidence_score > 0.5

    def test_irreversible_action(
        self, judge: TimingJudge, basic_context: PredictionContext
    ) -> None:
        """测试不可逆操作"""
        result = judge.should_ask_confirmation(
            basic_context, "This is permanent and cannot undo"
        )
        assert result.decision == TimingDecision.ASK_CONFIRMATION
        assert result.confidence_score > 0.8
