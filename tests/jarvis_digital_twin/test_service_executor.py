"""ServiceExecutor测试模块

测试服务执行器的各项功能。
"""

import time
from datetime import datetime

import pytest

from jarvis.jarvis_digital_twin.proactive_service import (
    ExecutionPlan,
    ServiceDefinition,
    ServicePriority,
    ServiceStatus,
    ServiceType,
    TriggerContext,
)
from jarvis.jarvis_digital_twin.proactive_service.service_executor import (
    ClarificationHandler,
    InformationHandler,
    ReminderHandler,
    ServiceExecutor,
    SuggestionHandler,
)


# ============== Fixtures ==============


@pytest.fixture
def executor() -> ServiceExecutor:
    """创建默认服务执行器"""
    return ServiceExecutor()


@pytest.fixture
def executor_with_handlers() -> ServiceExecutor:
    """创建带内置处理器的服务执行器"""
    executor = ServiceExecutor()
    executor.register_handler(ServiceType.SUGGESTION, SuggestionHandler())
    executor.register_handler(ServiceType.REMINDER, ReminderHandler())
    executor.register_handler(ServiceType.INFORMATION, InformationHandler())
    executor.register_handler(ServiceType.CLARIFICATION, ClarificationHandler())
    return executor


@pytest.fixture
def suggestion_handler() -> SuggestionHandler:
    """创建建议处理器"""
    return SuggestionHandler()


@pytest.fixture
def reminder_handler() -> ReminderHandler:
    """创建提醒处理器"""
    return ReminderHandler()


@pytest.fixture
def information_handler() -> InformationHandler:
    """创建信息处理器"""
    return InformationHandler()


@pytest.fixture
def clarification_handler() -> ClarificationHandler:
    """创建澄清处理器"""
    return ClarificationHandler()


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
def suggestion_service() -> ServiceDefinition:
    """创建建议类服务定义"""
    return ServiceDefinition(
        service_id="suggestion_001",
        service_type=ServiceType.SUGGESTION,
        name="代码建议服务",
        description="提供代码改进建议",
        priority=ServicePriority.MEDIUM,
        trigger_conditions=["help", "suggest"],
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
        trigger_conditions=["remind", "todo"],
        cooldown_seconds=300,
    )


@pytest.fixture
def information_service() -> ServiceDefinition:
    """创建信息类服务定义"""
    return ServiceDefinition(
        service_id="info_001",
        service_type=ServiceType.INFORMATION,
        name="信息提供服务",
        description="提供相关信息",
        priority=ServicePriority.MEDIUM,
        trigger_conditions=["info", "what"],
        cooldown_seconds=120,
    )


@pytest.fixture
def clarification_service() -> ServiceDefinition:
    """创建澄清类服务定义"""
    return ServiceDefinition(
        service_id="clarify_001",
        service_type=ServiceType.CLARIFICATION,
        name="澄清请求服务",
        description="请求用户澄清",
        priority=ServicePriority.HIGH,
        trigger_conditions=["unclear", "ambiguous"],
        cooldown_seconds=30,
    )


@pytest.fixture
def auto_action_service() -> ServiceDefinition:
    """创建自动操作类服务定义"""
    return ServiceDefinition(
        service_id="auto_001",
        service_type=ServiceType.AUTO_ACTION,
        name="自动操作服务",
        description="自动执行操作",
        priority=ServicePriority.HIGH,
        trigger_conditions=["auto", "execute"],
        cooldown_seconds=60,
    )


# ============== SuggestionHandler Tests ==============


class TestSuggestionHandler:
    """建议处理器测试"""

    def test_can_handle_suggestion_type(self, suggestion_handler: SuggestionHandler):
        """测试能处理建议类型"""
        assert suggestion_handler.can_handle(ServiceType.SUGGESTION) is True

    def test_cannot_handle_other_types(self, suggestion_handler: SuggestionHandler):
        """测试不能处理其他类型"""
        assert suggestion_handler.can_handle(ServiceType.REMINDER) is False
        assert suggestion_handler.can_handle(ServiceType.AUTO_ACTION) is False

    def test_handle_returns_completed_result(
        self, suggestion_handler: SuggestionHandler, basic_context: TriggerContext
    ):
        """测试处理返回完成结果"""
        result = suggestion_handler.handle(basic_context)
        assert result.status == ServiceStatus.COMPLETED
        assert result.message != ""

    def test_handle_includes_suggestion_in_data(
        self, suggestion_handler: SuggestionHandler, basic_context: TriggerContext
    ):
        """测试处理结果包含建议数据"""
        result = suggestion_handler.handle(basic_context)
        assert result.data is not None
        assert "suggestion" in result.data


# ============== ReminderHandler Tests ==============


class TestReminderHandler:
    """提醒处理器测试"""

    def test_can_handle_reminder_type(self, reminder_handler: ReminderHandler):
        """测试能处理提醒类型"""
        assert reminder_handler.can_handle(ServiceType.REMINDER) is True

    def test_cannot_handle_other_types(self, reminder_handler: ReminderHandler):
        """测试不能处理其他类型"""
        assert reminder_handler.can_handle(ServiceType.SUGGESTION) is False

    def test_handle_returns_completed_result(
        self, reminder_handler: ReminderHandler, basic_context: TriggerContext
    ):
        """测试处理返回完成结果"""
        result = reminder_handler.handle(basic_context)
        assert result.status == ServiceStatus.COMPLETED

    def test_handle_includes_reminder_in_data(
        self, reminder_handler: ReminderHandler, basic_context: TriggerContext
    ):
        """测试处理结果包含提醒数据"""
        result = reminder_handler.handle(basic_context)
        assert result.data is not None
        assert "reminder" in result.data


# ============== InformationHandler Tests ==============


class TestInformationHandler:
    """信息处理器测试"""

    def test_can_handle_information_type(self, information_handler: InformationHandler):
        """测试能处理信息类型"""
        assert information_handler.can_handle(ServiceType.INFORMATION) is True

    def test_cannot_handle_other_types(self, information_handler: InformationHandler):
        """测试不能处理其他类型"""
        assert information_handler.can_handle(ServiceType.REMINDER) is False

    def test_handle_returns_completed_result(
        self, information_handler: InformationHandler, basic_context: TriggerContext
    ):
        """测试处理返回完成结果"""
        result = information_handler.handle(basic_context)
        assert result.status == ServiceStatus.COMPLETED

    def test_handle_includes_information_in_data(
        self, information_handler: InformationHandler, basic_context: TriggerContext
    ):
        """测试处理结果包含信息数据"""
        result = information_handler.handle(basic_context)
        assert result.data is not None
        assert "information" in result.data


# ============== ClarificationHandler Tests ==============


class TestClarificationHandler:
    """澄清处理器测试"""

    def test_can_handle_clarification_type(
        self, clarification_handler: ClarificationHandler
    ):
        """测试能处理澄清类型"""
        assert clarification_handler.can_handle(ServiceType.CLARIFICATION) is True

    def test_cannot_handle_other_types(
        self, clarification_handler: ClarificationHandler
    ):
        """测试不能处理其他类型"""
        assert clarification_handler.can_handle(ServiceType.SUGGESTION) is False

    def test_handle_returns_completed_result(
        self, clarification_handler: ClarificationHandler, basic_context: TriggerContext
    ):
        """测试处理返回完成结果"""
        result = clarification_handler.handle(basic_context)
        assert result.status == ServiceStatus.COMPLETED

    def test_handle_includes_question_in_data(
        self, clarification_handler: ClarificationHandler, basic_context: TriggerContext
    ):
        """测试处理结果包含问题数据"""
        result = clarification_handler.handle(basic_context)
        assert result.data is not None
        assert "question" in result.data


# ============== ServiceExecutor Handler Registration Tests ==============


class TestServiceExecutorRegistration:
    """服务执行器处理器注册测试"""

    def test_register_handler(self, executor: ServiceExecutor):
        """测试注册处理器"""
        handler = SuggestionHandler()
        executor.register_handler(ServiceType.SUGGESTION, handler)
        assert executor.get_handler(ServiceType.SUGGESTION) is handler

    def test_register_multiple_handlers(self, executor: ServiceExecutor):
        """测试注册多个处理器"""
        suggestion_handler = SuggestionHandler()
        reminder_handler = ReminderHandler()
        executor.register_handler(ServiceType.SUGGESTION, suggestion_handler)
        executor.register_handler(ServiceType.REMINDER, reminder_handler)
        assert executor.get_handler(ServiceType.SUGGESTION) is suggestion_handler
        assert executor.get_handler(ServiceType.REMINDER) is reminder_handler

    def test_unregister_handler(self, executor: ServiceExecutor):
        """测试取消注册处理器"""
        handler = SuggestionHandler()
        executor.register_handler(ServiceType.SUGGESTION, handler)
        result = executor.unregister_handler(ServiceType.SUGGESTION)
        assert result is True
        assert executor.get_handler(ServiceType.SUGGESTION) is None

    def test_unregister_nonexistent_handler(self, executor: ServiceExecutor):
        """测试取消注册不存在的处理器"""
        result = executor.unregister_handler(ServiceType.SUGGESTION)
        assert result is False

    def test_get_handler_returns_none_for_unregistered(self, executor: ServiceExecutor):
        """测试获取未注册的处理器返回None"""
        assert executor.get_handler(ServiceType.SUGGESTION) is None

    def test_replace_handler(self, executor: ServiceExecutor):
        """测试替换处理器"""
        handler1 = SuggestionHandler()
        handler2 = SuggestionHandler()
        executor.register_handler(ServiceType.SUGGESTION, handler1)
        executor.register_handler(ServiceType.SUGGESTION, handler2)
        assert executor.get_handler(ServiceType.SUGGESTION) is handler2


# ============== ServiceExecutor Execute Tests ==============


class TestServiceExecutorExecute:
    """服务执行器执行测试"""

    def test_execute_with_registered_handler(
        self,
        executor_with_handlers: ServiceExecutor,
        suggestion_service: ServiceDefinition,
        basic_context: TriggerContext,
    ):
        """测试使用已注册处理器执行"""
        result = executor_with_handlers.execute(suggestion_service, basic_context)
        assert result.status == ServiceStatus.COMPLETED
        assert result.service_id == suggestion_service.service_id

    def test_execute_without_handler(
        self,
        executor: ServiceExecutor,
        suggestion_service: ServiceDefinition,
        basic_context: TriggerContext,
    ):
        """测试无处理器时执行失败"""
        result = executor.execute(suggestion_service, basic_context)
        assert result.status == ServiceStatus.FAILED
        assert "handler" in result.message.lower() or "处理器" in result.message

    def test_execute_records_duration(
        self,
        executor_with_handlers: ServiceExecutor,
        suggestion_service: ServiceDefinition,
        basic_context: TriggerContext,
    ):
        """测试执行记录耗时"""
        result = executor_with_handlers.execute(suggestion_service, basic_context)
        assert result.duration_ms >= 0

    def test_execute_records_timestamp(
        self,
        executor_with_handlers: ServiceExecutor,
        suggestion_service: ServiceDefinition,
        basic_context: TriggerContext,
    ):
        """测试执行记录时间戳"""
        before = datetime.now()
        result = executor_with_handlers.execute(suggestion_service, basic_context)
        after = datetime.now()
        assert before <= result.executed_at <= after

    def test_execute_different_service_types(
        self,
        executor_with_handlers: ServiceExecutor,
        suggestion_service: ServiceDefinition,
        reminder_service: ServiceDefinition,
        information_service: ServiceDefinition,
        clarification_service: ServiceDefinition,
        basic_context: TriggerContext,
    ):
        """测试执行不同类型服务"""
        result1 = executor_with_handlers.execute(suggestion_service, basic_context)
        result2 = executor_with_handlers.execute(reminder_service, basic_context)
        result3 = executor_with_handlers.execute(information_service, basic_context)
        result4 = executor_with_handlers.execute(clarification_service, basic_context)
        assert all(
            r.status == ServiceStatus.COMPLETED
            for r in [result1, result2, result3, result4]
        )

    def test_execute_auto_action_without_handler(
        self,
        executor_with_handlers: ServiceExecutor,
        auto_action_service: ServiceDefinition,
        basic_context: TriggerContext,
    ):
        """测试执行无处理器的自动操作服务"""
        result = executor_with_handlers.execute(auto_action_service, basic_context)
        assert result.status == ServiceStatus.FAILED


# ============== ServiceExecutor Execute Plan Tests ==============


class TestServiceExecutorExecutePlan:
    """服务执行器执行计划测试"""

    def test_execute_plan_single_service(
        self,
        executor_with_handlers: ServiceExecutor,
        suggestion_service: ServiceDefinition,
        basic_context: TriggerContext,
    ):
        """测试执行单服务计划"""
        plan = ExecutionPlan(
            services=[suggestion_service],
            execution_order=[suggestion_service.service_id],
        )
        results = executor_with_handlers.execute_plan(plan, basic_context)
        assert len(results) == 1
        assert results[0].status == ServiceStatus.COMPLETED

    def test_execute_plan_multiple_services(
        self,
        executor_with_handlers: ServiceExecutor,
        suggestion_service: ServiceDefinition,
        reminder_service: ServiceDefinition,
        basic_context: TriggerContext,
    ):
        """测试执行多服务计划"""
        plan = ExecutionPlan(
            services=[suggestion_service, reminder_service],
            execution_order=[
                suggestion_service.service_id,
                reminder_service.service_id,
            ],
        )
        results = executor_with_handlers.execute_plan(plan, basic_context)
        assert len(results) == 2
        assert all(r.status == ServiceStatus.COMPLETED for r in results)

    def test_execute_plan_respects_order(
        self,
        executor_with_handlers: ServiceExecutor,
        suggestion_service: ServiceDefinition,
        reminder_service: ServiceDefinition,
        basic_context: TriggerContext,
    ):
        """测试执行计划遵循顺序"""
        plan = ExecutionPlan(
            services=[suggestion_service, reminder_service],
            execution_order=[
                reminder_service.service_id,
                suggestion_service.service_id,
            ],
        )
        results = executor_with_handlers.execute_plan(plan, basic_context)
        assert results[0].service_id == reminder_service.service_id
        assert results[1].service_id == suggestion_service.service_id

    def test_execute_plan_empty(
        self,
        executor_with_handlers: ServiceExecutor,
        basic_context: TriggerContext,
    ):
        """测试执行空计划"""
        plan = ExecutionPlan()
        results = executor_with_handlers.execute_plan(plan, basic_context)
        assert len(results) == 0

    def test_execute_plan_partial_failure(
        self,
        executor_with_handlers: ServiceExecutor,
        suggestion_service: ServiceDefinition,
        auto_action_service: ServiceDefinition,
        basic_context: TriggerContext,
    ):
        """测试执行计划部分失败"""
        plan = ExecutionPlan(
            services=[suggestion_service, auto_action_service],
            execution_order=[
                suggestion_service.service_id,
                auto_action_service.service_id,
            ],
        )
        results = executor_with_handlers.execute_plan(plan, basic_context)
        assert len(results) == 2
        assert results[0].status == ServiceStatus.COMPLETED
        assert results[1].status == ServiceStatus.FAILED


# ============== ServiceExecutor History Tests ==============


class TestServiceExecutorHistory:
    """服务执行器历史记录测试"""

    def test_get_execution_history_empty(self, executor: ServiceExecutor):
        """测试获取空历史记录"""
        history = executor.get_execution_history()
        assert len(history) == 0

    def test_get_execution_history_after_execute(
        self,
        executor_with_handlers: ServiceExecutor,
        suggestion_service: ServiceDefinition,
        basic_context: TriggerContext,
    ):
        """测试执行后获取历史记录"""
        executor_with_handlers.execute(suggestion_service, basic_context)
        history = executor_with_handlers.get_execution_history()
        assert len(history) == 1
        assert history[0].service_id == suggestion_service.service_id

    def test_get_execution_history_multiple(
        self,
        executor_with_handlers: ServiceExecutor,
        suggestion_service: ServiceDefinition,
        reminder_service: ServiceDefinition,
        basic_context: TriggerContext,
    ):
        """测试多次执行后获取历史记录"""
        executor_with_handlers.execute(suggestion_service, basic_context)
        executor_with_handlers.execute(reminder_service, basic_context)
        history = executor_with_handlers.get_execution_history()
        assert len(history) == 2

    def test_get_execution_history_by_service_id(
        self,
        executor_with_handlers: ServiceExecutor,
        suggestion_service: ServiceDefinition,
        reminder_service: ServiceDefinition,
        basic_context: TriggerContext,
    ):
        """测试按服务ID获取历史记录"""
        executor_with_handlers.execute(suggestion_service, basic_context)
        executor_with_handlers.execute(reminder_service, basic_context)
        executor_with_handlers.execute(suggestion_service, basic_context)
        history = executor_with_handlers.get_execution_history(
            service_id=suggestion_service.service_id
        )
        assert len(history) == 2
        assert all(h.service_id == suggestion_service.service_id for h in history)

    def test_get_execution_history_with_limit(
        self,
        executor_with_handlers: ServiceExecutor,
        suggestion_service: ServiceDefinition,
        basic_context: TriggerContext,
    ):
        """测试限制历史记录数量"""
        for _ in range(5):
            executor_with_handlers.execute(suggestion_service, basic_context)
        history = executor_with_handlers.get_execution_history(limit=3)
        assert len(history) == 3

    def test_clear_history(
        self,
        executor_with_handlers: ServiceExecutor,
        suggestion_service: ServiceDefinition,
        basic_context: TriggerContext,
    ):
        """测试清除历史记录"""
        executor_with_handlers.execute(suggestion_service, basic_context)
        executor_with_handlers.clear_history()
        history = executor_with_handlers.get_execution_history()
        assert len(history) == 0

    def test_history_includes_failed_executions(
        self,
        executor_with_handlers: ServiceExecutor,
        auto_action_service: ServiceDefinition,
        basic_context: TriggerContext,
    ):
        """测试历史记录包含失败执行"""
        executor_with_handlers.execute(auto_action_service, basic_context)
        history = executor_with_handlers.get_execution_history()
        assert len(history) == 1
        assert history[0].status == ServiceStatus.FAILED

    def test_history_order_is_chronological(
        self,
        executor_with_handlers: ServiceExecutor,
        suggestion_service: ServiceDefinition,
        reminder_service: ServiceDefinition,
        basic_context: TriggerContext,
    ):
        """测试历史记录按时间顺序"""
        executor_with_handlers.execute(suggestion_service, basic_context)
        time.sleep(0.01)  # 确保时间差
        executor_with_handlers.execute(reminder_service, basic_context)
        history = executor_with_handlers.get_execution_history()
        assert history[0].executed_at <= history[1].executed_at
