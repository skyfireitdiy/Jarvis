"""用户画像聚合器模块

整合历史分析、偏好学习、目标追踪结果，生成完整的用户画像。
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import uuid

from jarvis.jarvis_utils.config import get_data_dir

from .history_analyzer import HistoryAnalyzer, InteractionPattern
from .preference_learner import PreferenceLearner, UserPreference, InteractionData
from .goal_tracker import GoalTracker, TrackedGoal, GoalStatus


@dataclass
class ProfileMetadata:
    """画像元数据

    记录用户画像的版本和更新信息。
    """

    profile_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    version: int = 1
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    data_sources: List[str] = field(default_factory=list)
    confidence_score: float = 0.0


@dataclass
class ProfileSummary:
    """画像摘要

    用户画像的可读摘要信息。
    """

    user_id: str = "default"
    primary_language: str = ""
    primary_framework: str = ""
    interaction_style: str = ""
    active_goals_count: int = 0
    completed_goals_count: int = 0
    peak_hours: List[int] = field(default_factory=list)
    top_commands: List[str] = field(default_factory=list)
    profile_completeness: float = 0.0


@dataclass
class DigitalTwinProfile:
    """数字孪生画像数据类

    整合用户的交互模式、偏好和目标，形成完整的用户画像。
    """

    user_id: str = "default"
    interaction_pattern: InteractionPattern = field(default_factory=InteractionPattern)
    preferences: UserPreference = field(default_factory=UserPreference)
    goals: List[TrackedGoal] = field(default_factory=list)
    metadata: ProfileMetadata = field(default_factory=ProfileMetadata)
    custom_attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典

        Returns:
            画像的字典表示
        """
        return {
            "user_id": self.user_id,
            "interaction_pattern": {
                "time_pattern": {
                    "peak_hours": self.interaction_pattern.time_pattern.peak_hours,
                    "peak_days": self.interaction_pattern.time_pattern.peak_days,
                    "average_session_duration": self.interaction_pattern.time_pattern.average_session_duration,
                    "total_interactions": self.interaction_pattern.time_pattern.total_interactions,
                },
                "command_pattern": {
                    "frequent_commands": self.interaction_pattern.command_pattern.frequent_commands,
                    "command_categories": self.interaction_pattern.command_pattern.command_categories,
                    "average_command_length": self.interaction_pattern.command_pattern.average_command_length,
                },
                "question_pattern": {
                    "common_topics": self.interaction_pattern.question_pattern.common_topics,
                    "question_types": self.interaction_pattern.question_pattern.question_types,
                    "average_question_length": self.interaction_pattern.question_pattern.average_question_length,
                },
                "analysis_timestamp": self.interaction_pattern.analysis_timestamp,
                "data_range_start": self.interaction_pattern.data_range_start,
                "data_range_end": self.interaction_pattern.data_range_end,
                "confidence_score": self.interaction_pattern.confidence_score,
            },
            "preferences": self.preferences.to_dict(),
            "goals": [goal.to_dict() for goal in self.goals],
            "metadata": {
                "profile_id": self.metadata.profile_id,
                "version": self.metadata.version,
                "created_at": self.metadata.created_at,
                "updated_at": self.metadata.updated_at,
                "data_sources": self.metadata.data_sources,
                "confidence_score": self.metadata.confidence_score,
            },
            "custom_attributes": self.custom_attributes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DigitalTwinProfile":
        """从字典创建DigitalTwinProfile对象

        Args:
            data: 画像数据字典

        Returns:
            DigitalTwinProfile实例
        """
        from .history_analyzer import (
            TimePattern,
            CommandPattern,
            QuestionPattern,
            InteractionPattern,
        )

        # 解析交互模式
        ip_data = data.get("interaction_pattern", {})
        tp_data = ip_data.get("time_pattern", {})
        cp_data = ip_data.get("command_pattern", {})
        qp_data = ip_data.get("question_pattern", {})

        time_pattern = TimePattern(
            peak_hours=tp_data.get("peak_hours", []),
            peak_days=tp_data.get("peak_days", []),
            average_session_duration=tp_data.get("average_session_duration", 0.0),
            total_interactions=tp_data.get("total_interactions", 0),
        )

        # 处理frequent_commands - 可能是列表的列表或元组列表
        freq_cmds_raw = cp_data.get("frequent_commands", [])
        freq_cmds = [
            tuple(cmd) if isinstance(cmd, list) else cmd for cmd in freq_cmds_raw
        ]

        command_pattern = CommandPattern(
            frequent_commands=freq_cmds,
            command_categories=cp_data.get("command_categories", {}),
            average_command_length=cp_data.get("average_command_length", 0.0),
        )

        # 处理common_topics - 可能是列表的列表或元组列表
        topics_raw = qp_data.get("common_topics", [])
        topics = [tuple(t) if isinstance(t, list) else t for t in topics_raw]

        question_pattern = QuestionPattern(
            common_topics=topics,
            question_types=qp_data.get("question_types", {}),
            average_question_length=qp_data.get("average_question_length", 0.0),
        )

        interaction_pattern = InteractionPattern(
            time_pattern=time_pattern,
            command_pattern=command_pattern,
            question_pattern=question_pattern,
            analysis_timestamp=ip_data.get("analysis_timestamp", ""),
            data_range_start=ip_data.get("data_range_start", ""),
            data_range_end=ip_data.get("data_range_end", ""),
            confidence_score=ip_data.get("confidence_score", 0.0),
        )

        # 解析偏好
        preferences = UserPreference.from_dict(data.get("preferences", {}))

        # 解析目标
        goals = [
            TrackedGoal.from_dict(goal_data) for goal_data in data.get("goals", [])
        ]

        # 解析元数据
        meta_data = data.get("metadata", {})
        metadata = ProfileMetadata(
            profile_id=meta_data.get("profile_id", str(uuid.uuid4())),
            version=meta_data.get("version", 1),
            created_at=meta_data.get("created_at", datetime.now().isoformat()),
            updated_at=meta_data.get("updated_at", datetime.now().isoformat()),
            data_sources=meta_data.get("data_sources", []),
            confidence_score=meta_data.get("confidence_score", 0.0),
        )

        return cls(
            user_id=data.get("user_id", "default"),
            interaction_pattern=interaction_pattern,
            preferences=preferences,
            goals=goals,
            metadata=metadata,
            custom_attributes=data.get("custom_attributes", {}),
        )


class UserProfileAggregator:
    """用户画像聚合器

    整合历史分析、偏好学习、目标追踪结果，生成完整的用户画像。
    """

    def __init__(
        self,
        user_id: str = "default",
        history_analyzer: Optional[HistoryAnalyzer] = None,
        preference_learner: Optional[PreferenceLearner] = None,
        goal_tracker: Optional[GoalTracker] = None,
    ) -> None:
        """初始化聚合器

        Args:
            user_id: 用户ID
            history_analyzer: 历史分析器实例（可选）
            preference_learner: 偏好学习器实例（可选）
            goal_tracker: 目标追踪器实例（可选）
        """
        self.user_id = user_id
        self._history_analyzer = history_analyzer or HistoryAnalyzer()
        self._preference_learner = preference_learner or PreferenceLearner(user_id)
        self._goal_tracker = goal_tracker or GoalTracker()
        self._current_profile: Optional[DigitalTwinProfile] = None
        self._profile_dir = Path(get_data_dir()) / "digital_twin" / "profiles"
        self._profile_dir.mkdir(parents=True, exist_ok=True)

    @property
    def history_analyzer(self) -> HistoryAnalyzer:
        """获取历史分析器"""
        return self._history_analyzer

    @property
    def preference_learner(self) -> PreferenceLearner:
        """获取偏好学习器"""
        return self._preference_learner

    @property
    def goal_tracker(self) -> GoalTracker:
        """获取目标追踪器"""
        return self._goal_tracker

    def build_profile(
        self,
        include_history: bool = True,
        include_preferences: bool = True,
        include_goals: bool = True,
    ) -> DigitalTwinProfile:
        """构建用户画像

        整合各个组件的分析结果，生成完整的用户画像。

        Args:
            include_history: 是否包含历史分析
            include_preferences: 是否包含偏好学习
            include_goals: 是否包含目标追踪

        Returns:
            完整的用户画像
        """
        data_sources: List[str] = []
        confidence_scores: List[float] = []

        # 获取交互模式
        interaction_pattern = InteractionPattern()
        if include_history:
            pattern = self._history_analyzer.analyze_interactions()
            if pattern is not None:
                interaction_pattern = pattern
                data_sources.append("history_analyzer")
                confidence_scores.append(interaction_pattern.confidence_score)

        # 获取用户偏好
        preferences = UserPreference(user_id=self.user_id)
        if include_preferences:
            pref = self._preference_learner.preference
            if pref:
                preferences = pref
                data_sources.append("preference_learner")
                # 计算偏好置信度
                pref_confidence = (
                    preferences.code_style.confidence.value
                    + preferences.tech_stack.confidence.value
                    + preferences.interaction_style.confidence.value
                ) / 3
                confidence_scores.append(pref_confidence)

        # 获取目标列表
        goals: List[TrackedGoal] = []
        if include_goals:
            active_goals = self._goal_tracker.get_current_goals(
                status=GoalStatus.ACTIVE
            )
            goals = active_goals
            if goals:
                data_sources.append("goal_tracker")
                # 计算目标置信度
                goal_confidence = (
                    sum(g.confidence for g in goals) / len(goals) if goals else 0.0
                )
                confidence_scores.append(goal_confidence)

        # 计算整体置信度
        overall_confidence = (
            sum(confidence_scores) / len(confidence_scores)
            if confidence_scores
            else 0.0
        )

        # 创建元数据
        metadata = ProfileMetadata(
            data_sources=data_sources,
            confidence_score=overall_confidence,
        )

        # 如果已有画像，保留版本信息
        if self._current_profile:
            metadata.profile_id = self._current_profile.metadata.profile_id
            metadata.version = self._current_profile.metadata.version + 1
            metadata.created_at = self._current_profile.metadata.created_at

        # 构建画像
        profile = DigitalTwinProfile(
            user_id=self.user_id,
            interaction_pattern=interaction_pattern,
            preferences=preferences,
            goals=goals,
            metadata=metadata,
        )

        self._current_profile = profile
        return profile

    def get_profile_summary(self) -> ProfileSummary:
        """获取画像摘要

        生成用户画像的可读摘要信息。

        Returns:
            画像摘要
        """
        if not self._current_profile:
            self.build_profile()

        profile = self._current_profile
        assert profile is not None

        # 提取主要语言
        primary_language = ""
        if profile.preferences.tech_stack.preferred_languages:
            primary_language = profile.preferences.tech_stack.preferred_languages[0]

        # 提取主要框架
        primary_framework = ""
        if profile.preferences.tech_stack.preferred_frameworks:
            primary_framework = profile.preferences.tech_stack.preferred_frameworks[0]

        # 提取交互风格
        interaction_style = profile.preferences.interaction_style.preferred_style.value

        # 统计目标
        active_goals = [g for g in profile.goals if g.status == GoalStatus.ACTIVE]
        completed_goals = [g for g in profile.goals if g.status == GoalStatus.COMPLETED]

        # 提取高峰时段
        peak_hours = profile.interaction_pattern.time_pattern.peak_hours[:3]

        # 提取常用命令
        top_commands = [
            cmd
            for cmd, _ in profile.interaction_pattern.command_pattern.frequent_commands[
                :5
            ]
        ]

        # 计算画像完整度
        completeness_factors = [
            bool(primary_language),
            bool(primary_framework),
            bool(profile.goals),
            bool(peak_hours),
            bool(top_commands),
            profile.metadata.confidence_score > 0.3,
        ]
        profile_completeness = sum(completeness_factors) / len(completeness_factors)

        return ProfileSummary(
            user_id=profile.user_id,
            primary_language=primary_language,
            primary_framework=primary_framework,
            interaction_style=interaction_style,
            active_goals_count=len(active_goals),
            completed_goals_count=len(completed_goals),
            peak_hours=peak_hours,
            top_commands=top_commands,
            profile_completeness=profile_completeness,
        )

    def save_profile(self, file_path: Optional[str] = None) -> str:
        """保存用户画像

        将当前画像保存到文件。

        Args:
            file_path: 保存路径（可选，默认使用标准路径）

        Returns:
            保存的文件路径
        """
        if not self._current_profile:
            self.build_profile()

        profile = self._current_profile
        assert profile is not None

        # 更新时间戳
        profile.metadata.updated_at = datetime.now().isoformat()

        # 确定保存路径
        if file_path:
            save_path = Path(file_path)
        else:
            filename = f"{self.user_id}_v{profile.metadata.version}.json"
            save_path = self._profile_dir / filename

        # 确保目录存在
        save_path.parent.mkdir(parents=True, exist_ok=True)

        # 保存到文件
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)

        return str(save_path)

    def load_profile(
        self, file_path: Optional[str] = None
    ) -> Optional[DigitalTwinProfile]:
        """加载用户画像

        从文件加载画像。

        Args:
            file_path: 文件路径（可选，默认加载最新版本）

        Returns:
            加载的画像，如果文件不存在则返回None
        """
        load_path: Optional[Path] = None
        if file_path:
            load_path = Path(file_path)
        else:
            # 查找最新版本
            load_path = self._find_latest_profile()

        if load_path is None:
            return None

        if not load_path.exists():
            return None

        with open(load_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        profile = DigitalTwinProfile.from_dict(data)
        self._current_profile = profile
        return profile

    def _find_latest_profile(self) -> Optional[Path]:
        """查找最新版本的画像文件

        Returns:
            最新画像文件路径，如果不存在则返回None
        """
        pattern = f"{self.user_id}_v*.json"
        files = list(self._profile_dir.glob(pattern))

        if not files:
            return None

        # 按版本号排序
        def extract_version(p: Path) -> int:
            try:
                # 从文件名提取版本号：user_id_v1.json -> 1
                name = p.stem  # user_id_v1
                version_str = name.split("_v")[-1]
                return int(version_str)
            except (ValueError, IndexError):
                return 0

        files.sort(key=extract_version, reverse=True)
        return files[0]

    def get_current_profile(self) -> Optional[DigitalTwinProfile]:
        """获取当前画像

        Returns:
            当前画像，如果未构建则返回None
        """
        return self._current_profile

    def update_profile(
        self,
        interaction_data: Optional[InteractionData] = None,
        goal_context: Optional[str] = None,
    ) -> DigitalTwinProfile:
        """更新用户画像

        基于新的交互数据更新画像。

        Args:
            interaction_data: 新的交互数据
            goal_context: 目标上下文（用于推断新目标）

        Returns:
            更新后的画像
        """
        # 如果有交互数据，更新偏好学习器
        if interaction_data:
            self._preference_learner.learn_from_interaction(interaction_data)

        # 如果有目标上下文，推断新目标
        if goal_context:
            self._goal_tracker.infer_goals_from_context(goal_context)

        # 重新构建画像
        return self.build_profile()

    def get_profile_versions(self) -> List[Dict[str, Any]]:
        """获取所有画像版本信息

        Returns:
            版本信息列表
        """
        pattern = f"{self.user_id}_v*.json"
        files = list(self._profile_dir.glob(pattern))

        versions: List[Dict[str, Any]] = []
        for file_path in files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    metadata = data.get("metadata", {})
                    versions.append(
                        {
                            "version": metadata.get("version", 0),
                            "created_at": metadata.get("created_at", ""),
                            "updated_at": metadata.get("updated_at", ""),
                            "file_path": str(file_path),
                            "confidence_score": metadata.get("confidence_score", 0.0),
                        }
                    )
            except (json.JSONDecodeError, IOError):
                continue

        # 按版本号排序
        versions.sort(key=lambda x: x.get("version", 0), reverse=True)
        return versions

    def delete_profile_version(self, version: int) -> bool:
        """删除指定版本的画像

        Args:
            version: 版本号

        Returns:
            是否删除成功
        """
        filename = f"{self.user_id}_v{version}.json"
        file_path = self._profile_dir / filename

        if file_path.exists():
            file_path.unlink()
            return True
        return False
