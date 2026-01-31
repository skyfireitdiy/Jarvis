"""智能基础设施层

提供双轨制智能架构的核心组件：
- LLMReasoner: LLM 推理引擎
- RuleLearner: 规则学习器
- HybridEngine: 混合引擎基类
"""

from jarvis.jarvis_autonomous.intelligence.hybrid_engine import (
    HybridEngine,
    InferenceMode,
    InferenceResult,
)
from jarvis.jarvis_autonomous.intelligence.llm_reasoning import (
    LLMClient,
    LLMReasoner,
    ReasoningContext,
    ReasoningResult,
    ReasoningType,
)
from jarvis.jarvis_autonomous.intelligence.rule_learner import (
    LearnedRule,
    RuleLearner,
    RuleStatus,
    RuleType,
)

__all__ = [
    # LLM 推理
    "LLMClient",
    "LLMReasoner",
    "ReasoningContext",
    "ReasoningResult",
    "ReasoningType",
    # 规则学习
    "RuleLearner",
    "LearnedRule",
    "RuleType",
    "RuleStatus",
    # 混合引擎
    "HybridEngine",
    "InferenceMode",
    "InferenceResult",
]
