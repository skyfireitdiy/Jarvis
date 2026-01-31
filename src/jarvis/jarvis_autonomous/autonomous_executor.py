"""自主执行器模块

在用户授权范围内自主执行任务。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class AuthorizationLevel(Enum):
    """授权级别枚举"""

    NONE = "none"  # 无授权，所有操作需确认
    READ_ONLY = "read_only"  # 只读，可以读取但不能修改
    LIMITED = "limited"  # 有限，可以执行低风险操作
    STANDARD = "standard"  # 标准，可以执行大部分操作
    FULL = "full"  # 完全，可以执行所有操作


class OperationRisk(Enum):
    """操作风险级别"""

    LOW = "low"  # 低风险：读取、分析、建议
    MEDIUM = "medium"  # 中风险：修改单个文件、添加代码
    HIGH = "high"  # 高风险：删除文件、修改配置、重构
    CRITICAL = "critical"  # 关键风险：系统级操作、不可逆操作


@dataclass
class ExecutionContext:
    """执行上下文

    包含执行任务所需的上下文信息。
    """

    task_id: str
    task_name: str
    task_description: str
    goal_id: Optional[str] = None
    plan_id: Optional[str] = None
    authorization_level: AuthorizationLevel = AuthorizationLevel.LIMITED
    allowed_operations: list[str] = field(default_factory=list)
    forbidden_operations: list[str] = field(default_factory=list)
    max_retries: int = 3
    timeout_seconds: int = 300


@dataclass
class ExecutionResult:
    """执行结果

    记录任务执行的结果。
    """

    task_id: str
    success: bool
    output: str
    error: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    retries: int = 0
    operations_performed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "retries": self.retries,
            "operations_performed": self.operations_performed,
        }


class AutonomousExecutor:
    """自主执行器

    在用户授权范围内自主执行任务。
    与task_list_manager协作，负责判断是否可以自主执行。
    """

    def __init__(
        self, default_authorization: AuthorizationLevel = AuthorizationLevel.LIMITED
    ) -> None:
        """初始化自主执行器

        Args:
            default_authorization: 默认授权级别
        """
        self.default_authorization = default_authorization
        self.execution_history: list[ExecutionResult] = []

        # 操作风险映射
        self.operation_risks: dict[str, OperationRisk] = {
            # 低风险操作
            "read_code": OperationRisk.LOW,
            "search": OperationRisk.LOW,
            "analyze": OperationRisk.LOW,
            "suggest": OperationRisk.LOW,
            "list_files": OperationRisk.LOW,
            "get_info": OperationRisk.LOW,
            # 中风险操作
            "edit_file": OperationRisk.MEDIUM,
            "create_file": OperationRisk.MEDIUM,
            "add_code": OperationRisk.MEDIUM,
            "run_test": OperationRisk.MEDIUM,
            # 高风险操作
            "delete_file": OperationRisk.HIGH,
            "refactor": OperationRisk.HIGH,
            "modify_config": OperationRisk.HIGH,
            "git_commit": OperationRisk.HIGH,
            # 关键风险操作
            "git_push": OperationRisk.CRITICAL,
            "deploy": OperationRisk.CRITICAL,
            "system_command": OperationRisk.CRITICAL,
            "delete_directory": OperationRisk.CRITICAL,
        }

        # 授权级别允许的最高风险
        self.authorization_limits: dict[AuthorizationLevel, OperationRisk] = {
            AuthorizationLevel.NONE: OperationRisk.LOW,  # 只能读取
            AuthorizationLevel.READ_ONLY: OperationRisk.LOW,
            AuthorizationLevel.LIMITED: OperationRisk.MEDIUM,
            AuthorizationLevel.STANDARD: OperationRisk.HIGH,
            AuthorizationLevel.FULL: OperationRisk.CRITICAL,
        }

    def can_execute_autonomously(
        self,
        operation: str,
        context: ExecutionContext,
    ) -> tuple[bool, str]:
        """判断是否可以自主执行操作

        Args:
            operation: 操作名称
            context: 执行上下文

        Returns:
            (是否可以自主执行, 原因说明)
        """
        # 检查是否在禁止列表中
        if operation in context.forbidden_operations:
            return False, f"操作 '{operation}' 在禁止列表中"

        # 检查是否在允许列表中（如果有指定）
        if context.allowed_operations and operation not in context.allowed_operations:
            return False, f"操作 '{operation}' 不在允许列表中"

        # 获取操作风险级别
        operation_risk = self.operation_risks.get(operation, OperationRisk.HIGH)

        # 获取授权允许的最高风险
        max_allowed_risk = self.authorization_limits.get(
            context.authorization_level, OperationRisk.LOW
        )

        # 比较风险级别
        risk_order = [
            OperationRisk.LOW,
            OperationRisk.MEDIUM,
            OperationRisk.HIGH,
            OperationRisk.CRITICAL,
        ]

        if risk_order.index(operation_risk) <= risk_order.index(max_allowed_risk):
            return True, f"操作 '{operation}' 在授权范围内"
        else:
            return (
                False,
                f"操作 '{operation}' 风险级别({operation_risk.value})超出授权范围({max_allowed_risk.value})",
            )

    def should_ask_confirmation(
        self,
        operation: str,
        context: ExecutionContext,
    ) -> tuple[bool, str]:
        """判断是否需要请求用户确认

        Args:
            operation: 操作名称
            context: 执行上下文

        Returns:
            (是否需要确认, 确认提示信息)
        """
        can_execute, reason = self.can_execute_autonomously(operation, context)

        if can_execute:
            return False, ""

        # 生成确认提示
        operation_risk = self.operation_risks.get(operation, OperationRisk.HIGH)
        prompt = f"操作 '{operation}' (风险级别: {operation_risk.value}) 需要您的确认。\n原因: {reason}\n是否继续执行？"

        return True, prompt

    def create_execution_context(
        self,
        task_id: str,
        task_name: str,
        task_description: str,
        goal_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        authorization_level: Optional[AuthorizationLevel] = None,
    ) -> ExecutionContext:
        """创建执行上下文

        Args:
            task_id: 任务ID
            task_name: 任务名称
            task_description: 任务描述
            goal_id: 目标ID
            plan_id: 计划ID
            authorization_level: 授权级别

        Returns:
            执行上下文
        """
        return ExecutionContext(
            task_id=task_id,
            task_name=task_name,
            task_description=task_description,
            goal_id=goal_id,
            plan_id=plan_id,
            authorization_level=authorization_level or self.default_authorization,
        )

    def record_execution(
        self,
        task_id: str,
        success: bool,
        output: str,
        error: Optional[str] = None,
        operations: Optional[list[str]] = None,
    ) -> ExecutionResult:
        """记录执行结果

        Args:
            task_id: 任务ID
            success: 是否成功
            output: 输出内容
            error: 错误信息
            operations: 执行的操作列表

        Returns:
            执行结果
        """
        result = ExecutionResult(
            task_id=task_id,
            success=success,
            output=output,
            error=error,
            completed_at=datetime.now(),
            operations_performed=operations or [],
        )
        self.execution_history.append(result)
        return result

    def get_execution_summary(self) -> dict[str, Any]:
        """获取执行摘要

        Returns:
            执行摘要信息
        """
        total = len(self.execution_history)
        successful = sum(1 for r in self.execution_history if r.success)
        failed = total - successful

        return {
            "total_executions": total,
            "successful": successful,
            "failed": failed,
            "success_rate": (successful / total * 100) if total > 0 else 0,
            "recent_executions": [r.to_dict() for r in self.execution_history[-5:]],
        }

    def suggest_authorization_level(self, task_description: str) -> AuthorizationLevel:
        """根据任务描述建议授权级别

        Args:
            task_description: 任务描述

        Returns:
            建议的授权级别
        """
        description_lower = task_description.lower()

        # 关键词匹配
        if any(
            kw in description_lower
            for kw in ["删除", "部署", "发布", "push", "deploy", "delete"]
        ):
            return AuthorizationLevel.NONE  # 需要完全确认
        elif any(
            kw in description_lower for kw in ["重构", "修改配置", "refactor", "config"]
        ):
            return AuthorizationLevel.LIMITED
        elif any(
            kw in description_lower
            for kw in ["实现", "开发", "编写", "implement", "develop"]
        ):
            return AuthorizationLevel.STANDARD
        elif any(
            kw in description_lower
            for kw in ["分析", "查看", "读取", "analyze", "read"]
        ):
            return AuthorizationLevel.READ_ONLY
        else:
            return AuthorizationLevel.LIMITED

    def get_allowed_operations(
        self, authorization_level: AuthorizationLevel
    ) -> list[str]:
        """获取授权级别允许的操作列表

        Args:
            authorization_level: 授权级别

        Returns:
            允许的操作列表
        """
        max_risk = self.authorization_limits.get(authorization_level, OperationRisk.LOW)
        risk_order = [
            OperationRisk.LOW,
            OperationRisk.MEDIUM,
            OperationRisk.HIGH,
            OperationRisk.CRITICAL,
        ]
        max_risk_index = risk_order.index(max_risk)

        return [
            op
            for op, risk in self.operation_risks.items()
            if risk_order.index(risk) <= max_risk_index
        ]
