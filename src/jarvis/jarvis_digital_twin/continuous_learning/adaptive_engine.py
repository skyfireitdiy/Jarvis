"""自适应引擎模块。

    负责根据反馈调整行为，支持多维度自适应。
与FeedbackLearner集成，实现智能行为调整。
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol


class AdaptationType(Enum):
    """适应类型枚举。

    定义可调整的适应类型。
    """

    THRESHOLD = "threshold"  # 阈值调整
    STRATEGY = "strategy"  # 策略调整
    BEHAVIOR = "behavior"  # 行为调整
    PREFERENCE = "preference"  # 偏好调整


@dataclass
class AdaptationResult:
    """适应结果数据类。

    记录一次适应操作的结果。
    """

    # 适应唯一标识
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # 是否成功
    success: bool = True
    # 适应类型
    adaptation_type: AdaptationType = AdaptationType.THRESHOLD
    # 旧值
    old_value: Any = None
    # 新值
    new_value: Any = None
    # 调整原因
    reason: str = ""
    # 时间戳
    timestamp: datetime = field(default_factory=datetime.now)
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AdaptationRecord:
    """适应记录数据类。

    用于内部存储适应历史。
    """

    result: AdaptationResult
    context: str = ""
    rollback_value: Any = None
    is_rolled_back: bool = False


class AdapterProtocol(Protocol):
    """适配器协议。

    定义适配器的标准接口。
    """

    def adapt(self, current_value: Any, feedback: Dict[str, Any]) -> Any:
        """执行适应。

        Args:
            current_value: 当前值
            feedback: 反馈信息

        Returns:
            调整后的值
        """
        ...


class ThresholdAdapter:
    """阈值适配器。

    调整触发阈值。
    """

    # 调整步长
    INCREASE_STEP = 0.1
    DECREASE_STEP = 0.05
    MIN_THRESHOLD = 0.1
    MAX_THRESHOLD = 0.9

    def __init__(
        self,
        increase_step: float = 0.1,
        decrease_step: float = 0.05,
        min_threshold: float = 0.1,
        max_threshold: float = 0.9,
    ) -> None:
        """初始化阈值适配器。

        Args:
            increase_step: 增加步长
            decrease_step: 减少步长
            min_threshold: 最小阈值
            max_threshold: 最大阈值
        """
        self._increase_step = increase_step
        self._decrease_step = decrease_step
        self._min_threshold = min_threshold
        self._max_threshold = max_threshold

    def adapt(self, current_value: float, feedback: Dict[str, Any]) -> float:
        """根据反馈调整阈值。

        Args:
            current_value: 当前阈值
            feedback: 反馈信息，包含 acceptance_rate, rejection_rate 等

        Returns:
            调整后的阈值
        """

        acceptance_rate = feedback.get("acceptance_rate", 0.5)
        rejection_rate = feedback.get("rejection_rate", 0.0)

        new_value = current_value

        # 接受率低，提高阈值（减少触发）
        if acceptance_rate < 0.3:
            new_value = current_value + self._increase_step
        # 接受率高，降低阈值（增加触发）
        elif acceptance_rate > 0.8:
            new_value = current_value - self._decrease_step
        # 拒绝率高，提高阈值
        elif rejection_rate > 0.5:
            new_value = current_value + self._increase_step * 0.5

        # 限制范围
        return max(self._min_threshold, min(self._max_threshold, new_value))


class StrategyAdapter:
    """策略适配器。

    调整执行策略。
    """

    # 策略优先级
    STRATEGY_PRIORITY = {
        "aggressive": 3,
        "balanced": 2,
        "conservative": 1,
    }

    def __init__(self) -> None:
        """初始化策略适配器。"""
        self._strategy_history: List[str] = []

    def adapt(self, current_value: str, feedback: Dict[str, Any]) -> str:
        """根据反馈调整策略。

        Args:
            current_value: 当前策略
            feedback: 反馈信息

        Returns:
            调整后的策略
        """

        success_rate = feedback.get("success_rate", 0.5)
        error_count = feedback.get("error_count", 0)

        # 记录历史
        self._strategy_history.append(current_value)

        # 成功率低或错误多，转为保守策略
        if success_rate < 0.3 or error_count > 5:
            return "conservative"
        # 成功率高，可以更激进
        elif success_rate > 0.8 and error_count == 0:
            return "aggressive"
        # 默认平衡策略
        return "balanced"

    def get_strategy_history(self) -> List[str]:
        """获取策略历史。"""
        return self._strategy_history.copy()


class BehaviorAdapter:
    """行为适配器。

    调整行为模式。
    """

    def __init__(self) -> None:
        """初始化行为适配器。"""
        self._behavior_weights: Dict[str, float] = {}

    def adapt(
        self, current_value: Dict[str, Any], feedback: Dict[str, Any]
    ) -> Dict[str, Any]:
        """根据反馈调整行为。

        Args:
            current_value: 当前行为配置
            feedback: 反馈信息

        Returns:
            调整后的行为配置
        """

        new_value = current_value.copy()

        # 根据反馈调整行为权重
        positive_feedback = feedback.get("positive", 0)
        negative_feedback = feedback.get("negative", 0)

        # 调整启用状态
        if "enabled" in new_value:
            if negative_feedback > 3:
                new_value["enabled"] = False
            elif positive_feedback > 5:
                new_value["enabled"] = True

        # 调整频率
        if "frequency" in new_value:
            if negative_feedback > positive_feedback:
                new_value["frequency"] = max(1, new_value["frequency"] - 1)
            elif positive_feedback > negative_feedback * 2:
                new_value["frequency"] = min(10, new_value["frequency"] + 1)

        # 调整优先级
        if "priority" in new_value:
            if positive_feedback > 5:
                new_value["priority"] = min(10, new_value["priority"] + 1)
            elif negative_feedback > 3:
                new_value["priority"] = max(1, new_value["priority"] - 1)

        return new_value

    def set_behavior_weight(self, behavior: str, weight: float) -> None:
        """设置行为权重。"""
        self._behavior_weights[behavior] = max(0.0, min(1.0, weight))

    def get_behavior_weight(self, behavior: str) -> float:
        """获取行为权重。"""
        return self._behavior_weights.get(behavior, 0.5)


class AdaptiveEngine:
    """自适应引擎。

    负责根据反馈调整行为，支持多维度自适应。
    """

    def __init__(
        self,
        feedback_learner: Optional[Any] = None,
        user_profile: Optional[Any] = None,
        llm_client: Optional[Any] = None,
    ) -> None:
        """初始化自适应引擎。

        Args:
            feedback_learner: 反馈学习器（来自阶段5.3）
            user_profile: 用户画像（来自阶段5.1）
            llm_client: LLM客户端（可选）
        """
        self._llm_client = llm_client
        self._feedback_learner = feedback_learner
        self._user_profile = user_profile

        # 适应历史
        self._adaptation_history: List[AdaptationRecord] = []

        # 当前设置
        self._current_settings: Dict[str, Any] = {
            "thresholds": {},
            "strategies": {},
            "behaviors": {},
            "preferences": {},
        }

        # 内置适配器
        self._threshold_adapter = ThresholdAdapter()
        self._strategy_adapter = StrategyAdapter()
        self._behavior_adapter = BehaviorAdapter()

        # 自定义适配器
        self._custom_adapters: Dict[AdaptationType, AdapterProtocol] = {}

        # 统计信息
        self._stats = {
            "total_adaptations": 0,
            "successful_adaptations": 0,
            "failed_adaptations": 0,
            "rollbacks": 0,
        }

    def adapt_to_feedback(
        self,
        feedback_type: str,
        feedback_value: float,
        context: str = "",
    ) -> AdaptationResult:
        """根据反馈调整。

        Args:
            feedback_type: 反馈类型（如 acceptance_rate, rejection_rate）
            feedback_value: 反馈值
            context: 上下文信息

        Returns:
            适应结果
        """
        result = AdaptationResult(
            adaptation_type=AdaptationType.THRESHOLD,
            reason=f"根据{feedback_type}反馈调整",
        )

        try:
            # 构建反馈字典
            feedback = {feedback_type: feedback_value}

            # 获取当前阈值
            threshold_key = f"{context}_threshold" if context else "default_threshold"
            current_threshold = self._current_settings["thresholds"].get(
                threshold_key, 0.5
            )

            # 使用阈值适配器调整
            new_threshold = self._threshold_adapter.adapt(current_threshold, feedback)

            # 记录结果
            result.old_value = current_threshold
            result.new_value = new_threshold
            result.success = True

            # 更新设置
            self._current_settings["thresholds"][threshold_key] = new_threshold

            # 记录历史
            self._record_adaptation(result, context, current_threshold)

            # 更新统计
            self._stats["total_adaptations"] += 1
            self._stats["successful_adaptations"] += 1

        except Exception as e:
            result.success = False
            result.reason = f"适应失败: {str(e)}"
            self._stats["total_adaptations"] += 1
            self._stats["failed_adaptations"] += 1

        return result

    def adapt_to_context(
        self,
        context: str,
        current_behavior: Dict[str, Any],
    ) -> AdaptationResult:
        """根据上下文调整。

        Args:
            context: 上下文信息
            current_behavior: 当前行为配置

        Returns:
            适应结果
        """
        result = AdaptationResult(
            adaptation_type=AdaptationType.BEHAVIOR,
            reason=f"根据上下文'{context}'调整行为",
        )

        try:
            # 分析上下文
            feedback = self._analyze_context(context)

            # 使用行为适配器调整
            new_behavior = self._behavior_adapter.adapt(current_behavior, feedback)

            # 记录结果
            result.old_value = current_behavior
            result.new_value = new_behavior
            result.success = True

            # 更新设置
            behavior_key = f"behavior_{context}" if context else "default_behavior"
            self._current_settings["behaviors"][behavior_key] = new_behavior

            # 记录历史
            self._record_adaptation(result, context, current_behavior)

            # 更新统计
            self._stats["total_adaptations"] += 1
            self._stats["successful_adaptations"] += 1

        except Exception as e:
            result.success = False
            result.reason = f"适应失败: {str(e)}"
            self._stats["total_adaptations"] += 1
            self._stats["failed_adaptations"] += 1

        return result

    def optimize_performance(
        self,
        metrics: Dict[str, Any],
    ) -> List[AdaptationResult]:
        """优化性能。

        Args:
            metrics: 性能指标

        Returns:
            适应结果列表
        """
        results: List[AdaptationResult] = []

        # 优化阈值
        if "acceptance_rate" in metrics or "rejection_rate" in metrics:
            threshold_result = self._optimize_thresholds(metrics)
            results.append(threshold_result)

        # 优化策略
        if "success_rate" in metrics or "error_count" in metrics:
            strategy_result = self._optimize_strategy(metrics)
            results.append(strategy_result)

        # 优化行为
        if "positive" in metrics or "negative" in metrics:
            behavior_result = self._optimize_behavior(metrics)
            results.append(behavior_result)

        return results

    def _optimize_thresholds(self, metrics: Dict[str, Any]) -> AdaptationResult:
        """优化阈值。"""
        result = AdaptationResult(
            adaptation_type=AdaptationType.THRESHOLD,
            reason="性能优化：调整阈值",
        )

        try:
            current_thresholds = self._current_settings["thresholds"].copy()
            new_thresholds = {}

            for key, value in current_thresholds.items():
                new_value = self._threshold_adapter.adapt(value, metrics)
                new_thresholds[key] = new_value

            result.old_value = current_thresholds
            result.new_value = new_thresholds
            result.success = True

            self._current_settings["thresholds"] = new_thresholds
            self._record_adaptation(
                result, "performance_optimization", current_thresholds
            )

            self._stats["total_adaptations"] += 1
            self._stats["successful_adaptations"] += 1

        except Exception as e:
            result.success = False
            result.reason = f"阈值优化失败: {str(e)}"
            self._stats["total_adaptations"] += 1
            self._stats["failed_adaptations"] += 1

        return result

    def _optimize_strategy(self, metrics: Dict[str, Any]) -> AdaptationResult:
        """优化策略。"""
        result = AdaptationResult(
            adaptation_type=AdaptationType.STRATEGY,
            reason="性能优化：调整策略",
        )

        try:
            current_strategy = self._current_settings["strategies"].get(
                "default", "balanced"
            )
            new_strategy = self._strategy_adapter.adapt(current_strategy, metrics)

            result.old_value = current_strategy
            result.new_value = new_strategy
            result.success = True

            self._current_settings["strategies"]["default"] = new_strategy
            self._record_adaptation(result, "strategy_optimization", current_strategy)

            self._stats["total_adaptations"] += 1
            self._stats["successful_adaptations"] += 1

        except Exception as e:
            result.success = False
            result.reason = f"策略优化失败: {str(e)}"
            self._stats["total_adaptations"] += 1
            self._stats["failed_adaptations"] += 1

        return result

    def _optimize_behavior(self, metrics: Dict[str, Any]) -> AdaptationResult:
        """优化行为。"""
        result = AdaptationResult(
            adaptation_type=AdaptationType.BEHAVIOR,
            reason="性能优化：调整行为",
        )

        try:
            current_behaviors = self._current_settings["behaviors"].copy()
            new_behaviors = {}

            for key, value in current_behaviors.items():
                if isinstance(value, dict):
                    new_value = self._behavior_adapter.adapt(value, metrics)
                    new_behaviors[key] = new_value
                else:
                    new_behaviors[key] = value

            result.old_value = current_behaviors
            result.new_value = new_behaviors
            result.success = True

            self._current_settings["behaviors"] = new_behaviors
            self._record_adaptation(result, "behavior_optimization", current_behaviors)

            self._stats["total_adaptations"] += 1
            self._stats["successful_adaptations"] += 1

        except Exception as e:
            result.success = False
            result.reason = f"行为优化失败: {str(e)}"
            self._stats["total_adaptations"] += 1
            self._stats["failed_adaptations"] += 1

        return result

    def get_adaptation_history(self, limit: int = 10) -> List[AdaptationResult]:
        """获取调整历史。

        Args:
            limit: 返回数量限制

        Returns:
            适应结果列表
        """
        results = [record.result for record in self._adaptation_history]
        return results[-limit:]

    def rollback_adaptation(self, adaptation_id: str) -> bool:
        """回滚调整。

        Args:
            adaptation_id: 适应ID

        Returns:
            是否成功回滚
        """
        for record in self._adaptation_history:
            if record.result.id == adaptation_id and not record.is_rolled_back:
                # 执行回滚
                adaptation_type = record.result.adaptation_type
                rollback_value = record.rollback_value

                if adaptation_type == AdaptationType.THRESHOLD:
                    # 回滚阈值
                    for key in self._current_settings["thresholds"]:
                        if isinstance(rollback_value, dict) and key in rollback_value:
                            self._current_settings["thresholds"][key] = rollback_value[
                                key
                            ]
                        elif isinstance(rollback_value, (int, float)):
                            self._current_settings["thresholds"][key] = rollback_value
                elif adaptation_type == AdaptationType.STRATEGY:
                    # 回滚策略
                    if isinstance(rollback_value, str):
                        self._current_settings["strategies"]["default"] = rollback_value
                elif adaptation_type == AdaptationType.BEHAVIOR:
                    # 回滚行为
                    if isinstance(rollback_value, dict):
                        self._current_settings["behaviors"].update(rollback_value)

                record.is_rolled_back = True
                self._stats["rollbacks"] += 1
            return True

        return False

    def get_current_settings(self) -> Dict[str, Any]:
        """获取当前设置。

        Returns:
            当前设置字典
        """
        return {
            "thresholds": self._current_settings["thresholds"].copy(),
            "strategies": self._current_settings["strategies"].copy(),
            "behaviors": self._current_settings["behaviors"].copy(),
            "preferences": self._current_settings["preferences"].copy(),
        }

    def apply_user_preference(
        self,
        preference_key: str,
        preference_value: Any,
    ) -> AdaptationResult:
        """应用用户偏好。

        Args:
            preference_key: 偏好键
            preference_value: 偏好值

        Returns:
            适应结果
        """
        result = AdaptationResult(
            adaptation_type=AdaptationType.PREFERENCE,
            reason=f"应用用户偏好: {preference_key}",
        )

        try:
            old_value = self._current_settings["preferences"].get(preference_key)
            self._current_settings["preferences"][preference_key] = preference_value

            result.old_value = old_value
            result.new_value = preference_value
            result.success = True

            self._record_adaptation(result, f"preference_{preference_key}", old_value)

            self._stats["total_adaptations"] += 1
            self._stats["successful_adaptations"] += 1

        except Exception as e:
            result.success = False
            result.reason = f"应用偏好失败: {str(e)}"
            self._stats["total_adaptations"] += 1
            self._stats["failed_adaptations"] += 1

        return result

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息。

        Returns:
            统计信息字典
        """
        return {
            "total_adaptations": self._stats["total_adaptations"],
            "successful_adaptations": self._stats["successful_adaptations"],
            "failed_adaptations": self._stats["failed_adaptations"],
            "rollbacks": self._stats["rollbacks"],
            "success_rate": (
                self._stats["successful_adaptations"] / self._stats["total_adaptations"]
                if self._stats["total_adaptations"] > 0
                else 0.0
            ),
            "history_count": len(self._adaptation_history),
            "current_thresholds_count": len(self._current_settings["thresholds"]),
            "current_strategies_count": len(self._current_settings["strategies"]),
            "current_behaviors_count": len(self._current_settings["behaviors"]),
            "current_preferences_count": len(self._current_settings["preferences"]),
        }

    def register_adapter(
        self,
        adaptation_type: AdaptationType,
        adapter: AdapterProtocol,
    ) -> None:
        """注册自定义适配器。

        Args:
            adaptation_type: 适应类型
            adapter: 适配器实例
        """
        self._custom_adapters[adaptation_type] = adapter

    def unregister_adapter(self, adaptation_type: AdaptationType) -> bool:
        """取消注册适配器。

        Args:
            adaptation_type: 适应类型

        Returns:
            是否成功取消
        """
        if adaptation_type in self._custom_adapters:
            del self._custom_adapters[adaptation_type]
            return True
        return False

    def set_threshold(self, key: str, value: float) -> None:
        """设置阈值。

        Args:
            key: 阈值键
            value: 阈值
        """
        self._current_settings["thresholds"][key] = max(0.0, min(1.0, value))

    def get_threshold(self, key: str, default: float = 0.5) -> float:
        """获取阈值。

        Args:
            key: 阈值键
            default: 默认值

        Returns:
            阈值
        """
        value = self._current_settings["thresholds"].get(key, default)
        return float(value) if value is not None else default

    def set_strategy(self, key: str, value: str) -> None:
        """设置策略。

        Args:
            key: 策略键
            value: 策略值
        """
        self._current_settings["strategies"][key] = value

    def get_strategy(self, key: str, default: str = "balanced") -> str:
        """获取策略。

        Args:
            key: 策略键
            default: 默认值

        Returns:
            策略
        """
        value = self._current_settings["strategies"].get(key, default)
        return str(value) if value is not None else default

    def clear_history(self) -> None:
        """清除历史记录。"""
        self._adaptation_history.clear()

    def reset_settings(self) -> None:
        """重置所有设置。"""
        self._current_settings = {
            "thresholds": {},
            "strategies": {},
            "behaviors": {},
            "preferences": {},
        }
        self._stats = {
            "total_adaptations": 0,
            "successful_adaptations": 0,
            "failed_adaptations": 0,
            "rollbacks": 0,
        }

    def _record_adaptation(
        self,
        result: AdaptationResult,
        context: str,
        rollback_value: Any,
    ) -> None:
        """记录适应操作。"""
        record = AdaptationRecord(
            result=result,
            context=context,
            rollback_value=rollback_value,
        )
        self._adaptation_history.append(record)

    def _analyze_context(self, context: str) -> Dict[str, Any]:
        """分析上下文。

        Args:
            context: 上下文字符串

        Returns:
            分析结果
        """
        feedback: Dict[str, Any] = {
            "positive": 0,
            "negative": 0,
        }

        context_lower = context.lower()

        # 正面关键词
        positive_keywords = [
            "成功",
            "完成",
            "好",
            "正确",
            "有效",
            "success",
            "complete",
            "good",
            "correct",
            "effective",
        ]
        # 负面关键词
        negative_keywords = [
            "失败",
            "错误",
            "问题",
            "无效",
            "差",
            "fail",
            "error",
            "problem",
            "invalid",
            "bad",
        ]

        for keyword in positive_keywords:
            if keyword in context_lower:
                feedback["positive"] += 1

        for keyword in negative_keywords:
            if keyword in context_lower:
                feedback["negative"] += 1

        return feedback

    def export_state(self) -> Dict[str, Any]:
        """导出状态。

        Returns:
            状态字典
        """
        return {
            "settings": self.get_current_settings(),
            "statistics": self.get_statistics(),
            "history_count": len(self._adaptation_history),
        }

    def import_state(self, state: Dict[str, Any]) -> None:
        """导入状态。

        Args:
            state: 状态字典
        """
        if "settings" in state:
            settings = state["settings"]
            self._current_settings["thresholds"] = settings.get("thresholds", {})
            self._current_settings["strategies"] = settings.get("strategies", {})
            self._current_settings["behaviors"] = settings.get("behaviors", {})
            self._current_settings["preferences"] = settings.get("preferences", {})
