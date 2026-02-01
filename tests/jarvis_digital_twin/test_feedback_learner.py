"""FeedbackLearner测试模块

测试反馈学习器的各项功能。
"""

import pytest

from jarvis.jarvis_digital_twin.proactive_service import FeedbackType
from jarvis.jarvis_digital_twin.proactive_service.feedback_learner import (
    FeedbackLearner,
    LearningResult,
    ServiceStats,
)


# ============== Fixtures ==============


@pytest.fixture
def learner() -> FeedbackLearner:
    """创建默认反馈学习器"""
    return FeedbackLearner()


@pytest.fixture
def learner_with_data() -> FeedbackLearner:
    """创建带有测试数据的反馈学习器"""
    learner = FeedbackLearner()
    # 添加一些测试反馈
    for i in range(5):
        learner.record_feedback("service_001", FeedbackType.ACCEPTED)
    for i in range(3):
        learner.record_feedback("service_001", FeedbackType.REJECTED)
    for i in range(2):
        learner.record_feedback("service_001", FeedbackType.IGNORED)
    return learner


# ============== ServiceStats Tests ==============


class TestServiceStats:
    """ServiceStats数据类测试"""

    def test_create_service_stats(self) -> None:
        """测试创建服务统计"""
        stats = ServiceStats(service_id="test_001")
        assert stats.service_id == "test_001"
        assert stats.total_triggers == 0
        assert stats.accepted_count == 0
        assert stats.rejected_count == 0

    def test_acceptance_rate_no_triggers(self) -> None:
        """测试无触发时的接受率"""
        stats = ServiceStats(service_id="test_001")
        assert stats.acceptance_rate == 0.5  # 默认值

    def test_acceptance_rate_with_data(self) -> None:
        """测试有数据时的接受率"""
        stats = ServiceStats(
            service_id="test_001",
            total_triggers=10,
            accepted_count=7,
            modified_count=1,
        )
        assert stats.acceptance_rate == 0.8  # (7+1)/10

    def test_rejection_rate(self) -> None:
        """测试拒绝率计算"""
        stats = ServiceStats(
            service_id="test_001",
            total_triggers=10,
            rejected_count=3,
        )
        assert stats.rejection_rate == 0.3

    def test_ignore_rate(self) -> None:
        """测试忽略率计算"""
        stats = ServiceStats(
            service_id="test_001",
            total_triggers=10,
            ignored_count=2,
        )
        assert stats.ignore_rate == 0.2


# ============== LearningResult Tests ==============


class TestLearningResult:
    """LearningResult数据类测试"""

    def test_create_learning_result(self) -> None:
        """测试创建学习结果"""
        result = LearningResult()
        assert result.adjustments == {}
        assert result.insights == []
        assert result.confidence == 0.5

    def test_learning_result_with_data(self) -> None:
        """测试带数据的学习结果"""
        result = LearningResult(
            adjustments={"service_001": 0.1},
            insights=["测试洞察"],
            confidence=0.8,
        )
        assert result.adjustments["service_001"] == 0.1
        assert len(result.insights) == 1
        assert result.confidence == 0.8


# ============== FeedbackLearner Basic Tests ==============


class TestFeedbackLearnerBasic:
    """FeedbackLearner基础功能测试"""

    def test_create_learner(self, learner: FeedbackLearner) -> None:
        """测试创建学习器"""
        assert learner is not None
        assert learner.get_feedback_count() == 0
        assert learner.get_service_count() == 0

    def test_record_feedback_accepted(self, learner: FeedbackLearner) -> None:
        """测试记录接受反馈"""
        feedback = learner.record_feedback("service_001", FeedbackType.ACCEPTED)
        assert feedback.service_id == "service_001"
        assert feedback.feedback_type == FeedbackType.ACCEPTED
        assert learner.get_feedback_count() == 1

    def test_record_feedback_rejected(self, learner: FeedbackLearner) -> None:
        """测试记录拒绝反馈"""
        feedback = learner.record_feedback("service_001", FeedbackType.REJECTED)
        assert feedback.feedback_type == FeedbackType.REJECTED

    def test_record_feedback_ignored(self, learner: FeedbackLearner) -> None:
        """测试记录忽略反馈"""
        feedback = learner.record_feedback("service_001", FeedbackType.IGNORED)
        assert feedback.feedback_type == FeedbackType.IGNORED

    def test_record_feedback_deferred(self, learner: FeedbackLearner) -> None:
        """测试记录延迟反馈"""
        feedback = learner.record_feedback("service_001", FeedbackType.DEFERRED)
        assert feedback.feedback_type == FeedbackType.DEFERRED

    def test_record_feedback_modified(self, learner: FeedbackLearner) -> None:
        """测试记录修改后接受反馈"""
        feedback = learner.record_feedback("service_001", FeedbackType.MODIFIED)
        assert feedback.feedback_type == FeedbackType.MODIFIED

    def test_record_feedback_with_comment(self, learner: FeedbackLearner) -> None:
        """测试记录带评论的反馈"""
        feedback = learner.record_feedback(
            "service_001",
            FeedbackType.REJECTED,
            user_comment="不需要这个建议",
        )
        assert feedback.user_comment == "不需要这个建议"


# ============== FeedbackLearner Stats Tests ==============


class TestFeedbackLearnerStats:
    """FeedbackLearner统计功能测试"""

    def test_get_service_stats(self, learner_with_data: FeedbackLearner) -> None:
        """测试获取服务统计"""
        stats = learner_with_data.get_service_stats("service_001")
        assert stats is not None
        assert stats.total_triggers == 10
        assert stats.accepted_count == 5
        assert stats.rejected_count == 3
        assert stats.ignored_count == 2

    def test_get_service_stats_not_found(self, learner: FeedbackLearner) -> None:
        """测试获取不存在的服务统计"""
        stats = learner.get_service_stats("nonexistent")
        assert stats is None

    def test_get_acceptance_rate(self, learner_with_data: FeedbackLearner) -> None:
        """测试获取接受率"""
        rate = learner_with_data.get_acceptance_rate("service_001")
        assert rate == 0.5  # 5/10

    def test_get_acceptance_rate_not_found(self, learner: FeedbackLearner) -> None:
        """测试获取不存在服务的接受率"""
        rate = learner.get_acceptance_rate("nonexistent")
        assert rate == 0.5  # 默认值

    def test_get_all_stats(self, learner: FeedbackLearner) -> None:
        """测试获取所有统计"""
        learner.record_feedback("service_001", FeedbackType.ACCEPTED)
        learner.record_feedback("service_002", FeedbackType.REJECTED)
        all_stats = learner.get_all_stats()
        assert len(all_stats) == 2
        assert "service_001" in all_stats
        assert "service_002" in all_stats


# ============== FeedbackLearner Threshold Tests ==============


class TestFeedbackLearnerThreshold:
    """FeedbackLearner阈值功能测试"""

    def test_get_default_threshold(self, learner: FeedbackLearner) -> None:
        """测试获取默认阈值"""
        threshold = learner.get_threshold("service_001")
        assert threshold == 0.5

    def test_set_threshold(self, learner: FeedbackLearner) -> None:
        """测试设置阈值"""
        learner.set_threshold("service_001", 0.7)
        assert learner.get_threshold("service_001") == 0.7

    def test_set_threshold_clamp_max(self, learner: FeedbackLearner) -> None:
        """测试阈值上限"""
        learner.set_threshold("service_001", 1.5)
        assert learner.get_threshold("service_001") == 1.0

    def test_set_threshold_clamp_min(self, learner: FeedbackLearner) -> None:
        """测试阈值下限"""
        learner.set_threshold("service_001", -0.5)
        assert learner.get_threshold("service_001") == 0.0

    def test_adjust_threshold_increase(self, learner: FeedbackLearner) -> None:
        """测试提高阈值"""
        new_threshold = learner.adjust_threshold("service_001", 0.1)
        assert new_threshold == 0.6

    def test_adjust_threshold_decrease(self, learner: FeedbackLearner) -> None:
        """测试降低阈值"""
        new_threshold = learner.adjust_threshold("service_001", -0.1)
        assert new_threshold == 0.4


# ============== FeedbackLearner Learning Tests ==============


class TestFeedbackLearnerLearning:
    """FeedbackLearner学习功能测试"""

    def test_learn_empty(self, learner: FeedbackLearner) -> None:
        """测试空数据学习"""
        result = learner.learn()
        assert result.adjustments == {}
        assert result.insights == []

    def test_learn_low_acceptance(self, learner: FeedbackLearner) -> None:
        """测试低接受率学习"""
        # 创建低接受率数据
        for _ in range(8):
            learner.record_feedback("service_001", FeedbackType.REJECTED)
        for _ in range(2):
            learner.record_feedback("service_001", FeedbackType.ACCEPTED)

        result = learner.learn()
        assert "service_001" in result.adjustments
        assert result.adjustments["service_001"] > 0  # 应该提高阈值

    def test_learn_high_acceptance(self, learner: FeedbackLearner) -> None:
        """测试高接受率学习"""
        # 创建高接受率数据
        for _ in range(9):
            learner.record_feedback("service_001", FeedbackType.ACCEPTED)
        for _ in range(1):
            learner.record_feedback("service_001", FeedbackType.REJECTED)

        result = learner.learn()
        assert "service_001" in result.adjustments
        assert result.adjustments["service_001"] < 0  # 应该降低阈值

    def test_learn_confidence_low_samples(self, learner: FeedbackLearner) -> None:
        """测试低样本量置信度"""
        for _ in range(5):
            learner.record_feedback("service_001", FeedbackType.ACCEPTED)
        result = learner.learn()
        assert result.confidence <= 0.5

    def test_learn_confidence_high_samples(self, learner: FeedbackLearner) -> None:
        """测试高样本量置信度"""
        for _ in range(100):
            learner.record_feedback("service_001", FeedbackType.ACCEPTED)
        result = learner.learn()
        assert result.confidence >= 0.9

    def test_apply_learning_result(self, learner: FeedbackLearner) -> None:
        """测试应用学习结果"""
        result = LearningResult(adjustments={"service_001": 0.1, "service_002": -0.05})
        count = learner.apply_learning_result(result)
        assert count == 2
        assert learner.get_threshold("service_001") == 0.6
        assert learner.get_threshold("service_002") == 0.45


# ============== FeedbackLearner Disable Tests ==============


class TestFeedbackLearnerDisable:
    """FeedbackLearner禁用功能测试"""

    def test_consecutive_rejection_disable(self, learner: FeedbackLearner) -> None:
        """测试连续拒绝禁用服务"""
        for _ in range(3):
            learner.record_feedback("service_001", FeedbackType.REJECTED)
        assert learner.is_service_disabled("service_001")

    def test_acceptance_resets_rejection_count(self, learner: FeedbackLearner) -> None:
        """测试接受重置拒绝计数"""
        learner.record_feedback("service_001", FeedbackType.REJECTED)
        learner.record_feedback("service_001", FeedbackType.REJECTED)
        learner.record_feedback("service_001", FeedbackType.ACCEPTED)
        learner.record_feedback("service_001", FeedbackType.REJECTED)
        learner.record_feedback("service_001", FeedbackType.REJECTED)
        assert not learner.is_service_disabled("service_001")

    def test_acceptance_enables_disabled_service(
        self, learner: FeedbackLearner
    ) -> None:
        """测试接受重新启用服务"""
        for _ in range(3):
            learner.record_feedback("service_001", FeedbackType.REJECTED)
        assert learner.is_service_disabled("service_001")
        learner.record_feedback("service_001", FeedbackType.ACCEPTED)
        assert not learner.is_service_disabled("service_001")

    def test_manual_enable_service(self, learner: FeedbackLearner) -> None:
        """测试手动启用服务"""
        learner.disable_service("service_001")
        assert learner.is_service_disabled("service_001")
        learner.enable_service("service_001")
        assert not learner.is_service_disabled("service_001")

    def test_manual_disable_service(self, learner: FeedbackLearner) -> None:
        """测试手动禁用服务"""
        learner.disable_service("service_001")
        assert learner.is_service_disabled("service_001")

    def test_get_disabled_services(self, learner: FeedbackLearner) -> None:
        """测试获取禁用服务列表"""
        learner.disable_service("service_001")
        learner.disable_service("service_002")
        disabled = learner.get_disabled_services()
        assert len(disabled) == 2
        assert "service_001" in disabled
        assert "service_002" in disabled


# ============== FeedbackLearner History Tests ==============


class TestFeedbackLearnerHistory:
    """FeedbackLearner历史功能测试"""

    def test_get_feedback_history(self, learner_with_data: FeedbackLearner) -> None:
        """测试获取反馈历史"""
        history = learner_with_data.get_feedback_history()
        assert len(history) == 10

    def test_get_feedback_history_by_service(self, learner: FeedbackLearner) -> None:
        """测试按服务过滤历史"""
        learner.record_feedback("service_001", FeedbackType.ACCEPTED)
        learner.record_feedback("service_002", FeedbackType.REJECTED)
        history = learner.get_feedback_history(service_id="service_001")
        assert len(history) == 1
        assert history[0].service_id == "service_001"

    def test_get_feedback_history_by_type(self, learner: FeedbackLearner) -> None:
        """测试按类型过滤历史"""
        learner.record_feedback("service_001", FeedbackType.ACCEPTED)
        learner.record_feedback("service_001", FeedbackType.REJECTED)
        history = learner.get_feedback_history(feedback_type=FeedbackType.ACCEPTED)
        assert len(history) == 1
        assert history[0].feedback_type == FeedbackType.ACCEPTED

    def test_get_feedback_history_limit(self, learner: FeedbackLearner) -> None:
        """测试历史数量限制"""
        for _ in range(10):
            learner.record_feedback("service_001", FeedbackType.ACCEPTED)
        history = learner.get_feedback_history(limit=5)
        assert len(history) == 5

    def test_clear_history(self, learner_with_data: FeedbackLearner) -> None:
        """测试清除历史"""
        learner_with_data.clear_history()
        assert learner_with_data.get_feedback_count() == 0
        assert learner_with_data.get_service_count() == 0


# ============== FeedbackLearner Export/Import Tests ==============


class TestFeedbackLearnerExportImport:
    """FeedbackLearner导出导入功能测试"""

    def test_export_stats(self, learner_with_data: FeedbackLearner) -> None:
        """测试导出统计"""
        data = learner_with_data.export_stats()
        assert "feedback_count" in data
        assert "service_count" in data
        assert "services" in data
        assert data["feedback_count"] == 10

    def test_import_stats(self, learner: FeedbackLearner) -> None:
        """测试导入统计"""
        data = {
            "disabled_services": ["service_001"],
            "thresholds": {"service_001": 0.7},
            "services": {
                "service_001": {
                    "total_triggers": 10,
                    "accepted_count": 5,
                    "rejected_count": 3,
                    "ignored_count": 2,
                    "deferred_count": 0,
                    "modified_count": 0,
                }
            },
        }
        learner.import_stats(data)
        assert learner.is_service_disabled("service_001")
        assert learner.get_threshold("service_001") == 0.7
        stats = learner.get_service_stats("service_001")
        assert stats is not None
        assert stats.total_triggers == 10


# ============== FeedbackLearner Integration Tests ==============


class TestFeedbackLearnerIntegration:
    """FeedbackLearner集成测试"""

    def test_full_workflow(self, learner: FeedbackLearner) -> None:
        """测试完整工作流"""
        # 1. 记录反馈
        for _ in range(8):
            learner.record_feedback("service_001", FeedbackType.REJECTED)
        for _ in range(2):
            learner.record_feedback("service_001", FeedbackType.ACCEPTED)

        # 2. 学习
        result = learner.learn()
        assert "service_001" in result.adjustments

        # 3. 应用学习结果
        learner.apply_learning_result(result)

        # 4. 验证阈值已调整
        threshold = learner.get_threshold("service_001")
        assert threshold > 0.5  # 应该提高了阈值

    def test_multiple_services(self, learner: FeedbackLearner) -> None:
        """测试多服务场景"""
        # 服务1：高接受率
        for _ in range(9):
            learner.record_feedback("service_001", FeedbackType.ACCEPTED)
        learner.record_feedback("service_001", FeedbackType.REJECTED)

        # 服务2：低接受率
        for _ in range(8):
            learner.record_feedback("service_002", FeedbackType.REJECTED)
        for _ in range(2):
            learner.record_feedback("service_002", FeedbackType.ACCEPTED)

        result = learner.learn()
        assert result.adjustments.get("service_001", 0) < 0  # 降低阈值
        assert result.adjustments.get("service_002", 0) > 0  # 提高阈值
