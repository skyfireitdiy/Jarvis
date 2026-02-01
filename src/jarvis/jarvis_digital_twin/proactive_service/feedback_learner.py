"""反馈学习器模块。

负责收集用户反馈并优化服务策略。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from jarvis.jarvis_digital_twin.proactive_service.types import (
    FeedbackType,
    ServiceFeedback,
)

try:
    from jarvis.jarvis_digital_twin.user_profile.preference_learner import (
        PreferenceLearner,
        InteractionData,
    )
except ImportError:
    PreferenceLearner = None  # type: ignore
    InteractionData = None  # type: ignore


@dataclass
class ServiceStats:
    """服务统计数据类。

    记录单个服务的统计信息。
    """

    service_id: str
    total_triggers: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    ignored_count: int = 0
    deferred_count: int = 0
    modified_count: int = 0
    last_feedback_at: Optional[datetime] = None

    @property
    def acceptance_rate(self) -> float:
        """计算接受率。

        Returns:
            接受率 (0-1)，如果没有触发则返回0.5
        """
        if self.total_triggers == 0:
            return 0.5
        # 接受和修改后接受都算作接受
        accepted = self.accepted_count + self.modified_count
        return accepted / self.total_triggers

    @property
    def rejection_rate(self) -> float:
        """计算拒绝率。

        Returns:
            拒绝率 (0-1)
        """
        if self.total_triggers == 0:
            return 0.0
        return self.rejected_count / self.total_triggers

    @property
    def ignore_rate(self) -> float:
        """计算忽略率。

        Returns:
            忽略率 (0-1)
        """
        if self.total_triggers == 0:
            return 0.0
        return self.ignored_count / self.total_triggers


@dataclass
class LearningResult:
    """学习结果数据类。

    记录从反馈中学习的结果。
    """

    # 服务ID到建议调整值的映射
    adjustments: Dict[str, float] = field(default_factory=dict)
    # 学习洞察列表
    insights: List[str] = field(default_factory=list)
    # 学习置信度
    confidence: float = 0.5
    # 学习时间
    learned_at: datetime = field(default_factory=datetime.now)


class FeedbackLearner:
    """反馈学习器。

    负责收集用户反馈并优化服务策略。
    """

    # 学习策略阈值
    LOW_ACCEPTANCE_THRESHOLD = 0.3  # 接受率低于此值时提高阈值
    HIGH_ACCEPTANCE_THRESHOLD = 0.8  # 接受率高于此值时降低阈值
    CONSECUTIVE_REJECTION_LIMIT = 3  # 连续拒绝次数限制

    # 阈值调整幅度
    THRESHOLD_INCREASE_STEP = 0.1  # 提高阈值的步长
    THRESHOLD_DECREASE_STEP = 0.05  # 降低阈值的步长

    # 默认阈值
    DEFAULT_THRESHOLD = 0.5

    def __init__(
        self,
        preference_learner: Optional["PreferenceLearner"] = None,
    ) -> None:
        """初始化反馈学习器。

        Args:
            preference_learner: 偏好学习器（来自阶段5.1）
        """
        self._preference_learner = preference_learner
        self._feedback_history: List[ServiceFeedback] = []
        self._service_stats: Dict[str, ServiceStats] = {}
        self._threshold_adjustments: Dict[str, float] = {}
        self._consecutive_rejections: Dict[str, int] = {}
        self._disabled_services: set[str] = set()

    def record_feedback(
        self,
        service_id: str,
        feedback_type: FeedbackType,
        user_comment: Optional[str] = None,
    ) -> ServiceFeedback:
        """记录用户反馈。

        Args:
            service_id: 服务ID
            feedback_type: 反馈类型
            user_comment: 用户评论

        Returns:
            创建的反馈记录
        """
        # 创建反馈记录
        feedback = ServiceFeedback(
            service_id=service_id,
            feedback_type=feedback_type,
            user_comment=user_comment,
            recorded_at=datetime.now(),
        )

        # 保存到历史
        self._feedback_history.append(feedback)

        # 更新服务统计
        self._update_service_stats(service_id, feedback_type)

        # 更新连续拒绝计数
        self._update_consecutive_rejections(service_id, feedback_type)

        # 如果有偏好学习器，同步学习
        if self._preference_learner is not None and InteractionData is not None:
            interaction = InteractionData(
                content=f"Service feedback: {feedback_type.value}",
                interaction_type="feedback",
                tags=["service_feedback", service_id, feedback_type.value],
                metadata={
                    "service_id": service_id,
                    "feedback_type": feedback_type.value,
                    "user_comment": user_comment,
                },
            )
            self._preference_learner.learn_from_interaction(interaction)

        return feedback

    def _update_service_stats(
        self,
        service_id: str,
        feedback_type: FeedbackType,
    ) -> None:
        """更新服务统计。

        Args:
            service_id: 服务ID
            feedback_type: 反馈类型
        """
        # 确保统计对象存在
        if service_id not in self._service_stats:
            self._service_stats[service_id] = ServiceStats(service_id=service_id)

        stats = self._service_stats[service_id]
        stats.total_triggers += 1
        stats.last_feedback_at = datetime.now()

        # 根据反馈类型更新计数
        if feedback_type == FeedbackType.ACCEPTED:
            stats.accepted_count += 1
        elif feedback_type == FeedbackType.REJECTED:
            stats.rejected_count += 1
        elif feedback_type == FeedbackType.IGNORED:
            stats.ignored_count += 1
        elif feedback_type == FeedbackType.DEFERRED:
            stats.deferred_count += 1
        elif feedback_type == FeedbackType.MODIFIED:
            stats.modified_count += 1

    def _update_consecutive_rejections(
        self,
        service_id: str,
        feedback_type: FeedbackType,
    ) -> None:
        """更新连续拒绝计数。

        Args:
            service_id: 服务ID
            feedback_type: 反馈类型
        """
        if feedback_type == FeedbackType.REJECTED:
            self._consecutive_rejections[service_id] = (
                self._consecutive_rejections.get(service_id, 0) + 1
            )
            # 连续拒绝达到限制时禁用服务
            if (
                self._consecutive_rejections[service_id]
                >= self.CONSECUTIVE_REJECTION_LIMIT
            ):
                self._disabled_services.add(service_id)
        else:
            # 非拒绝反馈重置计数
            self._consecutive_rejections[service_id] = 0
            # 如果服务被禁用，接受反馈可以重新启用
            if feedback_type in (FeedbackType.ACCEPTED, FeedbackType.MODIFIED):
                self._disabled_services.discard(service_id)

    def learn(self) -> LearningResult:
        """从反馈中学习。

        Returns:
            学习结果，包含调整建议
        """
        result = LearningResult()
        insights: List[str] = []

        for service_id, stats in self._service_stats.items():
            # 跳过样本量不足的服务
            if stats.total_triggers < 3:
                continue

            acceptance_rate = stats.acceptance_rate
            adjustment = 0.0

            # 接受率低于阈值：提高触发阈值
            if acceptance_rate < self.LOW_ACCEPTANCE_THRESHOLD:
                adjustment = self.THRESHOLD_INCREASE_STEP
                insights.append(
                    f"服务 {service_id} 接受率较低 ({acceptance_rate:.1%})，"
                    f"建议提高触发阈值"
                )

            # 接受率高于阈值：降低触发阈值
            elif acceptance_rate > self.HIGH_ACCEPTANCE_THRESHOLD:
                adjustment = -self.THRESHOLD_DECREASE_STEP
                insights.append(
                    f"服务 {service_id} 接受率较高 ({acceptance_rate:.1%})，"
                    f"可以降低触发阈值"
                )

            # 忽略率过高：可能需要调整触发时机
            if stats.ignore_rate > 0.5:
                insights.append(
                    f"服务 {service_id} 忽略率较高 ({stats.ignore_rate:.1%})，"
                    f"建议调整触发时机"
                )

            if adjustment != 0.0:
                result.adjustments[service_id] = adjustment

        # 检查被禁用的服务
        for service_id in self._disabled_services:
            insights.append(f"服务 {service_id} 因连续被拒绝已暂时禁用")

        result.insights = insights

        # 计算学习置信度（基于样本量）
        total_samples = sum(s.total_triggers for s in self._service_stats.values())
        if total_samples >= 100:
            result.confidence = 0.9
        elif total_samples >= 50:
            result.confidence = 0.7
        elif total_samples >= 20:
            result.confidence = 0.5
        else:
            result.confidence = 0.3

        return result

    def adjust_threshold(
        self,
        service_id: str,
        adjustment: float,
    ) -> float:
        """调整服务触发阈值。

        Args:
            service_id: 服务ID
            adjustment: 调整值（正数提高阈值，负数降低）

        Returns:
            调整后的阈值
        """
        current = self._threshold_adjustments.get(service_id, self.DEFAULT_THRESHOLD)
        new_threshold = max(0.0, min(1.0, current + adjustment))
        self._threshold_adjustments[service_id] = new_threshold
        return new_threshold

    def get_threshold(self, service_id: str) -> float:
        """获取服务的当前阈值。

        Args:
            service_id: 服务ID

        Returns:
            当前阈值
        """
        return self._threshold_adjustments.get(service_id, self.DEFAULT_THRESHOLD)

    def set_threshold(self, service_id: str, threshold: float) -> None:
        """设置服务的阈值。

        Args:
            service_id: 服务ID
            threshold: 阈值 (0-1)
        """
        self._threshold_adjustments[service_id] = max(0.0, min(1.0, threshold))

    def get_service_stats(self, service_id: str) -> Optional[ServiceStats]:
        """获取服务统计信息。

        Args:
            service_id: 服务ID

        Returns:
            服务统计信息，如果不存在则返回None
        """
        return self._service_stats.get(service_id)

    def get_acceptance_rate(self, service_id: str) -> float:
        """获取服务的接受率。

        Args:
            service_id: 服务ID

        Returns:
            接受率 (0-1)，如果没有记录则返回0.5
        """
        stats = self._service_stats.get(service_id)
        if stats is None:
            return 0.5
        return stats.acceptance_rate

    def get_feedback_history(
        self,
        service_id: Optional[str] = None,
        feedback_type: Optional[FeedbackType] = None,
        limit: int = 100,
    ) -> List[ServiceFeedback]:
        """获取反馈历史。

        Args:
            service_id: 服务ID过滤（可选）
            feedback_type: 反馈类型过滤（可选）
            limit: 返回数量限制

        Returns:
            反馈历史列表
        """
        result = self._feedback_history

        # 按服务ID过滤
        if service_id is not None:
            result = [f for f in result if f.service_id == service_id]

        # 按反馈类型过滤
        if feedback_type is not None:
            result = [f for f in result if f.feedback_type == feedback_type]

        # 返回最近的记录
        return result[-limit:]

    def clear_history(self) -> None:
        """清除反馈历史。"""
        self._feedback_history = []
        self._service_stats = {}
        self._consecutive_rejections = {}
        self._disabled_services = set()

    def is_service_disabled(self, service_id: str) -> bool:
        """检查服务是否被禁用。

        Args:
            service_id: 服务ID

        Returns:
            是否被禁用
        """
        return service_id in self._disabled_services

    def enable_service(self, service_id: str) -> None:
        """启用服务。

        Args:
            service_id: 服务ID
        """
        self._disabled_services.discard(service_id)
        self._consecutive_rejections[service_id] = 0

    def disable_service(self, service_id: str) -> None:
        """禁用服务。

        Args:
            service_id: 服务ID
        """
        self._disabled_services.add(service_id)

    def get_all_stats(self) -> Dict[str, ServiceStats]:
        """获取所有服务的统计信息。

        Returns:
            服务ID到统计信息的映射
        """
        return self._service_stats.copy()

    def get_disabled_services(self) -> List[str]:
        """获取所有被禁用的服务。

        Returns:
            被禁用的服务ID列表
        """
        return list(self._disabled_services)

    def apply_learning_result(self, result: LearningResult) -> int:
        """应用学习结果。

        Args:
            result: 学习结果

        Returns:
            应用的调整数量
        """
        count = 0
        for service_id, adjustment in result.adjustments.items():
            self.adjust_threshold(service_id, adjustment)
            count += 1
        return count

    def get_feedback_count(self) -> int:
        """获取反馈总数。

        Returns:
            反馈总数
        """
        return len(self._feedback_history)

    def get_service_count(self) -> int:
        """获取有统计的服务数量。

        Returns:
            服务数量
        """
        return len(self._service_stats)

    def export_stats(self) -> Dict[str, Any]:
        """导出统计数据。

        Returns:
            统计数据字典
        """
        return {
            "feedback_count": len(self._feedback_history),
            "service_count": len(self._service_stats),
            "disabled_services": list(self._disabled_services),
            "thresholds": self._threshold_adjustments.copy(),
            "services": {
                sid: {
                    "total_triggers": stats.total_triggers,
                    "accepted_count": stats.accepted_count,
                    "rejected_count": stats.rejected_count,
                    "ignored_count": stats.ignored_count,
                    "deferred_count": stats.deferred_count,
                    "modified_count": stats.modified_count,
                    "acceptance_rate": stats.acceptance_rate,
                    "rejection_rate": stats.rejection_rate,
                    "ignore_rate": stats.ignore_rate,
                }
                for sid, stats in self._service_stats.items()
            },
        }

    def import_stats(self, data: Dict[str, Any]) -> None:
        """导入统计数据。

        Args:
            data: 统计数据字典
        """
        self._disabled_services = set(data.get("disabled_services", []))
        self._threshold_adjustments = data.get("thresholds", {}).copy()

        # 重建服务统计
        services_data = data.get("services", {})
        for sid, stats_data in services_data.items():
            stats = ServiceStats(
                service_id=sid,
                total_triggers=stats_data.get("total_triggers", 0),
                accepted_count=stats_data.get("accepted_count", 0),
                rejected_count=stats_data.get("rejected_count", 0),
                ignored_count=stats_data.get("ignored_count", 0),
                deferred_count=stats_data.get("deferred_count", 0),
                modified_count=stats_data.get("modified_count", 0),
            )
            self._service_stats[sid] = stats
