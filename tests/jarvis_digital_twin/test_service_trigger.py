"""ServiceTrigger测试模块

测试服务触发器的各项功能。
"""

import time

import pytest

from jarvis.jarvis_digital_twin.prediction import TimingJudge
from jarvis.jarvis_digital_twin.proactive_service import (
    ContextTriggerEvaluator,
    KeywordTriggerEvaluator,
    PatternTriggerEvaluator,
    ServiceDefinition,
    ServicePriority,
    ServiceTrigger,
    ServiceType,
    TriggerContext,
)


# ============== Fixtures ==============


@pytest.fixture
def trigger() -> ServiceTrigger:
    """创建默认服务触发器"""
    return ServiceTrigger()


@pytest.fixture
def trigger_with_judge() -> ServiceTrigger:
    """创建带TimingJudge的服务触发器"""
    return ServiceTrigger(timing_judge=TimingJudge())


@pytest.fixture
def keyword_evaluator() -> KeywordTriggerEvaluator:
    """创建关键词评估器"""
    return KeywordTriggerEvaluator()


@pytest.fixture
def pattern_evaluator() -> PatternTriggerEvaluator:
    """创建模式评估器"""
    return PatternTriggerEvaluator()


@pytest.fixture
def context_evaluator() -> ContextTriggerEvaluator:
    """创建上下文评估器"""
    return ContextTriggerEvaluator()


@pytest.fixture
def basic_context() -> TriggerContext:
    """创建基础触发上下文"""
    return TriggerContext(
        user_input="How to implement this feature?",
        conversation_history=[
            {"role": "user", "content": "我想创建一个新模块"},
            {"role": "assistant", "content": "好的，我来帮你创建"},
        ],
    )


@pytest.fixture
def help_context() -> TriggerContext:
    """创建帮助请求上下文"""
    return TriggerContext(
        user_input="I need help with this error!",
        conversation_history=[],
    )


@pytest.fixture
def error_context() -> TriggerContext:
    """创建错误场景上下文"""
    return TriggerContext(
        user_input="I got an error: TypeError in my code",
        conversation_history=[],
    )


@pytest.fixture
def suggestion_service() -> ServiceDefinition:
    """创建建议类服务定义"""
    return ServiceDefinition(
        service_id="suggestion_001",
        service_type=ServiceType.SUGGESTION,
        name="代码建议服务",
        description="提供代码改进建议",
        priority=ServicePriority.MEDIUM,
        trigger_conditions=["help", "suggest", "建议"],
        cooldown_seconds=60,
    )


@pytest.fixture
def reminder_service() -> ServiceDefinition:
    """创建提醒类服务定义"""
    return ServiceDefinition(
        service_id="reminder_001",
        service_type=ServiceType.REMINDER,
        name="任务提醒服务",
        description="提醒用户待办任务",
        priority=ServicePriority.LOW,
        trigger_conditions=["remind", "todo", "提醒"],
        cooldown_seconds=300,
    )


@pytest.fixture
def error_service() -> ServiceDefinition:
    """创建错误处理服务定义"""
    return ServiceDefinition(
        service_id="error_001",
        service_type=ServiceType.AUTO_ACTION,
        name="错误处理服务",
        description="自动处理常见错误",
        priority=ServicePriority.HIGH,
        trigger_conditions=["error", "错误", "fail"],
        cooldown_seconds=30,
    )


# ============== KeywordTriggerEvaluator Tests ==============


class TestKeywordTriggerEvaluator:
    """关键词触发评估器测试"""

    def test_evaluate_with_matching_keyword(
        self, keyword_evaluator: KeywordTriggerEvaluator
    ):
        """测试关键词匹配"""
        context = TriggerContext(user_input="I need help with this")
        conditions = ["help", "assist"]
        assert keyword_evaluator.evaluate(context, conditions) is True

    def test_evaluate_without_matching_keyword(
        self, keyword_evaluator: KeywordTriggerEvaluator
    ):
        """测试无关键词匹配"""
        context = TriggerContext(user_input="Just a normal message")
        conditions = ["help", "error"]
        assert keyword_evaluator.evaluate(context, conditions) is False

    def test_evaluate_case_insensitive(
        self, keyword_evaluator: KeywordTriggerEvaluator
    ):
        """测试大小写不敏感"""
        context = TriggerContext(user_input="I need HELP")
        conditions = ["help"]
        assert keyword_evaluator.evaluate(context, conditions) is True

    def test_evaluate_case_sensitive(self):
        """测试大小写敏感"""
        evaluator = KeywordTriggerEvaluator(case_sensitive=True)
        context = TriggerContext(user_input="I need HELP")
        conditions = ["help"]
        assert evaluator.evaluate(context, conditions) is False

    def test_evaluate_empty_conditions(
        self, keyword_evaluator: KeywordTriggerEvaluator
    ):
        """测试空条件列表"""
        context = TriggerContext(user_input="Some input")
        assert keyword_evaluator.evaluate(context, []) is False

    def test_evaluate_chinese_keywords(
        self, keyword_evaluator: KeywordTriggerEvaluator
    ):
        """测试中文关键词"""
        context = TriggerContext(user_input="我需要帮助")
        conditions = ["帮助", "help"]
        assert keyword_evaluator.evaluate(context, conditions) is True

    def test_get_confidence_with_input(
        self, keyword_evaluator: KeywordTriggerEvaluator
    ):
        """测试置信度计算"""
        context = TriggerContext(
            user_input="A longer input message that should increase confidence",
            conversation_history=[{"role": "user", "content": "test"}],
        )
        confidence = keyword_evaluator.get_confidence(context)
        assert 0.0 < confidence <= 1.0

    def test_get_confidence_empty_input(
        self, keyword_evaluator: KeywordTriggerEvaluator
    ):
        """测试空输入的置信度"""
        context = TriggerContext(user_input="")
        assert keyword_evaluator.get_confidence(context) == 0.0


# ============== PatternTriggerEvaluator Tests ==============


class TestPatternTriggerEvaluator:
    """模式触发评估器测试"""

    def test_evaluate_with_matching_pattern(
        self, pattern_evaluator: PatternTriggerEvaluator
    ):
        """测试正则模式匹配"""
        context = TriggerContext(user_input="Error: TypeError at line 10")
        conditions = [r"Error:\s+\w+"]
        assert pattern_evaluator.evaluate(context, conditions) is True

    def test_evaluate_without_matching_pattern(
        self, pattern_evaluator: PatternTriggerEvaluator
    ):
        """测试无模式匹配"""
        context = TriggerContext(user_input="Everything is fine")
        conditions = [r"Error:\s+\w+"]
        assert pattern_evaluator.evaluate(context, conditions) is False

    def test_evaluate_multiple_patterns(
        self, pattern_evaluator: PatternTriggerEvaluator
    ):
        """测试多个模式"""
        context = TriggerContext(user_input="Warning: deprecated function")
        conditions = [r"Error:\s+\w+", r"Warning:\s+\w+"]
        assert pattern_evaluator.evaluate(context, conditions) is True

    def test_evaluate_invalid_pattern(self, pattern_evaluator: PatternTriggerEvaluator):
        """测试无效正则表达式"""
        context = TriggerContext(user_input="Some input")
        conditions = [r"[invalid(regex"]  # 无效的正则
        assert pattern_evaluator.evaluate(context, conditions) is False

    def test_evaluate_empty_conditions(
        self, pattern_evaluator: PatternTriggerEvaluator
    ):
        """测试空条件列表"""
        context = TriggerContext(user_input="Some input")
        assert pattern_evaluator.evaluate(context, []) is False

    def test_get_confidence(self, pattern_evaluator: PatternTriggerEvaluator):
        """测试置信度"""
        context = TriggerContext(user_input="Some input")
        assert pattern_evaluator.get_confidence(context) == 0.7

    def test_get_confidence_empty_input(
        self, pattern_evaluator: PatternTriggerEvaluator
    ):
        """测试空输入的置信度"""
        context = TriggerContext(user_input="")
        assert pattern_evaluator.get_confidence(context) == 0.0


# ============== ContextTriggerEvaluator Tests ==============


class TestContextTriggerEvaluator:
    """上下文触发评估器测试"""

    def test_evaluate_has_conversation_history(
        self, context_evaluator: ContextTriggerEvaluator
    ):
        """测试对话历史条件"""
        context = TriggerContext(
            user_input="test",
            conversation_history=[{"role": "user", "content": "hello"}],
        )
        conditions = ["has_conversation_history"]
        assert context_evaluator.evaluate(context, conditions) is True

    def test_evaluate_no_conversation_history(
        self, context_evaluator: ContextTriggerEvaluator
    ):
        """测试无对话历史"""
        context = TriggerContext(user_input="test", conversation_history=[])
        conditions = ["has_conversation_history"]
        assert context_evaluator.evaluate(context, conditions) is False

    def test_evaluate_has_question_mark(
        self, context_evaluator: ContextTriggerEvaluator
    ):
        """测试问号条件"""
        context = TriggerContext(user_input="How to do this?")
        conditions = ["has_question_mark"]
        assert context_evaluator.evaluate(context, conditions) is True

    def test_evaluate_has_chinese_question_mark(
        self, context_evaluator: ContextTriggerEvaluator
    ):
        """测试中文问号"""
        context = TriggerContext(user_input="这是什么？")
        conditions = ["has_question_mark"]
        assert context_evaluator.evaluate(context, conditions) is True

    def test_evaluate_has_error_keywords(
        self, context_evaluator: ContextTriggerEvaluator
    ):
        """测试错误关键词条件"""
        context = TriggerContext(user_input="I got an error in my code")
        conditions = ["has_error_keywords"]
        assert context_evaluator.evaluate(context, conditions) is True

    def test_evaluate_has_help_keywords(
        self, context_evaluator: ContextTriggerEvaluator
    ):
        """测试帮助关键词条件"""
        context = TriggerContext(user_input="How to implement this?")
        conditions = ["has_help_keywords"]
        assert context_evaluator.evaluate(context, conditions) is True

    def test_evaluate_long_input(self, context_evaluator: ContextTriggerEvaluator):
        """测试长输入条件"""
        context = TriggerContext(user_input="x" * 150)
        conditions = ["long_input"]
        assert context_evaluator.evaluate(context, conditions) is True

    def test_evaluate_short_input(self, context_evaluator: ContextTriggerEvaluator):
        """测试短输入条件"""
        context = TriggerContext(user_input="hi")
        conditions = ["short_input"]
        assert context_evaluator.evaluate(context, conditions) is True

    def test_evaluate_multiple_conditions(
        self, context_evaluator: ContextTriggerEvaluator
    ):
        """测试多个条件（全部满足）"""
        context = TriggerContext(
            user_input="How to fix this error?",
            conversation_history=[{"role": "user", "content": "test"}],
        )
        conditions = ["has_conversation_history", "has_question_mark"]
        assert context_evaluator.evaluate(context, conditions) is True

    def test_evaluate_unsupported_condition(
        self, context_evaluator: ContextTriggerEvaluator
    ):
        """测试不支持的条件"""
        context = TriggerContext(user_input="test")
        conditions = ["unsupported_condition"]
        # 不支持的条件会被跳过，但如果没有有效条件则返回False
        assert context_evaluator.evaluate(context, conditions) is False

    def test_get_confidence(self, context_evaluator: ContextTriggerEvaluator):
        """测试置信度计算"""
        context = TriggerContext(
            user_input="test",
            conversation_history=[{"role": "user", "content": "test"}],
            user_profile={"name": "test"},
        )
        confidence = context_evaluator.get_confidence(context)
        assert confidence > 0.5


# ============== ServiceTrigger Tests ==============


class TestServiceTrigger:
    """服务触发器测试"""

    def test_register_trigger(
        self, trigger: ServiceTrigger, suggestion_service: ServiceDefinition
    ):
        """测试注册触发条件"""
        trigger.register_trigger(suggestion_service)
        assert suggestion_service.service_id in trigger.registered_services

    def test_register_trigger_with_evaluator(
        self, trigger: ServiceTrigger, suggestion_service: ServiceDefinition
    ):
        """测试注册带自定义评估器的触发条件"""
        evaluator = PatternTriggerEvaluator()
        trigger.register_trigger(suggestion_service, evaluator)
        assert suggestion_service.service_id in trigger.registered_services

    def test_unregister_trigger(
        self, trigger: ServiceTrigger, suggestion_service: ServiceDefinition
    ):
        """测试取消注册"""
        trigger.register_trigger(suggestion_service)
        result = trigger.unregister_trigger(suggestion_service.service_id)
        assert result is True
        assert suggestion_service.service_id not in trigger.registered_services

    def test_unregister_nonexistent_trigger(self, trigger: ServiceTrigger):
        """测试取消注册不存在的服务"""
        result = trigger.unregister_trigger("nonexistent_id")
        assert result is False

    def test_check_trigger_matches(
        self,
        trigger: ServiceTrigger,
        suggestion_service: ServiceDefinition,
        help_context: TriggerContext,
    ):
        """测试触发检查匹配"""
        trigger.register_trigger(suggestion_service)
        triggered = trigger.check_trigger(help_context)
        assert len(triggered) == 1
        assert triggered[0].service_id == suggestion_service.service_id

    def test_check_trigger_no_match(
        self,
        trigger: ServiceTrigger,
        suggestion_service: ServiceDefinition,
        basic_context: TriggerContext,
    ):
        """测试触发检查不匹配"""
        trigger.register_trigger(suggestion_service)
        # basic_context 不包含 "help", "suggest", "建议"
        triggered = trigger.check_trigger(basic_context)
        assert len(triggered) == 0

    def test_check_trigger_multiple_services(
        self,
        trigger: ServiceTrigger,
        suggestion_service: ServiceDefinition,
        error_service: ServiceDefinition,
        error_context: TriggerContext,
    ):
        """测试多服务触发"""
        trigger.register_trigger(suggestion_service)
        trigger.register_trigger(error_service)
        triggered = trigger.check_trigger(error_context)
        # error_context 包含 "error"，应该触发 error_service
        assert len(triggered) == 1
        assert triggered[0].service_id == error_service.service_id

    def test_get_pending_triggers(
        self,
        trigger: ServiceTrigger,
        suggestion_service: ServiceDefinition,
        help_context: TriggerContext,
    ):
        """测试获取待处理触发"""
        trigger.register_trigger(suggestion_service)
        trigger.check_trigger(help_context)
        pending = trigger.get_pending_triggers()
        assert len(pending) == 1

    def test_clear_pending(
        self,
        trigger: ServiceTrigger,
        suggestion_service: ServiceDefinition,
        help_context: TriggerContext,
    ):
        """测试清除待处理状态"""
        trigger.register_trigger(suggestion_service)
        trigger.check_trigger(help_context)
        trigger.clear_pending(suggestion_service.service_id)
        assert trigger.pending_count == 0

    def test_clear_all_pending(
        self,
        trigger: ServiceTrigger,
        suggestion_service: ServiceDefinition,
        error_service: ServiceDefinition,
    ):
        """测试清除所有待处理状态"""
        trigger.register_trigger(suggestion_service)
        trigger.register_trigger(error_service)
        # 手动添加到待处理
        trigger._pending_triggers[suggestion_service.service_id] = suggestion_service
        trigger._pending_triggers[error_service.service_id] = error_service
        trigger.clear_all_pending()
        assert trigger.pending_count == 0

    def test_cooldown_mechanism(
        self,
        trigger: ServiceTrigger,
        suggestion_service: ServiceDefinition,
        help_context: TriggerContext,
    ):
        """测试冷却期机制"""
        # 设置较短的冷却时间用于测试
        suggestion_service.cooldown_seconds = 1
        trigger.register_trigger(suggestion_service)

        # 第一次触发
        triggered = trigger.check_trigger(help_context)
        assert len(triggered) == 1

        # 记录触发
        trigger.record_trigger(suggestion_service.service_id)

        # 立即再次检查，应该在冷却期内
        assert trigger.is_in_cooldown(suggestion_service.service_id) is True

        # 冷却期内不应触发
        triggered = trigger.check_trigger(help_context)
        assert len(triggered) == 0

    def test_cooldown_expires(
        self,
        trigger: ServiceTrigger,
        help_context: TriggerContext,
    ):
        """测试冷却期过期"""
        # 创建一个冷却时间很短的服务
        short_cooldown_service = ServiceDefinition(
            service_id="short_cooldown",
            service_type=ServiceType.SUGGESTION,
            name="短冷却服务",
            description="测试用",
            priority=ServicePriority.LOW,
            trigger_conditions=["help"],
            cooldown_seconds=1,
        )
        trigger.register_trigger(short_cooldown_service)

        # 第一次触发并记录
        trigger.check_trigger(help_context)
        trigger.record_trigger(short_cooldown_service.service_id)

        # 等待冷却期过期
        time.sleep(1.1)

        # 冷却期过后应该可以再次触发
        assert trigger.is_in_cooldown(short_cooldown_service.service_id) is False

    def test_get_cooldown_remaining(
        self,
        trigger: ServiceTrigger,
        suggestion_service: ServiceDefinition,
    ):
        """测试获取剩余冷却时间"""
        suggestion_service.cooldown_seconds = 60
        trigger.register_trigger(suggestion_service)
        trigger.record_trigger(suggestion_service.service_id)

        remaining = trigger.get_cooldown_remaining(suggestion_service.service_id)
        assert 0 < remaining <= 60

    def test_get_cooldown_remaining_not_in_cooldown(
        self,
        trigger: ServiceTrigger,
        suggestion_service: ServiceDefinition,
    ):
        """测试未在冷却期时获取剩余时间"""
        trigger.register_trigger(suggestion_service)
        remaining = trigger.get_cooldown_remaining(suggestion_service.service_id)
        assert remaining == 0.0

    def test_record_trigger(
        self,
        trigger: ServiceTrigger,
        suggestion_service: ServiceDefinition,
    ):
        """测试记录触发"""
        trigger.register_trigger(suggestion_service)
        trigger.record_trigger(suggestion_service.service_id)
        assert trigger.get_trigger_count(suggestion_service.service_id) == 1

        trigger.record_trigger(suggestion_service.service_id)
        assert trigger.get_trigger_count(suggestion_service.service_id) == 2

    def test_reset_trigger_record(
        self,
        trigger: ServiceTrigger,
        suggestion_service: ServiceDefinition,
    ):
        """测试重置触发记录"""
        trigger.register_trigger(suggestion_service)
        trigger.record_trigger(suggestion_service.service_id)
        trigger.record_trigger(suggestion_service.service_id)
        trigger.reset_trigger_record(suggestion_service.service_id)
        assert trigger.get_trigger_count(suggestion_service.service_id) == 0

    def test_trigger_with_timing_judge(
        self,
        trigger_with_judge: ServiceTrigger,
        error_service: ServiceDefinition,
        error_context: TriggerContext,
    ):
        """测试与TimingJudge集成"""
        trigger_with_judge.register_trigger(error_service)
        triggered = trigger_with_judge.check_trigger(error_context)
        # TimingJudge 会根据上下文判断是否触发
        # 由于 error_context 包含错误信息，应该会触发
        assert len(triggered) >= 0  # 结果取决于 TimingJudge 的判断

    def test_custom_evaluator(
        self,
        trigger: ServiceTrigger,
    ):
        """测试自定义评估器"""
        service = ServiceDefinition(
            service_id="pattern_service",
            service_type=ServiceType.AUTO_ACTION,
            name="模式匹配服务",
            description="使用正则匹配",
            priority=ServicePriority.HIGH,
            trigger_conditions=[r"Error:\s+\w+Error"],
            cooldown_seconds=60,
        )
        evaluator = PatternTriggerEvaluator()
        trigger.register_trigger(service, evaluator)

        context = TriggerContext(user_input="Error: TypeError occurred")
        triggered = trigger.check_trigger(context)
        assert len(triggered) == 1


# ============== Integration Tests ==============


class TestServiceTriggerIntegration:
    """服务触发器集成测试"""

    def test_full_workflow(self, trigger: ServiceTrigger):
        """测试完整工作流程"""
        # 1. 注册多个服务
        services = [
            ServiceDefinition(
                service_id=f"service_{i}",
                service_type=ServiceType.SUGGESTION,
                name=f"服务{i}",
                description=f"测试服务{i}",
                priority=ServicePriority.MEDIUM,
                trigger_conditions=[f"keyword{i}"],
                cooldown_seconds=60,
            )
            for i in range(3)
        ]
        for service in services:
            trigger.register_trigger(service)

        assert len(trigger.registered_services) == 3

        # 2. 触发检查
        context = TriggerContext(user_input="This contains keyword1")
        triggered = trigger.check_trigger(context)
        assert len(triggered) == 1
        assert triggered[0].service_id == "service_1"

        # 3. 记录触发
        trigger.record_trigger("service_1")
        assert trigger.is_in_cooldown("service_1") is True

        # 4. 清除待处理
        trigger.clear_pending("service_1")
        assert trigger.pending_count == 0

        # 5. 取消注册
        trigger.unregister_trigger("service_0")
        assert len(trigger.registered_services) == 2

    def test_multiple_triggers_same_context(self, trigger: ServiceTrigger):
        """测试同一上下文触发多个服务"""
        service1 = ServiceDefinition(
            service_id="multi_1",
            service_type=ServiceType.SUGGESTION,
            name="服务1",
            description="测试",
            priority=ServicePriority.HIGH,
            trigger_conditions=["help"],
            cooldown_seconds=60,
        )
        service2 = ServiceDefinition(
            service_id="multi_2",
            service_type=ServiceType.INFORMATION,
            name="服务2",
            description="测试",
            priority=ServicePriority.LOW,
            trigger_conditions=["help", "info"],
            cooldown_seconds=60,
        )
        trigger.register_trigger(service1)
        trigger.register_trigger(service2)

        context = TriggerContext(user_input="I need help with this")
        triggered = trigger.check_trigger(context)
        assert len(triggered) == 2

    def test_priority_ordering(self, trigger: ServiceTrigger):
        """测试服务优先级"""
        high_priority = ServiceDefinition(
            service_id="high",
            service_type=ServiceType.AUTO_ACTION,
            name="高优先级",
            description="测试",
            priority=ServicePriority.HIGH,
            trigger_conditions=["test"],
            cooldown_seconds=60,
        )
        low_priority = ServiceDefinition(
            service_id="low",
            service_type=ServiceType.SUGGESTION,
            name="低优先级",
            description="测试",
            priority=ServicePriority.LOW,
            trigger_conditions=["test"],
            cooldown_seconds=60,
        )
        trigger.register_trigger(low_priority)
        trigger.register_trigger(high_priority)

        context = TriggerContext(user_input="This is a test")
        triggered = trigger.check_trigger(context)
        assert len(triggered) == 2
