"""自适应引擎测试模块。

测试AdaptiveEngine类及相关适配器的功能。
"""

from datetime import datetime

from jarvis.jarvis_digital_twin.continuous_learning.adaptive_engine import (
    AdaptationType,
    AdaptationResult,
    AdaptiveEngine,
    BehaviorAdapter,
    StrategyAdapter,
    ThresholdAdapter,
)


class TestAdaptationType:
    """AdaptationType枚举测试。"""

    def test_adaptation_type_values(self) -> None:
        """测试适应类型枚举值。"""
        assert AdaptationType.THRESHOLD.value == "threshold"
        assert AdaptationType.STRATEGY.value == "strategy"
        assert AdaptationType.BEHAVIOR.value == "behavior"
        assert AdaptationType.PREFERENCE.value == "preference"

    def test_adaptation_type_count(self) -> None:
        """测试适应类型数量。"""
        assert len(AdaptationType) == 4


class TestAdaptationResult:
    """AdaptationResult数据类测试。"""

    def test_default_values(self) -> None:
        """测试默认值。"""
        result = AdaptationResult()
        assert result.success is True
        assert result.adaptation_type == AdaptationType.THRESHOLD
        assert result.old_value is None
        assert result.new_value is None
        assert result.reason == ""
        assert isinstance(result.timestamp, datetime)
        assert result.metadata == {}

    def test_custom_values(self) -> None:
        """测试自定义值。"""
        result = AdaptationResult(
            success=False,
            adaptation_type=AdaptationType.STRATEGY,
            old_value="conservative",
            new_value="aggressive",
            reason="性能优化",
        )
        assert result.success is False
        assert result.adaptation_type == AdaptationType.STRATEGY
        assert result.old_value == "conservative"
        assert result.new_value == "aggressive"
        assert result.reason == "性能优化"

    def test_id_generation(self) -> None:
        """测试ID自动生成。"""
        result1 = AdaptationResult()
        result2 = AdaptationResult()
        assert result1.id != result2.id


class TestThresholdAdapter:
    """ThresholdAdapter测试。"""

    def test_default_initialization(self) -> None:
        """测试默认初始化。"""
        adapter = ThresholdAdapter()
        assert adapter._increase_step == 0.1
        assert adapter._decrease_step == 0.05
        assert adapter._min_threshold == 0.1
        assert adapter._max_threshold == 0.9

    def test_custom_initialization(self) -> None:
        """测试自定义初始化。"""
        adapter = ThresholdAdapter(
            increase_step=0.2,
            decrease_step=0.1,
            min_threshold=0.2,
            max_threshold=0.8,
        )
        assert adapter._increase_step == 0.2
        assert adapter._decrease_step == 0.1
        assert adapter._min_threshold == 0.2
        assert adapter._max_threshold == 0.8

    def test_adapt_low_acceptance_rate(self) -> None:
        """测试低接受率时提高阈值。"""
        adapter = ThresholdAdapter()
        result = adapter.adapt(0.5, {"acceptance_rate": 0.2})
        assert result > 0.5

    def test_adapt_high_acceptance_rate(self) -> None:
        """测试高接受率时降低阈值。"""
        adapter = ThresholdAdapter()
        result = adapter.adapt(0.5, {"acceptance_rate": 0.9})
        assert result < 0.5

    def test_adapt_high_rejection_rate(self) -> None:
        """测试高拒绝率时提高阈值。"""
        adapter = ThresholdAdapter()
        result = adapter.adapt(0.5, {"rejection_rate": 0.6})
        assert result > 0.5

    def test_adapt_respects_min_threshold(self) -> None:
        """测试不低于最小阈值。"""
        adapter = ThresholdAdapter(min_threshold=0.3)
        result = adapter.adapt(0.3, {"acceptance_rate": 0.95})
        assert result >= 0.3

    def test_adapt_respects_max_threshold(self) -> None:
        """测试不超过最大阈值。"""
        adapter = ThresholdAdapter(max_threshold=0.7)
        result = adapter.adapt(0.7, {"acceptance_rate": 0.1})
        assert result <= 0.7


class TestStrategyAdapter:
    """StrategyAdapter测试。"""

    def test_initialization(self) -> None:
        """测试初始化。"""
        adapter = StrategyAdapter()
        assert adapter._strategy_history == []

    def test_adapt_low_success_rate(self) -> None:
        """测试低成功率时转为保守策略。"""
        adapter = StrategyAdapter()
        result = adapter.adapt("balanced", {"success_rate": 0.2})
        assert result == "conservative"

    def test_adapt_high_error_count(self) -> None:
        """测试高错误数时转为保守策略。"""
        adapter = StrategyAdapter()
        result = adapter.adapt("aggressive", {"error_count": 10})
        assert result == "conservative"

    def test_adapt_high_success_rate(self) -> None:
        """测试高成功率时转为激进策略。"""
        adapter = StrategyAdapter()
        result = adapter.adapt("balanced", {"success_rate": 0.9, "error_count": 0})
        assert result == "aggressive"

    def test_adapt_default_balanced(self) -> None:
        """测试默认返回平衡策略。"""
        adapter = StrategyAdapter()
        result = adapter.adapt("conservative", {"success_rate": 0.5, "error_count": 2})
        assert result == "balanced"

    def test_strategy_history(self) -> None:
        """测试策略历史记录。"""
        adapter = StrategyAdapter()
        adapter.adapt("balanced", {"success_rate": 0.5})
        adapter.adapt("conservative", {"success_rate": 0.9, "error_count": 0})
        history = adapter.get_strategy_history()
        assert len(history) == 2
        assert history[0] == "balanced"
        assert history[1] == "conservative"


class TestBehaviorAdapter:
    """BehaviorAdapter测试。"""

    def test_initialization(self) -> None:
        """测试初始化。"""
        adapter = BehaviorAdapter()
        assert adapter._behavior_weights == {}

    def test_adapt_disable_on_negative_feedback(self) -> None:
        """测试负面反馈过多时禁用。"""
        adapter = BehaviorAdapter()
        result = adapter.adapt(
            {"enabled": True, "frequency": 5},
            {"negative": 5, "positive": 0},
        )
        assert result["enabled"] is False

    def test_adapt_enable_on_positive_feedback(self) -> None:
        """测试正面反馈多时启用。"""
        adapter = BehaviorAdapter()
        result = adapter.adapt(
            {"enabled": False, "frequency": 5},
            {"positive": 10, "negative": 0},
        )
        assert result["enabled"] is True

    def test_adapt_decrease_frequency(self) -> None:
        """测试负面反馈多时降低频率。"""
        adapter = BehaviorAdapter()
        result = adapter.adapt(
            {"frequency": 5},
            {"negative": 3, "positive": 1},
        )
        assert result["frequency"] < 5

    def test_adapt_increase_frequency(self) -> None:
        """测试正面反馈多时增加频率。"""
        adapter = BehaviorAdapter()
        result = adapter.adapt(
            {"frequency": 5},
            {"positive": 10, "negative": 1},
        )
        assert result["frequency"] > 5

    def test_behavior_weight(self) -> None:
        """测试行为权重设置和获取。"""
        adapter = BehaviorAdapter()
        adapter.set_behavior_weight("test", 0.8)
        assert adapter.get_behavior_weight("test") == 0.8
        assert adapter.get_behavior_weight("unknown") == 0.5

    def test_behavior_weight_bounds(self) -> None:
        """测试行为权重边界。"""
        adapter = BehaviorAdapter()
        adapter.set_behavior_weight("low", -0.5)
        adapter.set_behavior_weight("high", 1.5)
        assert adapter.get_behavior_weight("low") == 0.0
        assert adapter.get_behavior_weight("high") == 1.0


class TestAdaptiveEngine:
    """AdaptiveEngine测试。"""

    def test_initialization(self) -> None:
        """测试初始化。"""
        engine = AdaptiveEngine()
        assert engine._feedback_learner is None
        assert engine._user_profile is None
        assert engine._adaptation_history == []

    def test_initialization_with_dependencies(self) -> None:
        """测试带依赖的初始化。"""
        mock_learner = object()
        mock_profile = object()
        engine = AdaptiveEngine(
            feedback_learner=mock_learner,
            user_profile=mock_profile,
        )
        assert engine._feedback_learner is mock_learner
        assert engine._user_profile is mock_profile

    def test_adapt_to_feedback(self) -> None:
        """测试根据反馈调整。"""
        engine = AdaptiveEngine()
        result = engine.adapt_to_feedback("acceptance_rate", 0.2, "test_context")
        assert result.success is True
        assert result.adaptation_type == AdaptationType.THRESHOLD

    def test_adapt_to_feedback_updates_settings(self) -> None:
        """测试反馈调整更新设置。"""
        engine = AdaptiveEngine()
        engine.adapt_to_feedback("acceptance_rate", 0.2, "test")
        settings = engine.get_current_settings()
        assert "test_threshold" in settings["thresholds"]

    def test_adapt_to_context(self) -> None:
        """测试根据上下文调整。"""
        engine = AdaptiveEngine()
        result = engine.adapt_to_context(
            "成功完成任务",
            {"enabled": True, "frequency": 5},
        )
        assert result.success is True
        assert result.adaptation_type == AdaptationType.BEHAVIOR

    def test_adapt_to_context_negative(self) -> None:
        """测试负面上下文调整。"""
        engine = AdaptiveEngine()
        result = engine.adapt_to_context(
            "任务失败，出现错误",
            {"enabled": True, "frequency": 5},
        )
        assert result.success is True

    def test_optimize_performance_thresholds(self) -> None:
        """测试性能优化-阈值。"""
        engine = AdaptiveEngine()
        engine.set_threshold("test", 0.5)
        results = engine.optimize_performance({"acceptance_rate": 0.2})
        assert len(results) >= 1
        assert any(r.adaptation_type == AdaptationType.THRESHOLD for r in results)

    def test_optimize_performance_strategy(self) -> None:
        """测试性能优化-策略。"""
        engine = AdaptiveEngine()
        results = engine.optimize_performance({"success_rate": 0.2, "error_count": 10})
        assert any(r.adaptation_type == AdaptationType.STRATEGY for r in results)

    def test_optimize_performance_behavior(self) -> None:
        """测试性能优化-行为。"""
        engine = AdaptiveEngine()
        engine._current_settings["behaviors"]["test"] = {"enabled": True}
        results = engine.optimize_performance({"positive": 1, "negative": 5})
        assert any(r.adaptation_type == AdaptationType.BEHAVIOR for r in results)

    def test_get_adaptation_history(self) -> None:
        """测试获取调整历史。"""
        engine = AdaptiveEngine()
        engine.adapt_to_feedback("acceptance_rate", 0.5, "test1")
        engine.adapt_to_feedback("rejection_rate", 0.3, "test2")
        history = engine.get_adaptation_history(limit=10)
        assert len(history) == 2

    def test_get_adaptation_history_limit(self) -> None:
        """测试历史记录限制。"""
        engine = AdaptiveEngine()
        for i in range(5):
            engine.adapt_to_feedback("acceptance_rate", 0.5, f"test{i}")
        history = engine.get_adaptation_history(limit=3)
        assert len(history) == 3

    def test_rollback_adaptation(self) -> None:
        """测试回滚调整。"""
        engine = AdaptiveEngine()
        engine.set_threshold("test", 0.5)
        result = engine.adapt_to_feedback("acceptance_rate", 0.2, "test")
        success = engine.rollback_adaptation(result.id)
        assert success is True
        assert engine._stats["rollbacks"] == 1

    def test_rollback_nonexistent(self) -> None:
        """测试回滚不存在的调整。"""
        engine = AdaptiveEngine()
        success = engine.rollback_adaptation("nonexistent_id")
        assert success is False

    def test_get_current_settings(self) -> None:
        """测试获取当前设置。"""
        engine = AdaptiveEngine()
        engine.set_threshold("test", 0.7)
        engine.set_strategy("default", "aggressive")
        settings = engine.get_current_settings()
        assert "thresholds" in settings
        assert "strategies" in settings
        assert "behaviors" in settings
        assert "preferences" in settings

    def test_apply_user_preference(self) -> None:
        """测试应用用户偏好。"""
        engine = AdaptiveEngine()
        result = engine.apply_user_preference("theme", "dark")
        assert result.success is True
        assert result.adaptation_type == AdaptationType.PREFERENCE
        assert result.new_value == "dark"

    def test_get_statistics(self) -> None:
        """测试获取统计信息。"""
        engine = AdaptiveEngine()
        engine.adapt_to_feedback("acceptance_rate", 0.5, "test")
        stats = engine.get_statistics()
        assert stats["total_adaptations"] == 1
        assert stats["successful_adaptations"] == 1
        assert stats["failed_adaptations"] == 0

    def test_set_and_get_threshold(self) -> None:
        """测试设置和获取阈值。"""
        engine = AdaptiveEngine()
        engine.set_threshold("test", 0.7)
        assert engine.get_threshold("test") == 0.7
        assert engine.get_threshold("unknown", 0.3) == 0.3

    def test_threshold_bounds(self) -> None:
        """测试阈值边界。"""
        engine = AdaptiveEngine()
        engine.set_threshold("low", -0.5)
        engine.set_threshold("high", 1.5)
        assert engine.get_threshold("low") == 0.0
        assert engine.get_threshold("high") == 1.0

    def test_set_and_get_strategy(self) -> None:
        """测试设置和获取策略。"""
        engine = AdaptiveEngine()
        engine.set_strategy("default", "aggressive")
        assert engine.get_strategy("default") == "aggressive"
        assert engine.get_strategy("unknown") == "balanced"

    def test_clear_history(self) -> None:
        """测试清除历史。"""
        engine = AdaptiveEngine()
        engine.adapt_to_feedback("acceptance_rate", 0.5, "test")
        engine.clear_history()
        assert len(engine._adaptation_history) == 0

    def test_reset_settings(self) -> None:
        """测试重置设置。"""
        engine = AdaptiveEngine()
        engine.set_threshold("test", 0.7)
        engine.adapt_to_feedback("acceptance_rate", 0.5, "test")
        engine.reset_settings()
        settings = engine.get_current_settings()
        assert settings["thresholds"] == {}
        assert engine._stats["total_adaptations"] == 0

    def test_export_state(self) -> None:
        """测试导出状态。"""
        engine = AdaptiveEngine()
        engine.set_threshold("test", 0.7)
        engine.adapt_to_feedback("acceptance_rate", 0.5, "test")
        state = engine.export_state()
        assert "settings" in state
        assert "statistics" in state
        assert "history_count" in state

    def test_import_state(self) -> None:
        """测试导入状态。"""
        engine = AdaptiveEngine()
        state = {
            "settings": {
                "thresholds": {"test": 0.8},
                "strategies": {"default": "conservative"},
                "behaviors": {},
                "preferences": {"theme": "light"},
            }
        }
        engine.import_state(state)
        assert engine.get_threshold("test") == 0.8
        assert engine.get_strategy("default") == "conservative"

    def test_register_adapter(self) -> None:
        """测试注册自定义适配器。"""
        engine = AdaptiveEngine()

        class CustomAdapter:
            def adapt(self, current_value, feedback):
                return current_value

        adapter = CustomAdapter()
        engine.register_adapter(AdaptationType.THRESHOLD, adapter)
        assert AdaptationType.THRESHOLD in engine._custom_adapters

    def test_unregister_adapter(self) -> None:
        """测试取消注册适配器。"""
        engine = AdaptiveEngine()

        class CustomAdapter:
            def adapt(self, current_value, feedback):
                return current_value

        adapter = CustomAdapter()
        engine.register_adapter(AdaptationType.THRESHOLD, adapter)
        success = engine.unregister_adapter(AdaptationType.THRESHOLD)
        assert success is True
        assert AdaptationType.THRESHOLD not in engine._custom_adapters

    def test_unregister_nonexistent_adapter(self) -> None:
        """测试取消注册不存在的适配器。"""
        engine = AdaptiveEngine()
        success = engine.unregister_adapter(AdaptationType.THRESHOLD)
        assert success is False


class TestAdaptiveEngineIntegration:
    """AdaptiveEngine集成测试。"""

    def test_full_adaptation_cycle(self) -> None:
        """测试完整的适应周期。"""
        engine = AdaptiveEngine()

        # 1. 设置初始阈值
        engine.set_threshold("service_a", 0.5)

        # 2. 模拟低接受率反馈
        result1 = engine.adapt_to_feedback("acceptance_rate", 0.2, "service_a")
        assert result1.success is True

        # 3. 检查阈值已提高
        new_threshold = engine.get_threshold("service_a_threshold")
        assert new_threshold > 0.5

        # 4. 应用用户偏好
        result2 = engine.apply_user_preference("notification", False)
        assert result2.success is True

        # 5. 检查统计
        stats = engine.get_statistics()
        assert stats["total_adaptations"] == 2
        assert stats["successful_adaptations"] == 2

    def test_performance_optimization_cycle(self) -> None:
        """测试性能优化周期。"""
        engine = AdaptiveEngine()

        # 设置初始状态
        engine.set_threshold("default", 0.5)
        engine.set_strategy("default", "balanced")
        engine._current_settings["behaviors"]["main"] = {
            "enabled": True,
            "frequency": 5,
            "priority": 5,
        }

        # 执行优化
        metrics = {
            "acceptance_rate": 0.2,
            "success_rate": 0.3,
            "error_count": 8,
            "positive": 2,
            "negative": 10,
        }
        results = engine.optimize_performance(metrics)

        # 验证结果
        assert len(results) == 3
        assert all(r.success for r in results)

        # 检查策略已变为保守
        assert engine.get_strategy("default") == "conservative"
