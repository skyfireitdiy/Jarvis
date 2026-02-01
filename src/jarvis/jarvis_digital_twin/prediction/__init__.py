"""Prediction - 预判引擎子模块。

提供预判引擎功能，包括：
- 上下文预测：预测下一个问题/操作
- 需求推理：从显式需求推理隐式需求
- 时机判断：判断何时主动提供帮助
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PredictionType(Enum):
    """预测类型枚举。"""

    NEXT_QUESTION = "next_question"  # 预测下一个问题
    NEXT_ACTION = "next_action"  # 预测下一步操作
    NEEDED_HELP = "needed_help"  # 预测需要的帮助
    IMPLICIT_NEED = "implicit_need"  # 隐式需求
    FOLLOW_UP_TASK = "follow_up_task"  # 后续任务
    ROOT_CAUSE = "root_cause"  # 根本原因


class PredictionConfidence(Enum):
    """预测置信度枚举。"""

    VERY_HIGH = "very_high"  # 非常高 (≥90%)
    HIGH = "high"  # 高 (70-90%)
    MEDIUM = "medium"  # 中等 (50-70%)
    LOW = "low"  # 低 (30-50%)
    VERY_LOW = "very_low"  # 非常低 (<30%)

    @classmethod
    def from_score(cls, score: float) -> "PredictionConfidence":
        """根据分数返回置信度等级。"""
        if score >= 0.9:
            return cls.VERY_HIGH
        elif score >= 0.7:
            return cls.HIGH
        elif score >= 0.5:
            return cls.MEDIUM
        elif score >= 0.3:
            return cls.LOW
        else:
            return cls.VERY_LOW


class TimingDecision(Enum):
    """时机决策枚举。"""

    OFFER_HELP = "offer_help"  # 主动提供帮助
    STAY_SILENT = "stay_silent"  # 保持沉默
    ASK_CONFIRMATION = "ask_confirmation"  # 请求确认
    WAIT_FOR_MORE_CONTEXT = "wait_for_more_context"  # 等待更多上下文


@dataclass
class PredictionContext:
    """预测上下文。

    包含进行预测所需的所有上下文信息。
    """

    # 当前对话内容
    current_message: str = ""
    # 对话历史（最近N条）
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    # 当前代码上下文
    code_context: dict[str, Any] = field(default_factory=dict)
    # 当前项目状态
    project_state: dict[str, Any] = field(default_factory=dict)
    # 用户画像数据
    user_profile: dict[str, Any] = field(default_factory=dict)
    # 时间戳
    timestamp: datetime = field(default_factory=datetime.now)
    # 额外元数据
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PredictionResult:
    """预测结果。

    包含预测的内容、类型、置信度等信息。
    """

    # 预测类型
    prediction_type: PredictionType
    # 预测内容
    content: str
    # 置信度分数 (0-1)
    confidence_score: float
    # 置信度等级
    confidence_level: PredictionConfidence = field(init=False)
    # 推理依据
    reasoning: str = ""
    # 相关证据
    evidence: list[str] = field(default_factory=list)
    # 备选预测
    alternatives: list["PredictionResult"] = field(default_factory=list)
    # 时间戳
    timestamp: datetime = field(default_factory=datetime.now)
    # 额外元数据
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """初始化后处理。"""
        self.confidence_level = PredictionConfidence.from_score(self.confidence_score)


@dataclass
class TimingResult:
    """时机判断结果。

    包含时机决策、置信度和推理依据。
    """

    # 时机决策
    decision: TimingDecision
    # 置信度分数 (0-1)
    confidence_score: float
    # 置信度等级
    confidence_level: PredictionConfidence = field(init=False)
    # 推理依据
    reasoning: str = ""
    # 建议的行动
    suggested_action: str = ""
    # 延迟时间（秒），如果需要等待
    delay_seconds: float = 0.0
    # 时间戳
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        """初始化后处理。"""
        self.confidence_level = PredictionConfidence.from_score(self.confidence_score)


@dataclass
class InferenceResult:
    """推理结果。

    包含推理出的需求、任务或原因。
    """

    # 推理类型
    inference_type: PredictionType
    # 推理内容
    content: str
    # 置信度分数 (0-1)
    confidence_score: float
    # 置信度等级
    confidence_level: PredictionConfidence = field(init=False)
    # 推理链（推理步骤）
    reasoning_chain: list[str] = field(default_factory=list)
    # 支持证据
    supporting_evidence: list[str] = field(default_factory=list)
    # 反对证据
    opposing_evidence: list[str] = field(default_factory=list)
    # 相关推理
    related_inferences: list["InferenceResult"] = field(default_factory=list)
    # 时间戳
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        """初始化后处理。"""
        self.confidence_level = PredictionConfidence.from_score(self.confidence_score)


# 导入子模块类（放在末尾避免循环导入）
from jarvis.jarvis_digital_twin.prediction.context_predictor import ContextPredictor  # noqa: E402
from jarvis.jarvis_digital_twin.prediction.need_inferrer import NeedInferrer  # noqa: E402
from jarvis.jarvis_digital_twin.prediction.timing_judge import TimingJudge  # noqa: E402

# 导出所有公共接口
__all__ = [
    # 枚举类型
    "PredictionType",
    "PredictionConfidence",
    "TimingDecision",
    # 数据类
    "PredictionContext",
    "PredictionResult",
    "TimingResult",
    "InferenceResult",
    # 预测器类
    "ContextPredictor",
    "NeedInferrer",
    "TimingJudge",
]
