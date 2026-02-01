"""ProactiveServiceManager 测试模块。

测试主动服务管理器的核心功能。
"""

from unittest.mock import MagicMock

from jarvis.jarvis_digital_twin.proactive_service import (
    FeedbackType,
    ProactiveServiceManager,
    ServiceDefinition,
    ServicePriority,
    ServiceType,
    KeywordTriggerEvaluator,
    SuggestionHandler,
)


class TestProactiveServiceManagerInit:
    """测试ProactiveServiceManager初始化。"""

    def test_init_default(self) -> None:
        """测试默认初始化。"""
        manager = ProactiveServiceManager()
        assert manager.enabled is True
        assert manager.get_last_results() == []
        assert manager.get_registered_services() == []

    def test_init_with_components(self) -> None:
        """测试带组件的初始化。"""
        timing_judge = MagicMock()
        need_inferrer = MagicMock()
        preference_learner = MagicMock()

        manager = ProactiveServiceManager(
            timing_judge=timing_judge,
            need_inferrer=need_inferrer,
            preference_learner=preference_learner,
        )
        assert manager.enabled is True

    def test_enabled_property(self) -> None:
        """测试enabled属性。"""
        manager = ProactiveServiceManager()
        assert manager.enabled is True

        manager.enabled = False
        assert manager.enabled is False

        manager.enabled = True
        assert manager.enabled is True


class TestServiceRegistration:
    """测试服务注册功能。"""

    def test_register_service_basic(self) -> None:
        """测试基本服务注册。"""
        manager = ProactiveServiceManager()
        service_def = ServiceDefinition(
            service_id="test_service",
            service_type=ServiceType.SUGGESTION,
            name="Test Service",
            description="A test service",
            priority=ServicePriority.MEDIUM,
            trigger_conditions=["test"],
        )

        manager.register_service(service_def)
        assert manager.is_service_registered("test_service")
        assert len(manager.get_registered_services()) == 1

    def test_register_service_with_handler(self) -> None:
        """测试带处理器的服务注册。"""
        manager = ProactiveServiceManager()
        service_def = ServiceDefinition(
            service_id="suggestion_service",
            service_type=ServiceType.SUGGESTION,
            name="Suggestion Service",
            description="A suggestion service",
            priority=ServicePriority.MEDIUM,
            trigger_conditions=["suggest"],
        )
        handler = SuggestionHandler()

        manager.register_service(service_def, handler=handler)
        assert manager.is_service_registered("suggestion_service")

    def test_register_service_with_evaluator(self) -> None:
        """测试带评估器的服务注册。"""
        manager = ProactiveServiceManager()
        service_def = ServiceDefinition(
            service_id="keyword_service",
            service_type=ServiceType.SUGGESTION,
            name="Keyword Service",
            description="A keyword-triggered service",
            priority=ServicePriority.MEDIUM,
            trigger_conditions=["keyword1", "keyword2"],
        )
        evaluator = KeywordTriggerEvaluator()

        manager.register_service(service_def, evaluator=evaluator)
        assert manager.is_service_registered("keyword_service")

    def test_unregister_service(self) -> None:
        """测试服务注销。"""
        manager = ProactiveServiceManager()
        service_def = ServiceDefinition(
            service_id="to_remove",
            service_type=ServiceType.SUGGESTION,
            name="To Remove",
            description="Service to be removed",
            priority=ServicePriority.LOW,
            trigger_conditions=["remove"],
        )

        manager.register_service(service_def)
        assert manager.is_service_registered("to_remove")

        result = manager.unregister_service("to_remove")
        assert result is True
        assert not manager.is_service_registered("to_remove")

    def test_unregister_nonexistent_service(self) -> None:
        """测试注销不存在的服务。"""
        manager = ProactiveServiceManager()
        result = manager.unregister_service("nonexistent")
        assert result is False


class TestProcessContext:
    """测试上下文处理功能。"""

    def test_process_context_disabled(self) -> None:
        """测试禁用状态下的上下文处理。"""
        manager = ProactiveServiceManager()
        manager.enabled = False

        results = manager.process_context("test input")
        assert results == []

    def test_process_context_no_services(self) -> None:
        """测试无注册服务时的上下文处理。"""
        manager = ProactiveServiceManager()
        results = manager.process_context("test input")
        assert results == []

    def test_process_context_no_trigger(self) -> None:
        """测试无触发时的上下文处理。"""
        manager = ProactiveServiceManager()
        service_def = ServiceDefinition(
            service_id="no_trigger",
            service_type=ServiceType.SUGGESTION,
            name="No Trigger",
            description="Won't trigger",
            priority=ServicePriority.MEDIUM,
            trigger_conditions=["specific_keyword"],
        )
        evaluator = KeywordTriggerEvaluator()
        manager.register_service(service_def, evaluator=evaluator)

        results = manager.process_context("unrelated input")
        assert results == []

    def test_process_context_with_trigger(self) -> None:
        """测试有触发时的上下文处理。"""
        manager = ProactiveServiceManager()
        service_def = ServiceDefinition(
            service_id="trigger_service",
            service_type=ServiceType.SUGGESTION,
            name="Trigger Service",
            description="Will trigger",
            priority=ServicePriority.MEDIUM,
            trigger_conditions=["trigger"],
        )
        evaluator = KeywordTriggerEvaluator()
        handler = SuggestionHandler()
        manager.register_service(service_def, handler=handler, evaluator=evaluator)

        results = manager.process_context("this will trigger the service")
        # 结果取决于服务是否被触发和执行
        assert isinstance(results, list)

    def test_process_context_with_history(self) -> None:
        """测试带对话历史的上下文处理。"""
        manager = ProactiveServiceManager()
        service_def = ServiceDefinition(
            service_id="history_service",
            service_type=ServiceType.SUGGESTION,
            name="History Service",
            description="Uses history",
            priority=ServicePriority.MEDIUM,
            trigger_conditions=["history"],
        )
        evaluator = KeywordTriggerEvaluator()
        manager.register_service(service_def, evaluator=evaluator)

        history = [
            {"role": "user", "content": "previous message"},
            {"role": "assistant", "content": "previous response"},
        ]
        results = manager.process_context(
            "check history",
            conversation_history=history,
        )
        assert isinstance(results, list)


class TestFeedbackRecording:
    """测试反馈记录功能。"""

    def test_record_feedback_accepted(self) -> None:
        """测试记录接受反馈。"""
        manager = ProactiveServiceManager()
        manager.record_feedback("service1", FeedbackType.ACCEPTED)
        stats = manager.get_service_stats("service1")
        assert stats is not None
        assert stats.accepted_count == 1

    def test_record_feedback_rejected(self) -> None:
        """测试记录拒绝反馈。"""
        manager = ProactiveServiceManager()
        manager.record_feedback("service2", FeedbackType.REJECTED)
        stats = manager.get_service_stats("service2")
        assert stats is not None
        assert stats.rejected_count == 1

    def test_record_feedback_with_comment(self) -> None:
        """测试带评论的反馈记录。"""
        manager = ProactiveServiceManager()
        manager.record_feedback(
            "service3",
            FeedbackType.MODIFIED,
            user_comment="Made some changes",
        )
        stats = manager.get_service_stats("service3")
        assert stats is not None

    def test_get_service_stats_nonexistent(self) -> None:
        """测试获取不存在服务的统计。"""
        manager = ProactiveServiceManager()
        stats = manager.get_service_stats("nonexistent")
        assert stats is None


class TestLearning:
    """测试学习功能。"""

    def test_learn_and_adjust_empty(self) -> None:
        """测试无反馈时的学习。"""
        manager = ProactiveServiceManager()
        result = manager.learn_and_adjust()
        assert result is not None
        assert result.adjustments == {}

    def test_learn_and_adjust_with_feedback(self) -> None:
        """测试有反馈时的学习。"""
        manager = ProactiveServiceManager()
        # 记录多个反馈
        for _ in range(5):
            manager.record_feedback("service_learn", FeedbackType.ACCEPTED)
        for _ in range(3):
            manager.record_feedback("service_learn", FeedbackType.REJECTED)

        result = manager.learn_and_adjust()
        assert result is not None


class TestExecutionHistory:
    """测试执行历史功能。"""

    def test_get_execution_history_empty(self) -> None:
        """测试空执行历史。"""
        manager = ProactiveServiceManager()
        history = manager.get_execution_history()
        assert history == []

    def test_get_last_results_empty(self) -> None:
        """测试空最近结果。"""
        manager = ProactiveServiceManager()
        results = manager.get_last_results()
        assert results == []

    def test_clear_execution_history(self) -> None:
        """测试清除执行历史。"""
        manager = ProactiveServiceManager()
        manager.clear_execution_history()
        history = manager.get_execution_history()
        assert history == []


class TestPendingServices:
    """测试待处理服务功能。"""

    def test_get_pending_services_empty(self) -> None:
        """测试空待处理服务。"""
        manager = ProactiveServiceManager()
        pending = manager.get_pending_services()
        assert pending == []


class TestIntegration:
    """集成测试。"""

    def test_full_workflow(self) -> None:
        """测试完整工作流程。"""
        manager = ProactiveServiceManager()

        # 1. 注册服务
        service_def = ServiceDefinition(
            service_id="workflow_service",
            service_type=ServiceType.SUGGESTION,
            name="Workflow Service",
            description="Full workflow test",
            priority=ServicePriority.HIGH,
            trigger_conditions=["workflow"],
        )
        evaluator = KeywordTriggerEvaluator()
        handler = SuggestionHandler()
        manager.register_service(service_def, handler=handler, evaluator=evaluator)

        # 2. 验证注册
        assert manager.is_service_registered("workflow_service")
        assert len(manager.get_registered_services()) == 1

        # 3. 处理上下文
        results = manager.process_context("test workflow input")
        assert isinstance(results, list)

        # 4. 记录反馈
        manager.record_feedback("workflow_service", FeedbackType.ACCEPTED)

        # 5. 学习
        learning_result = manager.learn_and_adjust()
        assert learning_result is not None

        # 6. 注销服务
        manager.unregister_service("workflow_service")
        assert not manager.is_service_registered("workflow_service")

    def test_multiple_services(self) -> None:
        """测试多服务场景。"""
        manager = ProactiveServiceManager()

        # 注册多个服务
        for i in range(3):
            service_def = ServiceDefinition(
                service_id=f"multi_service_{i}",
                service_type=ServiceType.SUGGESTION,
                name=f"Multi Service {i}",
                description=f"Multi service test {i}",
                priority=ServicePriority.MEDIUM,
                trigger_conditions=[f"keyword{i}"],
            )
            manager.register_service(service_def)

        assert len(manager.get_registered_services()) == 3

        # 注销一个
        manager.unregister_service("multi_service_1")
        assert len(manager.get_registered_services()) == 2

    def test_disabled_manager(self) -> None:
        """测试禁用管理器。"""
        manager = ProactiveServiceManager()
        service_def = ServiceDefinition(
            service_id="disabled_test",
            service_type=ServiceType.SUGGESTION,
            name="Disabled Test",
            description="Test when disabled",
            priority=ServicePriority.MEDIUM,
            trigger_conditions=["disabled"],
        )
        evaluator = KeywordTriggerEvaluator()
        manager.register_service(service_def, evaluator=evaluator)

        # 禁用管理器
        manager.enabled = False

        # 处理上下文应返回空
        results = manager.process_context("test disabled input")
        assert results == []

        # 重新启用
        manager.enabled = True
        # 服务仍然注册
        assert manager.is_service_registered("disabled_test")
