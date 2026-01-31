"""User Profile - 用户画像子模块。

提供用户画像深度建模功能，包括：
- 交互历史分析
- 偏好学习
- 目标追踪
- 画像聚合
"""

from jarvis.jarvis_digital_twin.user_profile.history_analyzer import (
    HistoryAnalyzer,
    InteractionPattern,
    InteractionRecord,
    TimePattern,
    CommandPattern,
    QuestionPattern,
    WorkSchedule,
)
from jarvis.jarvis_digital_twin.user_profile.preference_learner import (
    PreferenceLearner,
    UserPreference,
    CodeStyleDetail,
    TechStackPreference,
    InteractionStyleDetail,
    PreferenceConfidence,
)
from jarvis.jarvis_digital_twin.user_profile.goal_tracker import (
    GoalTracker,
    TrackedGoal,
    GoalType,
    GoalStatus,
    GoalProgress,
    GoalInferenceResult,
)
from jarvis.jarvis_digital_twin.user_profile.aggregator import (
    UserProfileAggregator,
    DigitalTwinProfile,
    ProfileMetadata,
    ProfileSummary,
)

__all__ = [
    # History Analyzer
    "HistoryAnalyzer",
    "InteractionPattern",
    "InteractionRecord",
    "TimePattern",
    "CommandPattern",
    "QuestionPattern",
    "WorkSchedule",
    # Preference Learner
    "PreferenceLearner",
    "UserPreference",
    "CodeStyleDetail",
    "TechStackPreference",
    "InteractionStyleDetail",
    "PreferenceConfidence",
    # Goal Tracker
    "GoalTracker",
    "TrackedGoal",
    "GoalType",
    "GoalStatus",
    "GoalProgress",
    "GoalInferenceResult",
    # Aggregator
    "UserProfileAggregator",
    "DigitalTwinProfile",
    "ProfileMetadata",
    "ProfileSummary",
]
