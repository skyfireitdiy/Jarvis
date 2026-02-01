"""服务执行器模块。

负责执行具体的主动服务，管理服务处理器和执行历史。
"""

import time
from datetime import datetime
from typing import Dict, List, Optional

from jarvis.jarvis_digital_twin.proactive_service.types import (
    ExecutionPlan,
    ServiceDefinition,
    ServiceHandlerProtocol,
    ServiceResult,
    ServiceStatus,
    ServiceType,
    TriggerContext,
)


class SuggestionHandler:
    """建议类服务处理器。

    生成建议消息并格式化输出。
    """

    def can_handle(self, service_type: ServiceType) -> bool:
        """检查是否能处理指定类型的服务。

        Args:
            service_type: 服务类型

        Returns:
            是否能处理
        """
        return service_type == ServiceType.SUGGESTION

    def handle(self, context: TriggerContext) -> ServiceResult:
        """处理服务请求。

        Args:
            context: 触发上下文

        Returns:
            服务执行结果
        """
        # 基于上下文生成建议
        user_input = context.user_input
        suggestion = f"基于您的输入'{user_input[:50]}...'，建议您可以考虑以下方案"

        return ServiceResult(
            service_id="suggestion_handler",
            status=ServiceStatus.COMPLETED,
            message="建议已生成",
            data={"suggestion": suggestion, "type": "code_improvement"},
        )


class ReminderHandler:
    """提醒类服务处理器。

    生成提醒消息，支持延迟提醒。
    """

    def can_handle(self, service_type: ServiceType) -> bool:
        """检查是否能处理指定类型的服务。

        Args:
            service_type: 服务类型

        Returns:
            是否能处理
        """
        return service_type == ServiceType.REMINDER

    def handle(self, context: TriggerContext) -> ServiceResult:
        """处理服务请求。

        Args:
            context: 触发上下文

        Returns:
            服务执行结果
        """
        # 生成提醒消息
        reminder = "请注意：您可能需要关注当前任务的进度"

        return ServiceResult(
            service_id="reminder_handler",
            status=ServiceStatus.COMPLETED,
            message="提醒已生成",
            data={"reminder": reminder, "delay_seconds": 0},
        )


class InformationHandler:
    """信息提供类服务处理器。

    提供相关信息并格式化展示。
    """

    def can_handle(self, service_type: ServiceType) -> bool:
        """检查是否能处理指定类型的服务。

        Args:
            service_type: 服务类型

        Returns:
            是否能处理
        """
        return service_type == ServiceType.INFORMATION

    def handle(self, context: TriggerContext) -> ServiceResult:
        """处理服务请求。

        Args:
            context: 触发上下文

        Returns:
            服务执行结果
        """
        # 提供相关信息
        information = "以下是与您查询相关的信息"

        return ServiceResult(
            service_id="information_handler",
            status=ServiceStatus.COMPLETED,
            message="信息已提供",
            data={"information": information, "sources": []},
        )


class ClarificationHandler:
    """澄清请求类服务处理器。

    生成澄清问题，收集用户回答。
    """

    def can_handle(self, service_type: ServiceType) -> bool:
        """检查是否能处理指定类型的服务。

        Args:
            service_type: 服务类型

        Returns:
            是否能处理
        """
        return service_type == ServiceType.CLARIFICATION

    def handle(self, context: TriggerContext) -> ServiceResult:
        """处理服务请求。

        Args:
            context: 触发上下文

        Returns:
            服务执行结果
        """
        # 生成澄清问题
        question = "请问您能否提供更多细节？"

        return ServiceResult(
            service_id="clarification_handler",
            status=ServiceStatus.COMPLETED,
            message="澄清问题已生成",
            data={"question": question, "options": []},
        )


class ServiceExecutor:
    """服务执行器。

    负责执行具体的主动服务，管理服务处理器和执行历史。
    """

    def __init__(self) -> None:
        """初始化执行器。"""
        self._handlers: Dict[ServiceType, ServiceHandlerProtocol] = {}
        self._execution_history: List[ServiceResult] = []

    def register_handler(
        self,
        service_type: ServiceType,
        handler: ServiceHandlerProtocol,
    ) -> None:
        """注册服务处理器。

        Args:
            service_type: 服务类型
            handler: 服务处理器实现
        """
        self._handlers[service_type] = handler

    def unregister_handler(self, service_type: ServiceType) -> bool:
        """取消注册处理器。

        Args:
            service_type: 服务类型

        Returns:
            是否成功取消注册
        """
        if service_type in self._handlers:
            del self._handlers[service_type]
            return True
        return False

    def get_handler(
        self, service_type: ServiceType
    ) -> Optional[ServiceHandlerProtocol]:
        """获取指定类型的处理器。

        Args:
            service_type: 服务类型

        Returns:
            服务处理器，如果未注册则返回None
        """
        return self._handlers.get(service_type)

    def execute(
        self,
        service: ServiceDefinition,
        context: TriggerContext,
    ) -> ServiceResult:
        """执行单个服务。

        Args:
            service: 服务定义
            context: 触发上下文

        Returns:
            服务执行结果
        """
        start_time = time.time()

        # 获取处理器
        handler = self._handlers.get(service.service_type)
        if handler is None:
            result = ServiceResult(
                service_id=service.service_id,
                status=ServiceStatus.FAILED,
                message=f"未找到服务类型 {service.service_type.value} 的处理器",
                executed_at=datetime.now(),
                duration_ms=0,
            )
            self._execution_history.append(result)
            return result

        try:
            # 执行处理器
            handler_result = handler.handle(context)

            # 计算耗时
            duration_ms = int((time.time() - start_time) * 1000)

            # 创建结果
            result = ServiceResult(
                service_id=service.service_id,
                status=handler_result.status,
                message=handler_result.message,
                data=handler_result.data,
                executed_at=datetime.now(),
                duration_ms=duration_ms,
            )
        except Exception as e:
            # 处理异常
            duration_ms = int((time.time() - start_time) * 1000)
            result = ServiceResult(
                service_id=service.service_id,
                status=ServiceStatus.FAILED,
                message=f"执行失败: {str(e)}",
                executed_at=datetime.now(),
                duration_ms=duration_ms,
            )

        # 记录历史
        self._execution_history.append(result)
        return result

    def execute_plan(
        self,
        plan: ExecutionPlan,
        context: TriggerContext,
    ) -> List[ServiceResult]:
        """执行执行计划。

        Args:
            plan: 执行计划
            context: 触发上下文

        Returns:
            所有服务的执行结果列表
        """
        results: List[ServiceResult] = []

        # 如果没有执行顺序，按服务列表顺序执行
        if not plan.execution_order:
            for service in plan.services:
                result = self.execute(service, context)
                results.append(result)
            return results

        # 按执行顺序执行
        service_map = {s.service_id: s for s in plan.services}
        for service_id in plan.execution_order:
            maybe_service = service_map.get(service_id)
            if maybe_service is not None:
                result = self.execute(maybe_service, context)
                results.append(result)

        return results

    def get_execution_history(
        self,
        service_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[ServiceResult]:
        """获取执行历史。

        Args:
            service_id: 服务ID（可选，用于过滤）
            limit: 返回结果的最大数量

        Returns:
            执行历史列表
        """
        if service_id:
            filtered = [
                r for r in self._execution_history if r.service_id == service_id
            ]
            return filtered[:limit]
        return self._execution_history[:limit]

    def clear_history(self) -> None:
        """清除执行历史。"""
        self._execution_history.clear()
