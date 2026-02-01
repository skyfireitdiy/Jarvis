"""Proactive Service - 主动服务子模块。

提供主动服务功能，包括：
- 服务触发：基于上下文触发主动服务
- 服务执行：执行各类主动服务
- 反馈学习：根据用户反馈优化服务
"""

from jarvis.jarvis_digital_twin.proactive_service.types import (
    # 枚举类型
    ConflictResolution,
    FeedbackType,
    ServicePriority,
    ServiceStatus,
    ServiceType,
    # 数据类
    ExecutionPlan,
    ServiceDefinition,
    ServiceFeedback,
    ServiceResult,
    TriggerContext,
    # Protocol接口
    ServiceHandlerProtocol,
    TriggerEvaluatorProtocol,
)
from jarvis.jarvis_digital_twin.proactive_service.service_trigger import (
    ContextTriggerEvaluator,
    KeywordTriggerEvaluator,
    PatternTriggerEvaluator,
    ServiceTrigger,
    TriggerRecord,
)
from jarvis.jarvis_digital_twin.proactive_service.service_orchestrator import (
    ConflictRule,
    ServiceOrchestrator,
)
from jarvis.jarvis_digital_twin.proactive_service.service_executor import (
    ClarificationHandler,
    InformationHandler,
    ReminderHandler,
    ServiceExecutor,
    SuggestionHandler,
)
from jarvis.jarvis_digital_twin.proactive_service.feedback_learner import (
    FeedbackLearner,
    LearningResult,
    ServiceStats,
)
from jarvis.jarvis_digital_twin.proactive_service.manager import (
    ProactiveServiceManager,
)

# 导出所有公共接口
__all__ = [
    # 枚举类型
    "ConflictResolution",
    "FeedbackType",
    "ServicePriority",
    "ServiceStatus",
    "ServiceType",
    # 数据类
    "ConflictRule",
    "ExecutionPlan",
    "ServiceDefinition",
    "ServiceFeedback",
    "ServiceResult",
    "TriggerContext",
    "TriggerRecord",
    # Protocol接口
    "ServiceHandlerProtocol",
    "TriggerEvaluatorProtocol",
    # 服务触发器
    "ContextTriggerEvaluator",
    "KeywordTriggerEvaluator",
    "PatternTriggerEvaluator",
    "ServiceTrigger",
    # 服务编排器
    "ServiceOrchestrator",
    # 服务执行器
    "ClarificationHandler",
    "InformationHandler",
    "ReminderHandler",
    "ServiceExecutor",
    "SuggestionHandler",
    # 反馈学习器
    "FeedbackLearner",
    "LearningResult",
    "ServiceStats",
    # 主动服务管理器
    "ProactiveServiceManager",
]
