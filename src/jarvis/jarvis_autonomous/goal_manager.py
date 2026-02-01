"""目标管理器模块

负责理解、存储和跟踪用户的长期目标。
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from jarvis.jarvis_utils.output import PrettyOutput


class GoalStatus(Enum):
    """目标状态枚举"""

    ACTIVE = "active"  # 活跃中
    COMPLETED = "completed"  # 已完成
    PAUSED = "paused"  # 已暂停
    ABANDONED = "abandoned"  # 已放弃


class GoalPriority(Enum):
    """目标优先级枚举"""

    CRITICAL = "critical"  # 关键
    HIGH = "high"  # 高
    MEDIUM = "medium"  # 中
    LOW = "low"  # 低


@dataclass
class GoalProgress:
    """目标进度"""

    goal_id: str
    progress_percentage: float  # 0-100
    completed_tasks: int
    total_tasks: int
    last_updated: datetime = field(default_factory=datetime.now)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "goal_id": self.goal_id,
            "progress_percentage": self.progress_percentage,
            "completed_tasks": self.completed_tasks,
            "total_tasks": self.total_tasks,
            "last_updated": self.last_updated.isoformat(),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoalProgress":
        """从字典创建"""
        return cls(
            goal_id=data["goal_id"],
            progress_percentage=data["progress_percentage"],
            completed_tasks=data["completed_tasks"],
            total_tasks=data["total_tasks"],
            last_updated=datetime.fromisoformat(data["last_updated"]),
            notes=data.get("notes", ""),
        )


@dataclass
class Goal:
    """用户目标

    表示用户的一个长期目标，包含目标描述、优先级、状态等信息。
    """

    id: str
    title: str  # 目标标题
    description: str  # 目标详细描述
    priority: GoalPriority = GoalPriority.MEDIUM
    status: GoalStatus = GoalStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    deadline: Optional[datetime] = None  # 截止日期
    tags: list[str] = field(default_factory=list)  # 标签
    parent_goal_id: Optional[str] = None  # 父目标ID（支持目标层级）
    sub_goal_ids: list[str] = field(default_factory=list)  # 子目标ID列表
    context: dict[str, Any] = field(default_factory=dict)  # 额外上下文信息
    progress: Optional[GoalProgress] = None  # 进度信息

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "tags": self.tags,
            "parent_goal_id": self.parent_goal_id,
            "sub_goal_ids": self.sub_goal_ids,
            "context": self.context,
            "progress": self.progress.to_dict() if self.progress else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Goal":
        """从字典创建"""
        progress_data = data.get("progress")
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            priority=GoalPriority(data.get("priority", "medium")),
            status=GoalStatus(data.get("status", "active")),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            deadline=(
                datetime.fromisoformat(data["deadline"])
                if data.get("deadline")
                else None
            ),
            tags=data.get("tags", []),
            parent_goal_id=data.get("parent_goal_id"),
            sub_goal_ids=data.get("sub_goal_ids", []),
            context=data.get("context", {}),
            progress=GoalProgress.from_dict(progress_data) if progress_data else None,
        )


class GoalManager:
    """目标管理器

    负责理解、存储和跟踪用户的长期目标。
    支持目标的CRUD操作、进度跟踪、目标层级管理等功能。
    """

    def __init__(self, storage_dir: Optional[str] = None):
        """初始化目标管理器

        Args:
            storage_dir: 目标存储目录，默认为 .jarvis/goals/
        """
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = Path.cwd() / ".jarvis" / "goals"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.goals: dict[str, Goal] = {}
        self._load_goals()

    def _load_goals(self) -> None:
        """从存储加载所有目标"""
        goals_file = self.storage_dir / "goals.json"
        if goals_file.exists():
            try:
                with open(goals_file, encoding="utf-8") as f:
                    data = json.load(f)
                    for goal_data in data.get("goals", []):
                        goal = Goal.from_dict(goal_data)
                        self.goals[goal.id] = goal
            except (json.JSONDecodeError, KeyError) as e:
                # 文件损坏或格式错误，从空开始
                PrettyOutput.auto_print(f"⚠️ 警告: 加载目标失败: {e}")
                self.goals = {}

    def _save_goals(self) -> None:
        """保存所有目标到存储"""
        goals_file = self.storage_dir / "goals.json"
        data = {"goals": [goal.to_dict() for goal in self.goals.values()]}
        with open(goals_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def create_goal(
        self,
        title: str,
        description: str,
        priority: GoalPriority = GoalPriority.MEDIUM,
        deadline: Optional[datetime] = None,
        tags: Optional[list[str]] = None,
        parent_goal_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> Goal:
        """创建新目标

        Args:
            title: 目标标题
            description: 目标描述
            priority: 优先级
            deadline: 截止日期
            tags: 标签列表
            parent_goal_id: 父目标ID
            context: 额外上下文

        Returns:
            创建的目标对象
        """
        goal_id = str(uuid.uuid4())
        goal = Goal(
            id=goal_id,
            title=title,
            description=description,
            priority=priority,
            deadline=deadline,
            tags=tags or [],
            parent_goal_id=parent_goal_id,
            context=context or {},
        )

        # 如果有父目标，更新父目标的子目标列表
        if parent_goal_id and parent_goal_id in self.goals:
            self.goals[parent_goal_id].sub_goal_ids.append(goal_id)

        self.goals[goal_id] = goal
        self._save_goals()
        return goal

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """获取目标

        Args:
            goal_id: 目标ID

        Returns:
            目标对象，不存在则返回None
        """
        return self.goals.get(goal_id)

    def update_goal(
        self,
        goal_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[GoalPriority] = None,
        status: Optional[GoalStatus] = None,
        deadline: Optional[datetime] = None,
        tags: Optional[list[str]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[Goal]:
        """更新目标

        Args:
            goal_id: 目标ID
            其他参数: 要更新的字段

        Returns:
            更新后的目标对象，不存在则返回None
        """
        goal = self.goals.get(goal_id)
        if not goal:
            return None

        if title is not None:
            goal.title = title
        if description is not None:
            goal.description = description
        if priority is not None:
            goal.priority = priority
        if status is not None:
            goal.status = status
        if deadline is not None:
            goal.deadline = deadline
        if tags is not None:
            goal.tags = tags
        if context is not None:
            goal.context.update(context)

        goal.updated_at = datetime.now()
        self._save_goals()
        return goal

    def delete_goal(self, goal_id: str) -> bool:
        """删除目标

        Args:
            goal_id: 目标ID

        Returns:
            是否删除成功
        """
        if goal_id not in self.goals:
            return False

        goal = self.goals[goal_id]

        # 从父目标的子目标列表中移除
        if goal.parent_goal_id and goal.parent_goal_id in self.goals:
            parent = self.goals[goal.parent_goal_id]
            if goal_id in parent.sub_goal_ids:
                parent.sub_goal_ids.remove(goal_id)

        # 递归删除子目标
        for sub_goal_id in goal.sub_goal_ids:
            self.delete_goal(sub_goal_id)

        del self.goals[goal_id]
        self._save_goals()
        return True

    def list_goals(
        self,
        status: Optional[GoalStatus] = None,
        priority: Optional[GoalPriority] = None,
        tags: Optional[list[str]] = None,
        parent_goal_id: Optional[str] = None,
    ) -> list[Goal]:
        """列出目标

        Args:
            status: 按状态过滤
            priority: 按优先级过滤
            tags: 按标签过滤（包含任一标签）
            parent_goal_id: 按父目标过滤

        Returns:
            符合条件的目标列表
        """
        result = list(self.goals.values())

        if status is not None:
            result = [g for g in result if g.status == status]
        if priority is not None:
            result = [g for g in result if g.priority == priority]
        if tags:
            result = [g for g in result if any(t in g.tags for t in tags)]
        if parent_goal_id is not None:
            result = [g for g in result if g.parent_goal_id == parent_goal_id]

        return result

    def update_progress(
        self,
        goal_id: str,
        progress_percentage: float,
        completed_tasks: int,
        total_tasks: int,
        notes: str = "",
    ) -> Optional[GoalProgress]:
        """更新目标进度

        Args:
            goal_id: 目标ID
            progress_percentage: 进度百分比 (0-100)
            completed_tasks: 已完成任务数
            total_tasks: 总任务数
            notes: 进度备注

        Returns:
            更新后的进度对象，目标不存在则返回None
        """
        goal = self.goals.get(goal_id)
        if not goal:
            return None

        progress = GoalProgress(
            goal_id=goal_id,
            progress_percentage=min(100, max(0, progress_percentage)),
            completed_tasks=completed_tasks,
            total_tasks=total_tasks,
            notes=notes,
        )
        goal.progress = progress
        goal.updated_at = datetime.now()

        # 如果进度达到100%，自动标记为完成
        if progress_percentage >= 100:
            goal.status = GoalStatus.COMPLETED

        self._save_goals()
        return progress

    def get_active_goals(self) -> list[Goal]:
        """获取所有活跃目标

        Returns:
            活跃目标列表，按优先级排序
        """
        active_goals = self.list_goals(status=GoalStatus.ACTIVE)
        # 按优先级排序
        priority_order = {
            GoalPriority.CRITICAL: 0,
            GoalPriority.HIGH: 1,
            GoalPriority.MEDIUM: 2,
            GoalPriority.LOW: 3,
        }
        return sorted(active_goals, key=lambda g: priority_order[g.priority])

    def get_goal_hierarchy(self, goal_id: str) -> dict[str, Any]:
        """获取目标层级结构

        Args:
            goal_id: 目标ID

        Returns:
            目标及其子目标的层级结构
        """
        goal = self.goals.get(goal_id)
        if not goal:
            return {}

        result = goal.to_dict()
        result["sub_goals"] = [
            self.get_goal_hierarchy(sub_id) for sub_id in goal.sub_goal_ids
        ]
        return result

    def extract_goal_from_text(self, text: str) -> Optional[dict[str, Any]]:
        """从文本中提取目标信息

        这是一个简单的实现，后续可以集成LLM进行更智能的提取。

        Args:
            text: 用户输入的文本

        Returns:
            提取的目标信息字典，包含title和description
        """
        # 简单的关键词匹配
        goal_keywords = [
            "我想",
            "我要",
            "我希望",
            "目标是",
            "计划",
            "打算",
            "需要完成",
            "想要实现",
        ]

        for keyword in goal_keywords:
            if keyword in text:
                # 提取关键词后的内容作为目标描述
                idx = text.find(keyword)
                description = text[idx:].strip()
                # 简单地将前50个字符作为标题
                title = description[:50].replace("\n", " ")
                if len(description) > 50:
                    title += "..."
                return {
                    "title": title,
                    "description": description,
                    "source_text": text,
                }

        return None

    def suggest_next_actions(self, goal_id: str) -> list[str]:
        """建议下一步行动

        Args:
            goal_id: 目标ID

        Returns:
            建议的行动列表
        """
        goal = self.goals.get(goal_id)
        if not goal:
            return []

        suggestions = []

        # 基于目标状态给出建议
        if goal.status == GoalStatus.ACTIVE:
            if not goal.progress:
                suggestions.append("开始规划目标的具体任务")
                suggestions.append("设定目标的截止日期")
            elif goal.progress.progress_percentage < 50:
                suggestions.append("继续推进当前任务")
                suggestions.append("检查是否有阻塞问题")
            else:
                suggestions.append("保持当前进度")
                suggestions.append("准备目标完成的验收")

        elif goal.status == GoalStatus.PAUSED:
            suggestions.append("评估是否继续该目标")
            suggestions.append("分析暂停的原因")

        # 基于子目标给出建议
        if goal.sub_goal_ids:
            incomplete_subs = [
                self.goals[sid]
                for sid in goal.sub_goal_ids
                if sid in self.goals and self.goals[sid].status != GoalStatus.COMPLETED
            ]
            if incomplete_subs:
                suggestions.append(f"完成子目标: {incomplete_subs[0].title}")

        return suggestions
