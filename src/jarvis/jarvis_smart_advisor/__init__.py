"""智能顾问模块

该模块提供智能顾问功能，包括：
- 智能问答：回答项目相关问题
- 代码审查建议：生成代码改进建议
- 架构决策辅助：提供架构设计建议
- 最佳实践推荐：推荐相关的规则和方法论

示例：
    from jarvis.jarvis_smart_advisor import SmartAdvisor

    advisor = SmartAdvisor()
    answer = advisor.ask("这个项目有哪些模块？")
    print(answer.text)
"""

from jarvis.jarvis_smart_advisor.advisor import SmartAdvisor
from jarvis.jarvis_smart_advisor.qa_engine import Answer, QAEngine, Question
from jarvis.jarvis_smart_advisor.review_advisor import (
    ReviewAdvisor,
    ReviewCategory,
    ReviewReport,
    ReviewSeverity,
    ReviewSuggestion,
)
from jarvis.jarvis_smart_advisor.architecture_advisor import (
    ArchitectureAdvisor,
    ArchitectureDecision,
    ArchitectureOption,
    DecisionImpact,
    DecisionType,
)
from jarvis.jarvis_smart_advisor.practice_advisor import (
    BestPractice,
    PracticeAdvisor,
    PracticeCategory,
    PracticeContext,
    PracticePriority,
    PracticeRecommendation,
)

__all__ = [
    "SmartAdvisor",
    "QAEngine",
    "Question",
    "Answer",
    "ReviewAdvisor",
    "ReviewSuggestion",
    "ReviewReport",
    "ReviewSeverity",
    "ReviewCategory",
    "ArchitectureAdvisor",
    "ArchitectureDecision",
    "ArchitectureOption",
    "DecisionImpact",
    "DecisionType",
    "PracticeAdvisor",
    "BestPractice",
    "PracticeCategory",
    "PracticeContext",
    "PracticePriority",
    "PracticeRecommendation",
]

__version__ = "0.1.0"
