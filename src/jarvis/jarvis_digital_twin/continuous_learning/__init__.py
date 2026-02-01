"""持续学习系统模块。

实现Jarvis的持续学习能力，包括：
- 知识学习和管理
- 技能习得和评估
- 经验积累和应用
- 学习结果跟踪
"""

from jarvis.jarvis_digital_twin.continuous_learning.knowledge_acquirer import (
    CodePatternSource,
    ErrorLearningSource,
    InteractionKnowledgeSource,
    KnowledgeAcquirer,
)
from jarvis.jarvis_digital_twin.continuous_learning.skill_learner import (
    RecencyEvaluator,
    SkillLearner,
    SuccessRateEvaluator,
    UsageFrequencyEvaluator,
)
from jarvis.jarvis_digital_twin.continuous_learning.experience_accumulator import (
    ContextSimilarityMatcher,
    ExperienceAccumulator,
    KeywordMatcher,
    OutcomeMatcher,
)
from jarvis.jarvis_digital_twin.continuous_learning.adaptive_engine import (
    AdaptationType,
    AdaptationResult,
    AdaptiveEngine,
    BehaviorAdapter,
    StrategyAdapter,
    ThresholdAdapter,
)
from jarvis.jarvis_digital_twin.continuous_learning.manager import (
    ContinuousLearningManager,
)
from jarvis.jarvis_digital_twin.continuous_learning.types import (
    # 枚举类型
    ExperienceType,
    KnowledgeType,
    LearningStatus,
    SkillType,
    # 数据类
    Experience,
    Knowledge,
    LearningResult,
    Skill,
    # Protocol接口
    ExperienceMatcherProtocol,
    KnowledgeSourceProtocol,
    SkillEvaluatorProtocol,
)

__all__ = [
    # 枚举类型
    "KnowledgeType",
    "SkillType",
    "ExperienceType",
    "LearningStatus",
    # 数据类
    "Knowledge",
    "Skill",
    "Experience",
    "LearningResult",
    # Protocol接口
    "KnowledgeSourceProtocol",
    "SkillEvaluatorProtocol",
    "ExperienceMatcherProtocol",
    # 知识获取器
    "KnowledgeAcquirer",
    "InteractionKnowledgeSource",
    "CodePatternSource",
    "ErrorLearningSource",
    # 技能学习器
    "SkillLearner",
    "UsageFrequencyEvaluator",
    "SuccessRateEvaluator",
    "RecencyEvaluator",
    # 经验积累器
    "ExperienceAccumulator",
    "KeywordMatcher",
    "ContextSimilarityMatcher",
    "OutcomeMatcher",
    # 自适应引擎
    "AdaptationType",
    "AdaptationResult",
    "AdaptiveEngine",
    "ThresholdAdapter",
    "StrategyAdapter",
    "BehaviorAdapter",
    # 持续学习管理器
    "ContinuousLearningManager",
]
