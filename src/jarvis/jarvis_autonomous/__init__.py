"""Jarvis自主决策模块

本模块实现Jarvis的自主决策能力，包括：
- 目标管理：理解和跟踪用户的长期目标
- 计划制定：自主制定达成目标的计划
- 任务分解：将复杂目标分解为可执行任务
- 自主执行：在授权范围内自主执行任务

与现有task_list系统深度整合，复用task_list_manager的执行能力。
"""

from jarvis.jarvis_autonomous.goal_manager import (
    Goal,
    GoalManager,
    GoalPriority,
    GoalProgress,
    GoalStatus,
)
from jarvis.jarvis_autonomous.planning_engine import (
    Plan,
    PlanningEngine,
    PlanStatus,
    PlanTemplate,
)
from jarvis.jarvis_autonomous.task_decomposer import (
    DecomposedTask,
    TaskComplexity,
    TaskDecomposer,
)
from jarvis.jarvis_autonomous.autonomous_executor import (
    AuthorizationLevel,
    AutonomousExecutor,
    ExecutionContext,
    ExecutionResult,
    OperationRisk,
)

__all__ = [
    # 目标管理
    "Goal",
    "GoalManager",
    "GoalPriority",
    "GoalProgress",
    "GoalStatus",
    # 计划制定
    "Plan",
    "PlanningEngine",
    "PlanStatus",
    "PlanTemplate",
    # 任务分解
    "DecomposedTask",
    "TaskComplexity",
    "TaskDecomposer",
    # 自主执行
    "AuthorizationLevel",
    "AutonomousExecutor",
    "ExecutionContext",
    "ExecutionResult",
    "OperationRisk",
]
