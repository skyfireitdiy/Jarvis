"""Jarvis Digital Twin - 数字孪生智能模块。

阶段5：数字孪生智能 - 完全理解用户，成为数字化的自我延伸。

子模块：
- user_profile: 用户画像深度建模（阶段5.1）
"""

from jarvis.jarvis_digital_twin.user_profile import (
    # History Analyzer
    HistoryAnalyzer,
    InteractionPattern,
    InteractionRecord,
    TimePattern,
    CommandPattern,
    QuestionPattern,
    WorkSchedule,
    # Preference Learner
    PreferenceLearner,
    UserPreference,
    CodeStyleDetail,
    TechStackPreference,
    InteractionStyleDetail,
    PreferenceConfidence,
    # Goal Tracker
    GoalTracker,
    TrackedGoal,
    GoalType,
    GoalStatus,
    GoalProgress,
    GoalInferenceResult,
    # Aggregator
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
