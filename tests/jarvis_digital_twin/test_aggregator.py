"""UserProfileAggregator测试模块

测试用户画像聚合器的功能。
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from jarvis.jarvis_digital_twin.user_profile.aggregator import (
    DigitalTwinProfile,
    ProfileMetadata,
    ProfileSummary,
    UserProfileAggregator,
)
from jarvis.jarvis_digital_twin.user_profile.goal_tracker import (
    GoalStatus,
    GoalType,
    TrackedGoal,
)
from jarvis.jarvis_digital_twin.user_profile.history_analyzer import (
    InteractionPattern,
)
from jarvis.jarvis_digital_twin.user_profile.preference_learner import (
    InteractionData,
    UserPreference,
)


class TestProfileMetadata:
    """ProfileMetadata数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        metadata = ProfileMetadata()
        assert metadata.version == 1
        assert metadata.data_sources == []
        assert metadata.confidence_score == 0.0
        assert metadata.profile_id  # 应该有UUID
        assert metadata.created_at  # 应该有时间戳

    def test_custom_values(self) -> None:
        """测试自定义值"""
        metadata = ProfileMetadata(
            profile_id="test-id",
            version=5,
            data_sources=["source1", "source2"],
            confidence_score=0.8,
        )
        assert metadata.profile_id == "test-id"
        assert metadata.version == 5
        assert len(metadata.data_sources) == 2
        assert metadata.confidence_score == 0.8


class TestProfileSummary:
    """ProfileSummary数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        summary = ProfileSummary()
        assert summary.user_id == "default"
        assert summary.primary_language == ""
        assert summary.active_goals_count == 0
        assert summary.profile_completeness == 0.0

    def test_custom_values(self) -> None:
        """测试自定义值"""
        summary = ProfileSummary(
            user_id="skyfire",
            primary_language="python",
            primary_framework="fastapi",
            active_goals_count=3,
            profile_completeness=0.75,
        )
        assert summary.user_id == "skyfire"
        assert summary.primary_language == "python"
        assert summary.primary_framework == "fastapi"
        assert summary.active_goals_count == 3


class TestDigitalTwinProfile:
    """DigitalTwinProfile数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        profile = DigitalTwinProfile()
        assert profile.user_id == "default"
        assert isinstance(profile.interaction_pattern, InteractionPattern)
        assert isinstance(profile.preferences, UserPreference)
        assert profile.goals == []
        assert isinstance(profile.metadata, ProfileMetadata)

    def test_to_dict(self) -> None:
        """测试转换为字典"""
        profile = DigitalTwinProfile(user_id="test_user")
        data = profile.to_dict()

        assert data["user_id"] == "test_user"
        assert "interaction_pattern" in data
        assert "preferences" in data
        assert "goals" in data
        assert "metadata" in data

    def test_from_dict(self) -> None:
        """测试从字典创建"""
        data = {
            "user_id": "test_user",
            "interaction_pattern": {
                "time_pattern": {
                    "peak_hours": [9, 10, 14],
                    "peak_days": [0, 1, 2],
                    "average_session_duration": 30.0,
                    "total_interactions": 100,
                },
                "command_pattern": {
                    "frequent_commands": [["git status", 50]],
                    "command_categories": {"git": 50},
                    "average_command_length": 15.0,
                },
                "question_pattern": {
                    "common_topics": [["python", 30]],
                    "question_types": {"how": 20},
                    "average_question_length": 50.0,
                },
                "analysis_timestamp": "2024-01-01T00:00:00",
                "data_range_start": "2023-01-01",
                "data_range_end": "2024-01-01",
                "confidence_score": 0.8,
            },
            "preferences": {
                "user_id": "test_user",
                "code_style": {"preferred_style": "concise"},
                "tech_stack": {"preferred_languages": ["python"]},
                "interaction_style": {"preferred_style": "friendly"},
            },
            "goals": [
                {
                    "id": "goal-1",
                    "goal_type": "short_term",
                    "description": "Test goal",
                    "status": "active",
                }
            ],
            "metadata": {
                "profile_id": "profile-1",
                "version": 2,
                "confidence_score": 0.7,
            },
        }

        profile = DigitalTwinProfile.from_dict(data)

        assert profile.user_id == "test_user"
        assert profile.interaction_pattern.time_pattern.peak_hours == [9, 10, 14]
        assert profile.preferences.tech_stack.preferred_languages == ["python"]
        assert len(profile.goals) == 1
        assert profile.goals[0].description == "Test goal"
        assert profile.metadata.version == 2

    def test_roundtrip(self) -> None:
        """测试序列化往返"""
        original = DigitalTwinProfile(
            user_id="roundtrip_user",
            goals=[
                TrackedGoal(
                    id="g1",
                    goal_type=GoalType.SHORT_TERM,
                    description="Test",
                    status=GoalStatus.ACTIVE,
                )
            ],
        )

        data = original.to_dict()
        restored = DigitalTwinProfile.from_dict(data)

        assert restored.user_id == original.user_id
        assert len(restored.goals) == len(original.goals)


class TestUserProfileAggregator:
    """UserProfileAggregator类测试"""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def aggregator(self, temp_dir: Path) -> UserProfileAggregator:
        """创建聚合器实例"""
        with patch(
            "jarvis.jarvis_digital_twin.user_profile.aggregator.get_data_dir",
            return_value=str(temp_dir),
        ):
            return UserProfileAggregator(user_id="test_user")

    def test_init(self, aggregator: UserProfileAggregator) -> None:
        """测试初始化"""
        assert aggregator.user_id == "test_user"
        assert aggregator.history_analyzer is not None
        assert aggregator.preference_learner is not None
        assert aggregator.goal_tracker is not None

    def test_build_profile_empty(self, aggregator: UserProfileAggregator) -> None:
        """测试构建空画像"""
        profile = aggregator.build_profile()

        assert profile.user_id == "test_user"
        assert isinstance(profile, DigitalTwinProfile)
        assert profile.metadata.version == 1

    def test_build_profile_with_options(
        self, aggregator: UserProfileAggregator
    ) -> None:
        """测试带选项构建画像"""
        profile = aggregator.build_profile(
            include_history=False,
            include_preferences=True,
            include_goals=False,
        )

        assert profile.user_id == "test_user"
        # 不包含历史时，data_sources不应包含history_analyzer
        assert (
            "history_analyzer" not in profile.metadata.data_sources
            or profile.metadata.data_sources == []
        )

    def test_get_profile_summary(self, aggregator: UserProfileAggregator) -> None:
        """测试获取画像摘要"""
        summary = aggregator.get_profile_summary()

        assert isinstance(summary, ProfileSummary)
        assert summary.user_id == "test_user"

    def test_save_and_load_profile(
        self, aggregator: UserProfileAggregator, temp_dir: Path
    ) -> None:
        """测试保存和加载画像"""
        # 构建画像
        profile = aggregator.build_profile()

        # 保存到指定路径
        save_path = temp_dir / "test_profile.json"
        result_path = aggregator.save_profile(str(save_path))

        assert Path(result_path).exists()

        # 加载画像
        loaded = aggregator.load_profile(str(save_path))

        assert loaded is not None
        assert loaded.user_id == profile.user_id

    def test_load_nonexistent_profile(self, aggregator: UserProfileAggregator) -> None:
        """测试加载不存在的画像"""
        result = aggregator.load_profile("/nonexistent/path.json")
        assert result is None

    def test_get_current_profile(self, aggregator: UserProfileAggregator) -> None:
        """测试获取当前画像"""
        # 初始时应为None
        assert aggregator.get_current_profile() is None

        # 构建后应有值
        aggregator.build_profile()
        assert aggregator.get_current_profile() is not None

    def test_update_profile_with_interaction(
        self, aggregator: UserProfileAggregator
    ) -> None:
        """测试使用交互数据更新画像"""
        interaction = InteractionData(
            content="I prefer python and fastapi",
            interaction_type="command",
            tags=["python", "fastapi"],
        )

        profile = aggregator.update_profile(interaction_data=interaction)

        assert isinstance(profile, DigitalTwinProfile)

    def test_update_profile_with_goal_context(
        self, aggregator: UserProfileAggregator
    ) -> None:
        """测试使用目标上下文更新画像"""
        profile = aggregator.update_profile(goal_context="我想要今天完成这个功能")

        assert isinstance(profile, DigitalTwinProfile)

    def test_version_increment(self, aggregator: UserProfileAggregator) -> None:
        """测试版本递增"""
        profile1 = aggregator.build_profile()
        assert profile1.metadata.version == 1

        profile2 = aggregator.build_profile()
        assert profile2.metadata.version == 2

    def test_get_profile_versions(
        self, aggregator: UserProfileAggregator, temp_dir: Path
    ) -> None:
        """测试获取画像版本列表"""
        # 保存多个版本
        aggregator.build_profile()
        aggregator.save_profile()

        aggregator.build_profile()
        aggregator.save_profile()

        versions = aggregator.get_profile_versions()

        # 应该有2个版本
        assert len(versions) >= 1

    def test_delete_profile_version(
        self, aggregator: UserProfileAggregator, temp_dir: Path
    ) -> None:
        """测试删除画像版本"""
        # 保存一个版本
        aggregator.build_profile()
        aggregator.save_profile()

        # 删除版本1
        result = aggregator.delete_profile_version(1)
        assert result is True

        # 再次删除应该失败
        result = aggregator.delete_profile_version(1)
        assert result is False


class TestDigitalTwinProfileEdgeCases:
    """DigitalTwinProfile边界情况测试"""

    def test_from_dict_with_empty_data(self) -> None:
        """测试从空字典创建"""
        profile = DigitalTwinProfile.from_dict({})

        assert profile.user_id == "default"
        assert profile.goals == []

    def test_from_dict_with_partial_data(self) -> None:
        """测试从部分数据创建"""
        data = {
            "user_id": "partial_user",
            "preferences": {"tech_stack": {"preferred_languages": ["rust", "go"]}},
        }

        profile = DigitalTwinProfile.from_dict(data)

        assert profile.user_id == "partial_user"
        assert "rust" in profile.preferences.tech_stack.preferred_languages

    def test_to_dict_with_goals(self) -> None:
        """测试带目标的序列化"""
        profile = DigitalTwinProfile(
            user_id="goal_user",
            goals=[
                TrackedGoal(
                    id="g1",
                    goal_type=GoalType.LONG_TERM,
                    description="Learn Rust",
                    confidence=0.9,
                ),
                TrackedGoal(
                    id="g2",
                    goal_type=GoalType.SHORT_TERM,
                    description="Fix bug",
                    confidence=0.7,
                ),
            ],
        )

        data = profile.to_dict()

        assert len(data["goals"]) == 2
        assert data["goals"][0]["description"] == "Learn Rust"
        assert data["goals"][1]["goal_type"] == "short_term"
