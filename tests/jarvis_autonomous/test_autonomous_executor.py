"""自主执行器测试"""

import pytest

from jarvis.jarvis_autonomous.autonomous_executor import (
    AuthorizationLevel,
    AutonomousExecutor,
    ExecutionContext,
    ExecutionResult,
    OperationRisk,
)


class TestOperationRisk:
    """OperationRisk测试"""

    def test_risk_levels(self) -> None:
        """测试风险等级"""
        assert OperationRisk.LOW.value == "low"
        assert OperationRisk.MEDIUM.value == "medium"
        assert OperationRisk.HIGH.value == "high"
        assert OperationRisk.CRITICAL.value == "critical"


class TestAuthorizationLevel:
    """AuthorizationLevel测试"""

    def test_authorization_levels(self) -> None:
        """测试授权等级"""
        assert AuthorizationLevel.NONE.value == "none"
        assert AuthorizationLevel.READ_ONLY.value == "read_only"
        assert AuthorizationLevel.LIMITED.value == "limited"
        assert AuthorizationLevel.STANDARD.value == "standard"
        assert AuthorizationLevel.FULL.value == "full"


class TestExecutionContext:
    """ExecutionContext测试"""

    def test_context_creation(self) -> None:
        """测试上下文创建"""
        context = ExecutionContext(
            task_id="task-1",
            task_name="测试任务",
            task_description="任务描述",
            authorization_level=AuthorizationLevel.STANDARD,
        )
        assert context.task_id == "task-1"
        assert context.authorization_level == AuthorizationLevel.STANDARD
        assert context.max_retries == 3

    def test_context_with_allowed_operations(self) -> None:
        """测试带允许操作列表的上下文"""
        context = ExecutionContext(
            task_id="task-2",
            task_name="受限任务",
            task_description="只允许读取",
            authorization_level=AuthorizationLevel.READ_ONLY,
            allowed_operations=["read_code", "search"],
        )
        assert "read_code" in context.allowed_operations
        assert len(context.forbidden_operations) == 0


class TestExecutionResult:
    """ExecutionResult测试"""

    def test_result_creation(self) -> None:
        """测试结果创建"""
        result = ExecutionResult(
            task_id="task-1",
            success=True,
            output="执行成功",
        )
        assert result.success is True
        assert result.error is None

    def test_result_to_dict(self) -> None:
        """测试结果转字典"""
        result = ExecutionResult(
            task_id="task-2",
            success=False,
            output="",
            error="执行失败",
        )
        data = result.to_dict()
        assert data["task_id"] == "task-2"
        assert data["success"] is False
        assert data["error"] == "执行失败"


class TestAutonomousExecutor:
    """AutonomousExecutor测试"""

    @pytest.fixture
    def executor(self) -> AutonomousExecutor:
        """创建执行器"""
        return AutonomousExecutor()

    def test_can_execute_low_risk(self, executor: AutonomousExecutor) -> None:
        """测试低风险操作可以执行"""
        context = executor.create_execution_context(
            task_id="task-1",
            task_name="读取代码",
            task_description="读取源代码",
            authorization_level=AuthorizationLevel.READ_ONLY,
        )
        can_exec, reason = executor.can_execute_autonomously("read_code", context)
        assert can_exec is True

    def test_cannot_execute_high_risk_with_low_auth(
        self, executor: AutonomousExecutor
    ) -> None:
        """测试低授权不能执行高风险操作"""
        context = executor.create_execution_context(
            task_id="task-2",
            task_name="删除文件",
            task_description="删除临时文件",
            authorization_level=AuthorizationLevel.READ_ONLY,
        )
        can_exec, reason = executor.can_execute_autonomously("delete_file", context)
        assert can_exec is False
        assert "风险" in reason or "授权" in reason

    def test_can_execute_medium_risk_with_limited_auth(
        self, executor: AutonomousExecutor
    ) -> None:
        """测试有限授权可以执行中风险操作"""
        context = executor.create_execution_context(
            task_id="task-3",
            task_name="编辑文件",
            task_description="修改代码",
            authorization_level=AuthorizationLevel.LIMITED,
        )
        can_exec, reason = executor.can_execute_autonomously("edit_file", context)
        assert can_exec is True

    def test_forbidden_operations(self, executor: AutonomousExecutor) -> None:
        """测试禁止操作列表"""
        context = ExecutionContext(
            task_id="task-4",
            task_name="受限任务",
            task_description="禁止删除",
            authorization_level=AuthorizationLevel.FULL,
            forbidden_operations=["delete_file"],
        )
        can_exec, reason = executor.can_execute_autonomously("delete_file", context)
        assert can_exec is False
        assert "禁止" in reason

    def test_should_ask_confirmation(self, executor: AutonomousExecutor) -> None:
        """测试是否需要确认"""
        context = executor.create_execution_context(
            task_id="task-5",
            task_name="高风险操作",
            task_description="删除目录",
            authorization_level=AuthorizationLevel.LIMITED,
        )
        need_confirm, prompt = executor.should_ask_confirmation(
            "delete_directory", context
        )
        assert need_confirm is True
        assert "确认" in prompt

    def test_record_execution(self, executor: AutonomousExecutor) -> None:
        """测试记录执行结果"""
        result = executor.record_execution(
            task_id="task-6",
            success=True,
            output="执行完成",
            operations=["read_code", "edit_file"],
        )
        assert result.success is True
        assert len(result.operations_performed) == 2

    def test_get_execution_summary(self, executor: AutonomousExecutor) -> None:
        """测试获取执行摘要"""
        executor.record_execution("task-1", True, "成功")
        executor.record_execution("task-2", False, "", error="失败")
        summary = executor.get_execution_summary()
        assert summary["total_executions"] == 2
        assert summary["successful"] == 1
        assert summary["failed"] == 1

    def test_suggest_authorization_level(self, executor: AutonomousExecutor) -> None:
        """测试建议授权级别"""
        # 删除操作需要完全确认
        level = executor.suggest_authorization_level("删除所有临时文件")
        assert level == AuthorizationLevel.NONE

        # 分析操作只需只读
        level = executor.suggest_authorization_level("分析代码结构")
        assert level == AuthorizationLevel.READ_ONLY

        # 开发操作需要标准权限
        level = executor.suggest_authorization_level("实现新功能")
        assert level == AuthorizationLevel.STANDARD

    def test_get_allowed_operations(self, executor: AutonomousExecutor) -> None:
        """测试获取允许的操作"""
        # 只读权限只能执行低风险操作
        ops = executor.get_allowed_operations(AuthorizationLevel.READ_ONLY)
        assert "read_code" in ops
        assert "delete_file" not in ops

        # 完全权限可以执行所有操作
        ops = executor.get_allowed_operations(AuthorizationLevel.FULL)
        assert "delete_file" in ops
        assert "deploy" in ops
