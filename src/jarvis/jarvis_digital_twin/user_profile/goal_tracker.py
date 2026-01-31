"""目标追踪器模块

追踪用户的短期、中期、长期目标，支持从对话中自动识别目标。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class GoalType(Enum):
    """目标类型枚举"""

    SHORT_TERM = "short_term"  # 短期目标（天/周级别）
    MEDIUM_TERM = "medium_term"  # 中期目标（月级别）
    LONG_TERM = "long_term"  # 长期目标（季度/年级别）


class GoalStatus(Enum):
    """目标状态枚举"""

    ACTIVE = "active"  # 活跃中
    COMPLETED = "completed"  # 已完成
    PAUSED = "paused"  # 已暂停
    ABANDONED = "abandoned"  # 已放弃


@dataclass
class GoalProgress:
    """目标进度数据类

    记录目标的完成进度信息。
    """

    percentage: float = 0.0  # 完成百分比 0-100
    completed_milestones: int = 0  # 已完成里程碑数
    total_milestones: int = 0  # 总里程碑数
    last_activity: str = ""  # 最后活动描述
    last_updated: str = ""  # 最后更新时间

    def update(self, milestone_completed: bool = False) -> None:
        """更新进度

        Args:
            milestone_completed: 是否完成了一个里程碑
        """
        if milestone_completed and self.total_milestones > 0:
            self.completed_milestones = min(
                self.completed_milestones + 1, self.total_milestones
            )
            self.percentage = (self.completed_milestones / self.total_milestones) * 100
        self.last_updated = datetime.now().isoformat()


@dataclass
class TrackedGoal:
    """追踪目标数据类

    记录用户的目标信息，包括类型、描述、进度和置信度。
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    goal_type: GoalType = GoalType.SHORT_TERM
    description: str = ""
    progress: GoalProgress = field(default_factory=GoalProgress)
    confidence: float = 0.5  # 目标识别置信度 0-1
    status: GoalStatus = GoalStatus.ACTIVE
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = ""  # 目标来源（如：对话、显式设置）
    context: Dict[str, Any] = field(default_factory=dict)  # 额外上下文
    tags: List[str] = field(default_factory=list)  # 标签
    parent_goal_id: Optional[str] = None  # 父目标ID
    sub_goal_ids: List[str] = field(default_factory=list)  # 子目标ID列表

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典

        Returns:
            目标的字典表示
        """
        return {
            "id": self.id,
            "goal_type": self.goal_type.value,
            "description": self.description,
            "progress": {
                "percentage": self.progress.percentage,
                "completed_milestones": self.progress.completed_milestones,
                "total_milestones": self.progress.total_milestones,
                "last_activity": self.progress.last_activity,
                "last_updated": self.progress.last_updated,
            },
            "confidence": self.confidence,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source": self.source,
            "context": self.context,
            "tags": self.tags,
            "parent_goal_id": self.parent_goal_id,
            "sub_goal_ids": self.sub_goal_ids,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrackedGoal":
        """从字典创建目标

        Args:
            data: 目标数据字典

        Returns:
            TrackedGoal实例
        """
        progress_data = data.get("progress", {})
        progress = GoalProgress(
            percentage=progress_data.get("percentage", 0.0),
            completed_milestones=progress_data.get("completed_milestones", 0),
            total_milestones=progress_data.get("total_milestones", 0),
            last_activity=progress_data.get("last_activity", ""),
            last_updated=progress_data.get("last_updated", ""),
        )
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            goal_type=GoalType(data.get("goal_type", "short_term")),
            description=data.get("description", ""),
            progress=progress,
            confidence=data.get("confidence", 0.5),
            status=GoalStatus(data.get("status", "active")),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            source=data.get("source", ""),
            context=data.get("context", {}),
            tags=data.get("tags", []),
            parent_goal_id=data.get("parent_goal_id"),
            sub_goal_ids=data.get("sub_goal_ids", []),
        )


@dataclass
class GoalInferenceResult:
    """目标推断结果数据类

    记录从上下文中推断出的目标信息。
    """

    inferred_goals: List[TrackedGoal] = field(default_factory=list)
    context_analyzed: str = ""
    inference_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    confidence_threshold: float = 0.5


class GoalTracker:
    """目标追踪器

    追踪用户的短期、中期、长期目标，支持从对话中自动识别目标。
    """

    # 目标类型关键词映射
    GOAL_TYPE_KEYWORDS: Dict[GoalType, List[str]] = {
        GoalType.SHORT_TERM: [
            "今天",
            "明天",
            "这周",
            "本周",
            "马上",
            "立即",
            "尽快",
            "today",
            "tomorrow",
            "this week",
            "asap",
            "soon",
        ],
        GoalType.MEDIUM_TERM: [
            "这个月",
            "本月",
            "下个月",
            "几周内",
            "this month",
            "next month",
            "in weeks",
        ],
        GoalType.LONG_TERM: [
            "今年",
            "明年",
            "长期",
            "未来",
            "最终",
            "this year",
            "next year",
            "long term",
            "eventually",
            "future",
        ],
    }

    # 目标意图关键词
    GOAL_INTENT_KEYWORDS: List[str] = [
        "想要",
        "需要",
        "计划",
        "打算",
        "目标",
        "希望",
        "准备",
        "要做",
        "want to",
        "need to",
        "plan to",
        "going to",
        "goal is",
        "hope to",
        "intend to",
        "aim to",
    ]

    def __init__(self) -> None:
        """初始化目标追踪器"""
        self._goals: Dict[str, TrackedGoal] = {}
        self._goal_history: List[Dict[str, Any]] = []

    def track_goal(
        self,
        description: str,
        goal_type: GoalType = GoalType.SHORT_TERM,
        confidence: float = 1.0,
        source: str = "explicit",
        context: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        total_milestones: int = 0,
        parent_goal_id: Optional[str] = None,
    ) -> TrackedGoal:
        """追踪一个新目标

        Args:
            description: 目标描述
            goal_type: 目标类型
            confidence: 置信度
            source: 目标来源
            context: 额外上下文
            tags: 标签列表
            total_milestones: 总里程碑数
            parent_goal_id: 父目标ID

        Returns:
            创建的TrackedGoal实例
        """
        progress = GoalProgress(
            total_milestones=total_milestones,
            last_updated=datetime.now().isoformat(),
        )

        goal = TrackedGoal(
            goal_type=goal_type,
            description=description,
            progress=progress,
            confidence=confidence,
            source=source,
            context=context or {},
            tags=tags or [],
            parent_goal_id=parent_goal_id,
        )

        self._goals[goal.id] = goal

        # 如果有父目标，更新父目标的子目标列表
        if parent_goal_id and parent_goal_id in self._goals:
            self._goals[parent_goal_id].sub_goal_ids.append(goal.id)

        # 记录历史
        self._goal_history.append(
            {
                "action": "track",
                "goal_id": goal.id,
                "timestamp": datetime.now().isoformat(),
            }
        )

        return goal

    def infer_goals_from_context(
        self,
        context: str,
        confidence_threshold: float = 0.5,
    ) -> GoalInferenceResult:
        """从上下文中推断目标

        Args:
            context: 对话或文本上下文
            confidence_threshold: 置信度阈值

        Returns:
            GoalInferenceResult实例
        """
        inferred_goals: List[TrackedGoal] = []
        context_lower = context.lower()

        # 检查是否包含目标意图关键词
        has_intent = any(
            keyword in context_lower for keyword in self.GOAL_INTENT_KEYWORDS
        )

        if not has_intent:
            return GoalInferenceResult(
                inferred_goals=[],
                context_analyzed=context,
                confidence_threshold=confidence_threshold,
            )

        # 推断目标类型
        inferred_type = self._infer_goal_type(context_lower)

        # 计算置信度
        confidence = self._calculate_confidence(context_lower)

        if confidence >= confidence_threshold:
            # 提取目标描述
            description = self._extract_goal_description(context)

            goal = self.track_goal(
                description=description,
                goal_type=inferred_type,
                confidence=confidence,
                source="inferred",
                context={"original_context": context},
            )
            inferred_goals.append(goal)

        return GoalInferenceResult(
            inferred_goals=inferred_goals,
            context_analyzed=context,
            confidence_threshold=confidence_threshold,
        )

    def get_current_goals(
        self,
        goal_type: Optional[GoalType] = None,
        status: Optional[GoalStatus] = None,
        min_confidence: float = 0.0,
    ) -> List[TrackedGoal]:
        """获取当前目标列表

        Args:
            goal_type: 过滤目标类型
            status: 过滤目标状态
            min_confidence: 最小置信度

        Returns:
            符合条件的目标列表
        """
        goals = list(self._goals.values())

        if goal_type is not None:
            goals = [g for g in goals if g.goal_type == goal_type]

        if status is not None:
            goals = [g for g in goals if g.status == status]

        goals = [g for g in goals if g.confidence >= min_confidence]

        # 按创建时间排序
        goals.sort(key=lambda g: g.created_at, reverse=True)

        return goals

    def update_goal_progress(
        self,
        goal_id: str,
        milestone_completed: bool = False,
        new_percentage: Optional[float] = None,
        activity_description: str = "",
    ) -> Optional[TrackedGoal]:
        """更新目标进度

        Args:
            goal_id: 目标ID
            milestone_completed: 是否完成了一个里程碑
            new_percentage: 新的完成百分比
            activity_description: 活动描述

        Returns:
            更新后的目标，如果目标不存在则返回None
        """
        if goal_id not in self._goals:
            return None

        goal = self._goals[goal_id]

        if milestone_completed:
            goal.progress.update(milestone_completed=True)

        if new_percentage is not None:
            goal.progress.percentage = max(0.0, min(100.0, new_percentage))

        if activity_description:
            goal.progress.last_activity = activity_description

        goal.progress.last_updated = datetime.now().isoformat()
        goal.updated_at = datetime.now().isoformat()

        # 检查是否完成
        if goal.progress.percentage >= 100.0:
            goal.status = GoalStatus.COMPLETED

        # 记录历史
        self._goal_history.append(
            {
                "action": "update_progress",
                "goal_id": goal_id,
                "timestamp": datetime.now().isoformat(),
                "milestone_completed": milestone_completed,
                "new_percentage": new_percentage,
            }
        )

        return goal

    def get_goal_by_id(self, goal_id: str) -> Optional[TrackedGoal]:
        """根据ID获取目标

        Args:
            goal_id: 目标ID

        Returns:
            目标实例，如果不存在则返回None
        """
        return self._goals.get(goal_id)

    def update_goal_status(
        self, goal_id: str, new_status: GoalStatus
    ) -> Optional[TrackedGoal]:
        """更新目标状态

        Args:
            goal_id: 目标ID
            new_status: 新状态

        Returns:
            更新后的目标，如果目标不存在则返回None
        """
        if goal_id not in self._goals:
            return None

        goal = self._goals[goal_id]
        goal.status = new_status
        goal.updated_at = datetime.now().isoformat()

        # 记录历史
        self._goal_history.append(
            {
                "action": "update_status",
                "goal_id": goal_id,
                "timestamp": datetime.now().isoformat(),
                "new_status": new_status.value,
            }
        )

        return goal

    def remove_goal(self, goal_id: str) -> bool:
        """移除目标

        Args:
            goal_id: 目标ID

        Returns:
            是否成功移除
        """
        if goal_id not in self._goals:
            return False

        goal = self._goals[goal_id]

        # 从父目标的子目标列表中移除
        if goal.parent_goal_id and goal.parent_goal_id in self._goals:
            parent = self._goals[goal.parent_goal_id]
            if goal_id in parent.sub_goal_ids:
                parent.sub_goal_ids.remove(goal_id)

        # 处理子目标
        for sub_id in goal.sub_goal_ids:
            if sub_id in self._goals:
                self._goals[sub_id].parent_goal_id = None

        del self._goals[goal_id]

        # 记录历史
        self._goal_history.append(
            {
                "action": "remove",
                "goal_id": goal_id,
                "timestamp": datetime.now().isoformat(),
            }
        )

        return True

    def get_goals_by_tag(self, tag: str) -> List[TrackedGoal]:
        """根据标签获取目标

        Args:
            tag: 标签

        Returns:
            包含该标签的目标列表
        """
        return [g for g in self._goals.values() if tag in g.tags]

    def get_sub_goals(self, parent_goal_id: str) -> List[TrackedGoal]:
        """获取子目标列表

        Args:
            parent_goal_id: 父目标ID

        Returns:
            子目标列表
        """
        if parent_goal_id not in self._goals:
            return []

        parent = self._goals[parent_goal_id]
        return [
            self._goals[sub_id]
            for sub_id in parent.sub_goal_ids
            if sub_id in self._goals
        ]

    def get_goal_statistics(self) -> Dict[str, Any]:
        """获取目标统计信息

        Returns:
            统计信息字典
        """
        goals = list(self._goals.values())

        if not goals:
            return {
                "total_goals": 0,
                "by_type": {},
                "by_status": {},
                "average_confidence": 0.0,
                "average_progress": 0.0,
            }

        by_type: Dict[str, int] = {}
        by_status: Dict[str, int] = {}

        for goal in goals:
            type_key = goal.goal_type.value
            status_key = goal.status.value

            by_type[type_key] = by_type.get(type_key, 0) + 1
            by_status[status_key] = by_status.get(status_key, 0) + 1

        avg_confidence = sum(g.confidence for g in goals) / len(goals)
        avg_progress = sum(g.progress.percentage for g in goals) / len(goals)

        return {
            "total_goals": len(goals),
            "by_type": by_type,
            "by_status": by_status,
            "average_confidence": round(avg_confidence, 2),
            "average_progress": round(avg_progress, 2),
        }

    def get_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取目标操作历史

        Args:
            limit: 返回的最大记录数

        Returns:
            历史记录列表
        """
        history = self._goal_history.copy()
        history.reverse()  # 最新的在前

        if limit is not None:
            history = history[:limit]

        return history

    def clear_all_goals(self) -> int:
        """清除所有目标

        Returns:
            清除的目标数量
        """
        count = len(self._goals)
        self._goals.clear()

        # 记录历史
        self._goal_history.append(
            {
                "action": "clear_all",
                "timestamp": datetime.now().isoformat(),
                "count": count,
            }
        )

        return count

    def _infer_goal_type(self, context: str) -> GoalType:
        """从上下文推断目标类型

        Args:
            context: 小写的上下文文本

        Returns:
            推断的目标类型
        """
        # 检查长期目标关键词
        for keyword in self.GOAL_TYPE_KEYWORDS[GoalType.LONG_TERM]:
            if keyword in context:
                return GoalType.LONG_TERM

        # 检查中期目标关键词
        for keyword in self.GOAL_TYPE_KEYWORDS[GoalType.MEDIUM_TERM]:
            if keyword in context:
                return GoalType.MEDIUM_TERM

        # 检查短期目标关键词
        for keyword in self.GOAL_TYPE_KEYWORDS[GoalType.SHORT_TERM]:
            if keyword in context:
                return GoalType.SHORT_TERM

        # 默认为短期目标
        return GoalType.SHORT_TERM

    def _calculate_confidence(self, context: str) -> float:
        """计算目标识别置信度

        Args:
            context: 小写的上下文文本

        Returns:
            置信度值 0-1
        """
        confidence = 0.3  # 基础置信度

        # 检查意图关键词数量
        intent_count = sum(
            1 for keyword in self.GOAL_INTENT_KEYWORDS if keyword in context
        )
        confidence += min(intent_count * 0.15, 0.45)

        # 检查时间关键词
        has_time_keyword = any(
            keyword in context
            for keywords in self.GOAL_TYPE_KEYWORDS.values()
            for keyword in keywords
        )
        if has_time_keyword:
            confidence += 0.15

        # 检查上下文长度（较长的上下文可能更明确）
        if len(context) > 50:
            confidence += 0.1

        return min(confidence, 1.0)

    def _extract_goal_description(self, context: str) -> str:
        """从上下文提取目标描述

        Args:
            context: 原始上下文文本

        Returns:
            提取的目标描述
        """
        # 简单实现：返回整个上下文作为描述
        # 实际应用中可以使用更复杂的NLP技术
        description = context.strip()

        # 限制长度
        max_length = 200
        if len(description) > max_length:
            description = description[:max_length] + "..."

        return description
