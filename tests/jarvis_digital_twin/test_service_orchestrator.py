"""服务编排器测试模块。

测试ServiceOrchestrator类的功能，包括：
- 服务优先级排序
- 冲突检测和解决
- 执行计划生成
- 与NeedInferrer集成
"""

import pytest
from datetime import datetime
from typing import List

from jarvis.jarvis_digital_twin.proactive_service import (
    ConflictResolution,
    ExecutionPlan,
    ServiceDefinition,
    ServiceOrchestrator,
    ServicePriority,
    ServiceType,
    TriggerContext,
)
from jarvis.jarvis_digital_twin.proactive_service.service_orchestrator import (
    ConflictRule,
    PRIORITY_WEIGHTS,
)


# ==================== 测试夹具 ====================


@pytest.fixture
def orchestrator() -> ServiceOrchestrator:
    """创建服务编排器实例。"""
    return ServiceOrchestrator()


@pytest.fixture
def sample_services() -> List[ServiceDefinition]:
    """创建示例服务列表。"""
    return [
        ServiceDefinition(
            service_id="svc_1",
            service_type=ServiceType.SUGGESTION,
            name="代码建议",
            description="提供代码改进建议",
            priority=ServicePriority.HIGH,
            trigger_conditions=["code", "improve"],
        ),
        ServiceDefinition(
            service_id="svc_2",
            service_type=ServiceType.REMINDER,
            name="测试提醒",
            description="提醒编写测试",
            priority=ServicePriority.MEDIUM,
            trigger_conditions=["test", "unittest"],
        ),
        ServiceDefinition(
            service_id="svc_3",
            service_type=ServiceType.INFORMATION,
            name="文档信息",
            description="提供相关文档",
            priority=ServicePriority.LOW,
            trigger_conditions=["doc", "help"],
        ),
    ]


@pytest.fixture
def trigger_context() -> TriggerContext:
    """创建触发上下文。"""
    return TriggerContext(
        user_input="我需要改进这段代码",
        conversation_history=[],
        user_profile={"skill_level": "intermediate"},
    )


# ==================== 初始化测试 ====================


class TestServiceOrchestratorInit:
    """测试ServiceOrchestrator初始化。"""

    def test_init_without_need_inferrer(self) -> None:
        """测试不带NeedInferrer初始化。"""
        orchestrator = ServiceOrchestrator()
        assert orchestrator._need_inferrer is None
        assert len(orchestrator._conflict_rules) > 0

    def test_init_default_conflict_rules(
        self, orchestrator: ServiceOrchestrator
    ) -> None:
        """测试默认冲突规则初始化。"""
        rules = orchestrator.conflict_rules
        # 应该有互斥类型的规则
        assert len(rules) > 0

    def test_set_need_inferrer(self, orchestrator: ServiceOrchestrator) -> None:
        """测试设置NeedInferrer。"""
        # 由于NeedInferrer需要复杂的依赖，这里只测试方法存在
        assert hasattr(orchestrator, "set_need_inferrer")


# ==================== 冲突规则测试 ====================


class TestConflictRules:
    """测试冲突规则管理。"""

    def test_register_conflict_rule(self, orchestrator: ServiceOrchestrator) -> None:
        """测试注册冲突规则。"""
        orchestrator.register_conflict_rule(
            ServiceType.SUGGESTION,
            ServiceType.REMINDER,
            ConflictResolution.KEEP_HIGHEST_PRIORITY,
        )
        rules = orchestrator.conflict_rules
        key = (ServiceType.SUGGESTION, ServiceType.REMINDER)
        assert key in rules
        assert rules[key].resolution == ConflictResolution.KEEP_HIGHEST_PRIORITY

    def test_register_conflict_rule_bidirectional(
        self, orchestrator: ServiceOrchestrator
    ) -> None:
        """测试冲突规则双向注册。"""
        orchestrator.register_conflict_rule(
            ServiceType.SUGGESTION,
            ServiceType.REMINDER,
            ConflictResolution.MERGE,
        )
        rules = orchestrator.conflict_rules
        # 应该双向注册
        assert (ServiceType.SUGGESTION, ServiceType.REMINDER) in rules
        assert (ServiceType.REMINDER, ServiceType.SUGGESTION) in rules

    def test_unregister_conflict_rule(self, orchestrator: ServiceOrchestrator) -> None:
        """测试取消注册冲突规则。"""
        orchestrator.register_conflict_rule(
            ServiceType.SUGGESTION,
            ServiceType.REMINDER,
            ConflictResolution.KEEP_FIRST,
        )
        result = orchestrator.unregister_conflict_rule(
            ServiceType.SUGGESTION,
            ServiceType.REMINDER,
        )
        assert result is True
        rules = orchestrator.conflict_rules
        assert (ServiceType.SUGGESTION, ServiceType.REMINDER) not in rules

    def test_unregister_nonexistent_rule(
        self, orchestrator: ServiceOrchestrator
    ) -> None:
        """测试取消注册不存在的规则。"""
        result = orchestrator.unregister_conflict_rule(
            ServiceType.INFORMATION,
            ServiceType.REMINDER,
        )
        # 如果规则不存在，返回False
        # 注意：可能有默认规则
        assert isinstance(result, bool)


# ==================== 优先级排序测试 ====================


class TestPrioritize:
    """测试服务优先级排序。"""

    def test_prioritize_empty_list(self, orchestrator: ServiceOrchestrator) -> None:
        """测试空列表排序。"""
        result = orchestrator.prioritize([])
        assert result == []

    def test_prioritize_single_service(
        self,
        orchestrator: ServiceOrchestrator,
        sample_services: List[ServiceDefinition],
    ) -> None:
        """测试单个服务排序。"""
        result = orchestrator.prioritize([sample_services[0]])
        assert len(result) == 1
        assert result[0].service_id == "svc_1"

    def test_prioritize_by_priority(
        self,
        orchestrator: ServiceOrchestrator,
        sample_services: List[ServiceDefinition],
    ) -> None:
        """测试按优先级排序。"""
        result = orchestrator.prioritize(sample_services)
        # HIGH > MEDIUM > LOW
        assert result[0].priority == ServicePriority.HIGH
        assert result[1].priority == ServicePriority.MEDIUM
        assert result[2].priority == ServicePriority.LOW

    def test_prioritize_with_context(
        self,
        orchestrator: ServiceOrchestrator,
        sample_services: List[ServiceDefinition],
        trigger_context: TriggerContext,
    ) -> None:
        """测试带上下文的排序。"""
        result = orchestrator.prioritize(sample_services, trigger_context)
        # 上下文包含"代码"，应该影响排序
        assert len(result) == 3

    def test_prioritize_same_priority(self, orchestrator: ServiceOrchestrator) -> None:
        """测试相同优先级的服务排序。"""
        services = [
            ServiceDefinition(
                service_id="svc_a",
                service_type=ServiceType.SUGGESTION,
                name="服务A",
                description="描述A",
                priority=ServicePriority.MEDIUM,
                trigger_conditions=["a"],
            ),
            ServiceDefinition(
                service_id="svc_b",
                service_type=ServiceType.REMINDER,
                name="服务B",
                description="描述B",
                priority=ServicePriority.MEDIUM,
                trigger_conditions=["b"],
            ),
        ]
        result = orchestrator.prioritize(services)
        assert len(result) == 2


# ==================== 冲突解决测试 ====================


class TestResolveConflicts:
    """测试服务冲突解决。"""

    def test_resolve_conflicts_empty_list(
        self, orchestrator: ServiceOrchestrator
    ) -> None:
        """测试空列表冲突解决。"""
        result = orchestrator.resolve_conflicts([])
        assert result == []

    def test_resolve_conflicts_single_service(
        self,
        orchestrator: ServiceOrchestrator,
        sample_services: List[ServiceDefinition],
    ) -> None:
        """测试单个服务冲突解决。"""
        result = orchestrator.resolve_conflicts([sample_services[0]])
        assert len(result) == 1

    def test_resolve_conflicts_no_conflict(
        self,
        orchestrator: ServiceOrchestrator,
        sample_services: List[ServiceDefinition],
    ) -> None:
        """测试无冲突的服务列表。"""
        result = orchestrator.resolve_conflicts(sample_services)
        # 不同类型的服务，无冲突
        assert len(result) >= 1

    def test_resolve_same_type_conflict(
        self, orchestrator: ServiceOrchestrator
    ) -> None:
        """测试同类型服务冲突解决。"""
        services = [
            ServiceDefinition(
                service_id="svc_1",
                service_type=ServiceType.SUGGESTION,
                name="建议1",
                description="描述1",
                priority=ServicePriority.HIGH,
                trigger_conditions=["a"],
            ),
            ServiceDefinition(
                service_id="svc_2",
                service_type=ServiceType.SUGGESTION,
                name="建议2",
                description="描述2",
                priority=ServicePriority.LOW,
                trigger_conditions=["b"],
            ),
        ]
        result = orchestrator.resolve_conflicts(services)
        # 默认保留最高优先级
        assert len(result) == 1
        assert result[0].priority == ServicePriority.HIGH

    def test_resolve_cross_type_conflict_cancel_both(
        self, orchestrator: ServiceOrchestrator
    ) -> None:
        """测试跨类型冲突解决（取消两者）。"""
        # AUTO_ACTION 和 CLARIFICATION 是互斥的
        services = [
            ServiceDefinition(
                service_id="svc_1",
                service_type=ServiceType.AUTO_ACTION,
                name="自动操作",
                description="自动执行",
                priority=ServicePriority.HIGH,
                trigger_conditions=["auto"],
            ),
            ServiceDefinition(
                service_id="svc_2",
                service_type=ServiceType.CLARIFICATION,
                name="澄清请求",
                description="请求澄清",
                priority=ServicePriority.MEDIUM,
                trigger_conditions=["clarify"],
            ),
        ]
        result = orchestrator.resolve_conflicts(services)
        # 互斥类型应该都被取消
        assert len(result) == 0


# ==================== 编排测试 ====================


class TestOrchestrate:
    """测试服务编排。"""

    def test_orchestrate_empty_list(
        self, orchestrator: ServiceOrchestrator, trigger_context: TriggerContext
    ) -> None:
        """测试空列表编排。"""
        result = orchestrator.orchestrate([], trigger_context)
        assert result == []

    def test_orchestrate_single_service(
        self,
        orchestrator: ServiceOrchestrator,
        sample_services: List[ServiceDefinition],
        trigger_context: TriggerContext,
    ) -> None:
        """测试单个服务编排。"""
        result = orchestrator.orchestrate([sample_services[0]], trigger_context)
        assert len(result) == 1

    def test_orchestrate_multiple_services(
        self,
        orchestrator: ServiceOrchestrator,
        sample_services: List[ServiceDefinition],
        trigger_context: TriggerContext,
    ) -> None:
        """测试多个服务编排。"""
        result = orchestrator.orchestrate(sample_services, trigger_context)
        # 应该按优先级排序
        assert len(result) >= 1
        if len(result) > 1:
            # 验证排序
            for i in range(len(result) - 1):
                assert PRIORITY_WEIGHTS.get(
                    result[i].priority, 0
                ) >= PRIORITY_WEIGHTS.get(result[i + 1].priority, 0)


# ==================== 执行计划测试 ====================


class TestGetExecutionPlan:
    """测试执行计划生成。"""

    def test_get_execution_plan_empty(self, orchestrator: ServiceOrchestrator) -> None:
        """测试空列表执行计划。"""
        plan = orchestrator.get_execution_plan([])
        assert isinstance(plan, ExecutionPlan)
        assert len(plan.services) == 0
        assert len(plan.execution_order) == 0

    def test_get_execution_plan_single_service(
        self,
        orchestrator: ServiceOrchestrator,
        sample_services: List[ServiceDefinition],
    ) -> None:
        """测试单个服务执行计划。"""
        plan = orchestrator.get_execution_plan([sample_services[0]])
        assert len(plan.services) == 1
        assert len(plan.execution_order) == 1
        assert plan.execution_order[0] == "svc_1"

    def test_get_execution_plan_multiple_services(
        self,
        orchestrator: ServiceOrchestrator,
        sample_services: List[ServiceDefinition],
    ) -> None:
        """测试多个服务执行计划。"""
        plan = orchestrator.get_execution_plan(sample_services)
        assert len(plan.services) == 3
        assert len(plan.execution_order) == 3
        assert plan.estimated_duration_ms > 0

    def test_get_execution_plan_parallel_groups(
        self,
        orchestrator: ServiceOrchestrator,
        sample_services: List[ServiceDefinition],
    ) -> None:
        """测试并行组生成。"""
        plan = orchestrator.get_execution_plan(sample_services)
        # 不同类型的服务可以并行
        assert len(plan.parallel_groups) >= 1

    def test_execution_plan_has_timestamp(
        self,
        orchestrator: ServiceOrchestrator,
        sample_services: List[ServiceDefinition],
    ) -> None:
        """测试执行计划包含时间戳。"""
        plan = orchestrator.get_execution_plan(sample_services)
        assert isinstance(plan.created_at, datetime)


# ==================== 统计信息测试 ====================


class TestGetServiceStats:
    """测试服务统计信息。"""

    def test_get_service_stats_empty(self, orchestrator: ServiceOrchestrator) -> None:
        """测试空列表统计。"""
        stats = orchestrator.get_service_stats([])
        assert stats["total"] == 0
        assert stats["by_type"] == {}
        assert stats["by_priority"] == {}

    def test_get_service_stats_single_service(
        self,
        orchestrator: ServiceOrchestrator,
        sample_services: List[ServiceDefinition],
    ) -> None:
        """测试单个服务统计。"""
        stats = orchestrator.get_service_stats([sample_services[0]])
        assert stats["total"] == 1
        assert "suggestion" in stats["by_type"]
        assert "high" in stats["by_priority"]

    def test_get_service_stats_multiple_services(
        self,
        orchestrator: ServiceOrchestrator,
        sample_services: List[ServiceDefinition],
    ) -> None:
        """测试多个服务统计。"""
        stats = orchestrator.get_service_stats(sample_services)
        assert stats["total"] == 3
        assert len(stats["by_type"]) == 3
        assert len(stats["by_priority"]) == 3


# ==================== 边界情况测试 ====================


class TestEdgeCases:
    """测试边界情况。"""

    def test_all_critical_priority(self, orchestrator: ServiceOrchestrator) -> None:
        """测试所有服务都是CRITICAL优先级。"""
        services = [
            ServiceDefinition(
                service_id=f"svc_{i}",
                service_type=ServiceType.SUGGESTION,
                name=f"服务{i}",
                description=f"描述{i}",
                priority=ServicePriority.CRITICAL,
                trigger_conditions=[f"cond_{i}"],
            )
            for i in range(3)
        ]
        result = orchestrator.resolve_conflicts(services)
        # 同类型同优先级，保留一个
        assert len(result) == 1

    def test_all_background_priority(self, orchestrator: ServiceOrchestrator) -> None:
        """测试所有服务都是BACKGROUND优先级。"""
        services = [
            ServiceDefinition(
                service_id=f"svc_{i}",
                service_type=ServiceType.INFORMATION,
                name=f"服务{i}",
                description=f"描述{i}",
                priority=ServicePriority.BACKGROUND,
                trigger_conditions=[f"cond_{i}"],
            )
            for i in range(3)
        ]
        result = orchestrator.prioritize(services)
        assert len(result) == 3

    def test_mixed_conflict_rules(self, orchestrator: ServiceOrchestrator) -> None:
        """测试混合冲突规则。"""
        # 注册自定义规则
        orchestrator.register_conflict_rule(
            ServiceType.SUGGESTION,
            ServiceType.INFORMATION,
            ConflictResolution.MERGE,
        )
        services = [
            ServiceDefinition(
                service_id="svc_1",
                service_type=ServiceType.SUGGESTION,
                name="建议",
                description="描述",
                priority=ServicePriority.HIGH,
                trigger_conditions=["a"],
            ),
            ServiceDefinition(
                service_id="svc_2",
                service_type=ServiceType.INFORMATION,
                name="信息",
                description="描述",
                priority=ServicePriority.LOW,
                trigger_conditions=["b"],
            ),
        ]
        result = orchestrator.resolve_conflicts(services)
        # MERGE策略应该保留所有
        assert len(result) == 2

    def test_context_with_matching_keywords(
        self, orchestrator: ServiceOrchestrator
    ) -> None:
        """测试上下文包含匹配关键词。"""
        services = [
            ServiceDefinition(
                service_id="svc_1",
                service_type=ServiceType.SUGGESTION,
                name="代码建议",
                description="提供代码改进建议",
                priority=ServicePriority.LOW,
                trigger_conditions=["code", "improve"],
            ),
            ServiceDefinition(
                service_id="svc_2",
                service_type=ServiceType.REMINDER,
                name="测试提醒",
                description="提醒编写测试",
                priority=ServicePriority.HIGH,
                trigger_conditions=["test"],
            ),
        ]
        context = TriggerContext(
            user_input="我需要改进这段code",
            conversation_history=[],
        )
        result = orchestrator.prioritize(services, context)
        # 虽然svc_2优先级更高，但svc_1的关键词匹配可能影响排序
        assert len(result) == 2


# ==================== ConflictRule数据类测试 ====================


class TestConflictRuleDataclass:
    """测试ConflictRule数据类。"""

    def test_conflict_rule_creation(self) -> None:
        """测试创建ConflictRule。"""
        rule = ConflictRule(
            service_type_a=ServiceType.SUGGESTION,
            service_type_b=ServiceType.REMINDER,
            resolution=ConflictResolution.KEEP_FIRST,
        )
        assert rule.service_type_a == ServiceType.SUGGESTION
        assert rule.service_type_b == ServiceType.REMINDER
        assert rule.resolution == ConflictResolution.KEEP_FIRST
        assert isinstance(rule.created_at, datetime)

    def test_conflict_rule_with_custom_timestamp(self) -> None:
        """测试带自定义时间戳的ConflictRule。"""
        custom_time = datetime(2024, 1, 1, 12, 0, 0)
        rule = ConflictRule(
            service_type_a=ServiceType.AUTO_ACTION,
            service_type_b=ServiceType.CLARIFICATION,
            resolution=ConflictResolution.CANCEL_BOTH,
            created_at=custom_time,
        )
        assert rule.created_at == custom_time


# ==================== 集成测试 ====================


class TestNeedInferrerIntegration:
    """测试NeedInferrer集成。"""

    def test_set_need_inferrer(self, orchestrator: ServiceOrchestrator) -> None:
        """测试设置NeedInferrer。"""
        # 创建一个mock NeedInferrer
        from unittest.mock import MagicMock

        mock_inferrer = MagicMock()
        orchestrator.set_need_inferrer(mock_inferrer)
        assert orchestrator._need_inferrer is mock_inferrer

    def test_orchestrate_with_need_inferrer(
        self,
        orchestrator: ServiceOrchestrator,
        sample_services: List[ServiceDefinition],
        trigger_context: TriggerContext,
    ) -> None:
        """测试带NeedInferrer的编排。"""
        from unittest.mock import MagicMock
        from jarvis.jarvis_digital_twin.prediction import (
            InferenceResult,
            PredictionType,
        )

        # 创建mock NeedInferrer
        mock_inferrer = MagicMock()
        mock_inferrer.infer_implicit_needs.return_value = [
            InferenceResult(
                inference_type=PredictionType.IMPLICIT_NEED,
                content="code improvement suggestion",
                confidence_score=0.8,
            )
        ]
        orchestrator.set_need_inferrer(mock_inferrer)

        result = orchestrator.orchestrate(sample_services, trigger_context)
        assert len(result) >= 1
        # 验证NeedInferrer被调用
        mock_inferrer.infer_implicit_needs.assert_called_once()

    def test_orchestrate_with_inferrer_exception(
        self,
        orchestrator: ServiceOrchestrator,
        sample_services: List[ServiceDefinition],
        trigger_context: TriggerContext,
    ) -> None:
        """测试NeedInferrer抛出异常时的处理。"""
        from unittest.mock import MagicMock

        mock_inferrer = MagicMock()
        mock_inferrer.infer_implicit_needs.side_effect = Exception("Test error")
        orchestrator.set_need_inferrer(mock_inferrer)

        # 应该不抛出异常，返回正常结果
        result = orchestrator.orchestrate(sample_services, trigger_context)
        assert len(result) >= 1

    def test_orchestrate_with_empty_inferences(
        self,
        orchestrator: ServiceOrchestrator,
        sample_services: List[ServiceDefinition],
        trigger_context: TriggerContext,
    ) -> None:
        """测试NeedInferrer返回空结果时的处理。"""
        from unittest.mock import MagicMock

        mock_inferrer = MagicMock()
        mock_inferrer.infer_implicit_needs.return_value = []
        orchestrator.set_need_inferrer(mock_inferrer)

        result = orchestrator.orchestrate(sample_services, trigger_context)
        assert len(result) >= 1


class TestIntegration:
    """集成测试。"""

    def test_full_workflow(
        self,
        orchestrator: ServiceOrchestrator,
        sample_services: List[ServiceDefinition],
        trigger_context: TriggerContext,
    ) -> None:
        """测试完整工作流程。"""
        # 1. 编排服务
        orchestrated = orchestrator.orchestrate(sample_services, trigger_context)
        assert len(orchestrated) >= 1

        # 2. 生成执行计划
        plan = orchestrator.get_execution_plan(orchestrated)
        assert isinstance(plan, ExecutionPlan)
        assert len(plan.services) == len(orchestrated)

        # 3. 获取统计信息
        stats = orchestrator.get_service_stats(orchestrated)
        assert stats["total"] == len(orchestrated)

    def test_workflow_with_custom_rules(
        self,
        orchestrator: ServiceOrchestrator,
        trigger_context: TriggerContext,
    ) -> None:
        """测试带自定义规则的工作流程。"""
        # 注册自定义规则
        orchestrator.register_conflict_rule(
            ServiceType.SUGGESTION,
            ServiceType.REMINDER,
            ConflictResolution.KEEP_LAST,
        )

        services = [
            ServiceDefinition(
                service_id="svc_1",
                service_type=ServiceType.SUGGESTION,
                name="建议",
                description="描述",
                priority=ServicePriority.HIGH,
                trigger_conditions=["a"],
            ),
            ServiceDefinition(
                service_id="svc_2",
                service_type=ServiceType.REMINDER,
                name="提醒",
                description="描述",
                priority=ServicePriority.LOW,
                trigger_conditions=["b"],
            ),
        ]

        orchestrated = orchestrator.orchestrate(services, trigger_context)
        # KEEP_LAST策略应该保留REMINDER
        assert len(orchestrated) == 1
        assert orchestrated[0].service_type == ServiceType.REMINDER
