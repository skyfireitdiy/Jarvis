"""主动服务系统类型定义模块。

定义主动服务系统所需的所有类型，包括：
- 服务类型枚举
- 服务优先级枚举
- 服务状态枚举
- 反馈类型枚举
- 服务定义数据类
- 服务结果数据类
- 服务反馈数据类
- 触发上下文数据类
- Protocol接口定义
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol


class ServiceType(Enum):
    """服务类型枚举。

    定义主动服务的不同类型。
    """

    SUGGESTION = "suggestion"  # 建议类服务
    REMINDER = "reminder"  # 提醒类服务
    AUTO_ACTION = "auto_action"  # 自动操作类服务
    INFORMATION = "information"  # 信息提供类服务
    CLARIFICATION = "clarification"  # 澄清请求类服务


class ServicePriority(Enum):
    """服务优先级枚举。

    定义服务的优先级等级。
    """

    CRITICAL = "critical"  # 紧急
    HIGH = "high"  # 高
    MEDIUM = "medium"  # 中
    LOW = "low"  # 低
    BACKGROUND = "background"  # 后台


class ServiceStatus(Enum):
    """服务状态枚举。

    定义服务的执行状态。
    """

    PENDING = "pending"  # 待处理
    TRIGGERED = "triggered"  # 已触发
    EXECUTING = "executing"  # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消
    REJECTED = "rejected"  # 被拒绝


class FeedbackType(Enum):
    """反馈类型枚举。

    定义用户对服务的反馈类型。
    """

    ACCEPTED = "accepted"  # 接受
    REJECTED = "rejected"  # 拒绝
    IGNORED = "ignored"  # 忽略
    DEFERRED = "deferred"  # 延迟
    MODIFIED = "modified"  # 修改后接受


class ConflictResolution(Enum):
    """冲突解决策略枚举。

    定义服务冲突时的解决策略。
    """

    KEEP_FIRST = "keep_first"  # 保留第一个
    KEEP_LAST = "keep_last"  # 保留最后一个
    KEEP_HIGHEST_PRIORITY = "keep_highest_priority"  # 保留最高优先级
    MERGE = "merge"  # 合并执行
    CANCEL_BOTH = "cancel_both"  # 都取消


@dataclass
class ServiceDefinition:
    """服务定义数据类。

    定义一个主动服务的完整配置。
    """

    # 服务唯一标识
    service_id: str
    # 服务类型
    service_type: ServiceType
    # 服务名称
    name: str
    # 服务描述
    description: str
    # 服务优先级
    priority: ServicePriority
    # 触发条件列表
    trigger_conditions: List[str]
    # 冷却时间（秒），避免频繁触发
    cooldown_seconds: int = 300


@dataclass
class ServiceResult:
    """服务执行结果数据类。

    记录服务执行的结果信息。
    """

    # 服务唯一标识
    service_id: str
    # 执行状态
    status: ServiceStatus
    # 结果消息
    message: str
    # 结果数据
    data: Optional[Dict[str, Any]] = None
    # 执行时间
    executed_at: datetime = field(default_factory=datetime.now)
    # 执行耗时（毫秒）
    duration_ms: int = 0


@dataclass
class ServiceFeedback:
    """服务反馈数据类。

    记录用户对服务的反馈信息。
    """

    # 服务唯一标识
    service_id: str
    # 反馈类型
    feedback_type: FeedbackType
    # 用户评论
    user_comment: Optional[str] = None
    # 记录时间
    recorded_at: datetime = field(default_factory=datetime.now)


@dataclass
class TriggerContext:
    """触发上下文数据类。

    包含触发服务所需的上下文信息。
    """

    # 用户输入
    user_input: str
    # 对话历史
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    # 用户画像数据
    user_profile: Optional[Any] = None
    # 预测结果
    predictions: Optional[Dict[str, Any]] = None
    # 时间戳
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ExecutionPlan:
    """执行计划数据类。

    定义服务执行的计划信息。
    """

    # 服务定义列表
    services: List["ServiceDefinition"] = field(default_factory=list)
    # 执行顺序（service_id列表）
    execution_order: List[str] = field(default_factory=list)
    # 可并行执行的组（每组包含可同时执行的service_id）
    parallel_groups: List[List[str]] = field(default_factory=list)
    # 预估执行时间（毫秒）
    estimated_duration_ms: int = 0
    # 创建时间
    created_at: datetime = field(default_factory=datetime.now)


class ServiceHandlerProtocol(Protocol):
    """服务处理器协议。

    定义服务处理器的标准接口，支持依赖注入。
    """

    def handle(self, context: TriggerContext) -> ServiceResult:
        """处理服务请求。

        Args:
            context: 触发上下文

        Returns:
            服务执行结果
        """
        ...

    def can_handle(self, service_type: ServiceType) -> bool:
        """检查是否能处理指定类型的服务。

        Args:
            service_type: 服务类型

        Returns:
            是否能处理
        """
        ...


class TriggerEvaluatorProtocol(Protocol):
    """触发评估器协议。

    定义触发条件评估器的标准接口，支持依赖注入。
    """

    def evaluate(
        self,
        context: TriggerContext,
        conditions: List[str],
    ) -> bool:
        """评估触发条件。

        Args:
            context: 触发上下文
            conditions: 触发条件列表

        Returns:
            是否满足触发条件
        """
        ...

    def get_confidence(self, context: TriggerContext) -> float:
        """获取触发置信度。

        Args:
            context: 触发上下文

        Returns:
            置信度分数 (0-1)
        """
        ...
