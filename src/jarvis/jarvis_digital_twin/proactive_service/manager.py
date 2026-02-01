"""主动服务管理器模块。

整合所有主动服务组件，提供统一的服务管理接口。
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from jarvis.jarvis_digital_twin.proactive_service.feedback_learner import (
    FeedbackLearner,
    LearningResult,
    ServiceStats,
)
from jarvis.jarvis_digital_twin.proactive_service.service_executor import (
    ServiceExecutor,
)
from jarvis.jarvis_digital_twin.proactive_service.service_orchestrator import (
    ServiceOrchestrator,
)
from jarvis.jarvis_digital_twin.proactive_service.service_trigger import (
    ServiceTrigger,
)
from jarvis.jarvis_digital_twin.proactive_service.types import (
    FeedbackType,
    ServiceDefinition,
    ServiceHandlerProtocol,
    ServiceResult,
    TriggerContext,
    TriggerEvaluatorProtocol,
)

if TYPE_CHECKING:
    from jarvis.jarvis_digital_twin.prediction import NeedInferrer, TimingJudge
    from jarvis.jarvis_digital_twin.user_profile import PreferenceLearner


class ProactiveServiceManager:
    """主动服务管理器。

    整合触发器、编排器、执行器和学习器，提供统一的主动服务接口。

    Attributes:
        _trigger: 服务触发器
        _orchestrator: 服务编排器
        _executor: 服务执行器
        _learner: 反馈学习器
    """

    def __init__(
        self,
        timing_judge: Optional["TimingJudge"] = None,
        need_inferrer: Optional["NeedInferrer"] = None,
        preference_learner: Optional["PreferenceLearner"] = None,
    ) -> None:
        """初始化主动服务管理器。

        Args:
            timing_judge: 时机判断器（来自阶段5.2预判引擎）
            need_inferrer: 需求推理器（来自阶段5.2预判引擎）
            preference_learner: 偏好学习器（来自阶段5.1用户画像）
        """
        self._trigger = ServiceTrigger(timing_judge)
        self._orchestrator = ServiceOrchestrator(need_inferrer)
        self._executor = ServiceExecutor()
        self._learner = FeedbackLearner(preference_learner)

        # 内部状态
        self._enabled = True
        self._last_results: List[ServiceResult] = []

    @property
    def enabled(self) -> bool:
        """获取管理器启用状态。"""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """设置管理器启用状态。"""
        self._enabled = value

    def process_context(
        self,
        user_input: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        user_profile: Optional[Any] = None,
        predictions: Optional[Dict[str, Any]] = None,
    ) -> List[ServiceResult]:
        """处理上下文，执行主动服务。

        完整流程：触发检查 -> 编排 -> 执行 -> 返回结果

        Args:
            user_input: 用户输入
            conversation_history: 对话历史
            user_profile: 用户画像数据
            predictions: 预测结果

        Returns:
            服务执行结果列表
        """
        if not self._enabled:
            return []

        # 构建触发上下文
        context = TriggerContext(
            user_input=user_input,
            conversation_history=conversation_history or [],
            user_profile=user_profile,
            predictions=predictions,
            timestamp=datetime.now(),
        )

        # 1. 触发检查：获取满足触发条件的服务
        triggered_services = self._trigger.check_trigger(context)
        if not triggered_services:
            self._last_results = []
            return []

        # 2. 编排：排序和过滤服务
        orchestrated_services = self._orchestrator.orchestrate(
            triggered_services, context
        )
        if not orchestrated_services:
            self._last_results = []
            return []

        # 3. 执行：逐个执行服务
        results: List[ServiceResult] = []
        for service_def in orchestrated_services:
            result = self._executor.execute(service_def, context)
            results.append(result)

        # 4. 记录结果
        self._last_results = results

        return results

    def register_service(
        self,
        service_def: ServiceDefinition,
        handler: Optional[ServiceHandlerProtocol] = None,
        evaluator: Optional[TriggerEvaluatorProtocol] = None,
    ) -> None:
        """注册服务。

        包括服务定义、处理器和触发评估器。

        Args:
            service_def: 服务定义
            handler: 服务处理器（可选）
            evaluator: 触发评估器（可选）
        """
        # 注册到触发器
        self._trigger.register_trigger(service_def, evaluator)

        # 注册处理器到执行器
        if handler:
            self._executor.register_handler(service_def.service_type, handler)

    def unregister_service(self, service_id: str) -> bool:
        """注销服务。

        Args:
            service_id: 服务ID

        Returns:
            是否成功注销
        """
        return self._trigger.unregister_trigger(service_id)

    def record_feedback(
        self,
        service_id: str,
        feedback_type: FeedbackType,
        user_comment: Optional[str] = None,
    ) -> None:
        """记录用户反馈。

        Args:
            service_id: 服务ID
            feedback_type: 反馈类型
            user_comment: 用户评论（可选）
        """
        self._learner.record_feedback(service_id, feedback_type, user_comment)

    def get_service_stats(self, service_id: str) -> Optional[ServiceStats]:
        """获取服务统计信息。

        Args:
            service_id: 服务ID

        Returns:
            服务统计信息，如果不存在则返回None
        """
        return self._learner.get_service_stats(service_id)

    def learn_and_adjust(self) -> LearningResult:
        """学习并调整策略。

        基于用户反馈学习，生成阈值调整建议。

        Returns:
            学习结果
        """
        return self._learner.learn()

    def get_last_results(self) -> List[ServiceResult]:
        """获取最近一次执行的结果。

        Returns:
            最近一次执行的服务结果列表
        """
        return self._last_results.copy()

    def get_pending_services(self) -> List[ServiceDefinition]:
        """获取待处理的服务。

        Returns:
            待处理的服务定义列表
        """
        return self._trigger.get_pending_triggers()

    def get_execution_history(self) -> List[ServiceResult]:
        """获取执行历史。

        Returns:
            执行历史列表
        """
        return self._executor.get_execution_history()

    def clear_execution_history(self) -> None:
        """清除执行历史。"""
        self._executor.clear_history()

    def get_registered_services(self) -> List[ServiceDefinition]:
        """获取所有已注册的服务。

        Returns:
            已注册的服务定义列表
        """
        return list(self._trigger.registered_services.values())

    def is_service_registered(self, service_id: str) -> bool:
        """检查服务是否已注册。

        Args:
            service_id: 服务ID

        Returns:
            是否已注册
        """
        return service_id in self._trigger.registered_services
