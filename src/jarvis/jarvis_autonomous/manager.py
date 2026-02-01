"""自主能力管理器模块。

整合自主决策和创造性思维组件，提供统一的自主能力接口。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from jarvis.jarvis_autonomous.goal_manager import (
    Goal,
    GoalManager,
    GoalPriority,
    GoalProgress,
)
from jarvis.jarvis_autonomous.planning_engine import Plan, PlanningEngine
from jarvis.jarvis_autonomous.task_decomposer import DecomposedTask, TaskDecomposer
from jarvis.jarvis_autonomous.autonomous_executor import (
    AuthorizationLevel,
    AutonomousExecutor,
    ExecutionContext,
)
from jarvis.jarvis_autonomous.creativity import (
    CreativityEngine,
    SolutionDesigner,
    CodeInnovator,
    Idea,
    IdeaCategory,
    Solution,
    CodeInnovation,
    InnovationRequest,
    InnovationType,
)


class AutonomousManager:
    """自主能力管理器。

    整合目标管理、计划制定、任务分解、自主执行和创造性思维组件，
    提供统一的自主能力接口。
    """

    def __init__(
        self,
        goal_manager: Optional[GoalManager] = None,
        planning_engine: Optional[PlanningEngine] = None,
        task_decomposer: Optional[TaskDecomposer] = None,
        autonomous_executor: Optional[AutonomousExecutor] = None,
        creativity_engine: Optional[CreativityEngine] = None,
        solution_designer: Optional[SolutionDesigner] = None,
        code_innovator: Optional[CodeInnovator] = None,
    ) -> None:
        """初始化自主能力管理器。"""
        self._goal_manager = goal_manager or GoalManager()
        self._planning_engine = planning_engine or PlanningEngine()
        self._task_decomposer = task_decomposer or TaskDecomposer()
        self._autonomous_executor = autonomous_executor or AutonomousExecutor()
        self._creativity_engine = creativity_engine or CreativityEngine()
        self._solution_designer = solution_designer or SolutionDesigner()
        self._code_innovator = code_innovator or CodeInnovator()

        self._enabled = True
        self._action_history: List[Dict[str, Any]] = []

    @property
    def enabled(self) -> bool:
        """获取管理器启用状态。"""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """设置管理器启用状态。"""
        self._enabled = value

    @property
    def goal_manager(self) -> GoalManager:
        """获取目标管理器。"""
        return self._goal_manager

    @property
    def planning_engine(self) -> PlanningEngine:
        """获取计划制定引擎。"""
        return self._planning_engine

    @property
    def task_decomposer(self) -> TaskDecomposer:
        """获取任务分解器。"""
        return self._task_decomposer

    @property
    def autonomous_executor(self) -> AutonomousExecutor:
        """获取自主执行器。"""
        return self._autonomous_executor

    @property
    def creativity_engine(self) -> CreativityEngine:
        """获取创意生成引擎。"""
        return self._creativity_engine

    @property
    def solution_designer(self) -> SolutionDesigner:
        """获取方案设计器。"""
        return self._solution_designer

    @property
    def code_innovator(self) -> CodeInnovator:
        """获取代码创新器。"""
        return self._code_innovator

    # ==================== 目标管理 ====================

    def extract_goal_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """从文本中提取目标信息。"""
        if not self._enabled:
            return None

        result = self._goal_manager.extract_goal_from_text(text)
        if result:
            self._record_action("extract_goal_from_text", {"text": text[:100]})
        return result

    def create_goal(
        self,
        title: str,
        description: str,
        priority: GoalPriority = GoalPriority.MEDIUM,
        tags: Optional[List[str]] = None,
    ) -> Goal:
        """创建新目标。"""
        goal = self._goal_manager.create_goal(
            title=title,
            description=description,
            priority=priority,
            tags=tags or [],
        )
        self._record_action("create_goal", {"title": title})
        return goal

    def get_active_goals(self) -> List[Goal]:
        """获取所有活跃目标。"""
        return self._goal_manager.get_active_goals()

    def update_goal_progress(
        self,
        goal_id: str,
        progress_percentage: float,
        completed_tasks: int,
        total_tasks: int,
        notes: str = "",
    ) -> Optional[GoalProgress]:
        """更新目标进度。"""
        return self._goal_manager.update_progress(
            goal_id, progress_percentage, completed_tasks, total_tasks, notes
        )

    # ==================== 计划制定 ====================

    def create_plan(self, goal: Goal, template_name: Optional[str] = None) -> Plan:
        """为目标创建执行计划。返回Plan对象。"""
        plan, _ = self._planning_engine.create_plan(goal, template_name)
        self._record_action("create_plan", {"goal": goal.title, "plan": plan.name})
        return plan

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        """获取计划。"""
        return self._planning_engine.get_plan(plan_id)

    def get_plans_for_goal(self, goal_id: str) -> List[Plan]:
        """获取目标的所有计划。"""
        return self._planning_engine.get_plans_for_goal(goal_id)

    # ==================== 任务分解 ====================

    def decompose_task(self, goal: Goal) -> List[DecomposedTask]:
        """分解目标为子任务。"""
        if not self._enabled:
            return []

        tasks = self._task_decomposer.decompose(goal)
        if tasks:
            self._record_action(
                "decompose_task", {"goal": goal.title, "subtasks": len(tasks)}
            )
        return tasks

    def analyze_complexity(self, goal: Goal) -> Any:
        """分析目标复杂度。"""
        return self._task_decomposer.analyze_complexity(goal)

    # ==================== 自主执行 ====================

    def can_execute_autonomously(
        self, operation: str, context: Optional[ExecutionContext] = None
    ) -> Tuple[bool, str]:
        """判断是否可以自主执行操作。返回(是否可执行, 原因)。"""
        if not self._enabled:
            return False, "自主能力管理器未启用"

        if context is None:
            context = self._autonomous_executor.create_execution_context(
                task_id="auto",
                task_name=operation,
                task_description=operation,
            )
        return self._autonomous_executor.can_execute_autonomously(operation, context)

    def should_ask_confirmation(
        self, operation: str, context: Optional[ExecutionContext] = None
    ) -> Tuple[bool, str]:
        """判断是否需要请求确认。返回(是否需要确认, 原因)。"""
        if context is None:
            context = self._autonomous_executor.create_execution_context(
                task_id="auto",
                task_name=operation,
                task_description=operation,
            )
        return self._autonomous_executor.should_ask_confirmation(operation, context)

    def get_authorization_level(self) -> AuthorizationLevel:
        """获取当前授权级别。"""
        return self._autonomous_executor.default_authorization

    def set_authorization_level(self, level: AuthorizationLevel) -> None:
        """设置授权级别。"""
        self._autonomous_executor.default_authorization = level

    # ==================== 创造性思维 ====================

    def generate_ideas(
        self, context: str, category: Optional[IdeaCategory] = None, max_ideas: int = 5
    ) -> List[Idea]:
        """生成创意想法。"""
        if not self._enabled:
            return []

        ideas = self._creativity_engine.generate_ideas(context, category, max_ideas)
        if ideas:
            self._record_action(
                "generate_ideas", {"context": context[:50], "count": len(ideas)}
            )
        return ideas

    def design_solutions(
        self,
        problem: str,
        constraints: Optional[List[str]] = None,
        max_solutions: int = 3,
    ) -> List[Solution]:
        """设计解决方案。"""
        if not self._enabled:
            return []

        solutions = self._solution_designer.generate_solutions(
            problem, constraints, max_solutions
        )
        if solutions:
            self._record_action(
                "design_solutions", {"problem": problem[:50], "count": len(solutions)}
            )
        return solutions

    def suggest_code_innovations(
        self, code: str, language: str = "python", innovation_type: str = "optimization"
    ) -> CodeInnovation:
        """建议代码创新。"""
        if not self._enabled:
            return CodeInnovation(
                id="",
                innovation_type=InnovationType.OPTIMIZATION,
                title="",
                description="",
                original_code="",
                suggested_code="",
                benefits=[],
                risks=[],
            )

        # 将字符串转换为InnovationType枚举
        try:
            inno_type = InnovationType(innovation_type)
        except ValueError:
            inno_type = InnovationType.OPTIMIZATION

        request = InnovationRequest(
            code=code,
            context=f"language: {language}",
            innovation_type=inno_type,
        )
        innovation = self._code_innovator.innovate(request)
        self._record_action(
            "suggest_code_innovations", {"language": language, "type": innovation_type}
        )
        return innovation

    # ==================== 综合能力 ====================

    def process_user_input(self, user_input: str, context: str = "") -> Dict[str, Any]:
        """处理用户输入，提取目标和意图。"""
        if not self._enabled:
            return {"enabled": False}

        result: Dict[str, Any] = {
            "enabled": True,
            "goal_info": None,
            "timestamp": datetime.now().isoformat(),
        }

        goal_info = self.extract_goal_from_text(user_input)
        if goal_info:
            result["goal_info"] = goal_info

        return result

    def get_statistics(self) -> Dict[str, Any]:
        """获取自主能力统计信息。"""
        return {
            "enabled": self._enabled,
            "action_count": len(self._action_history),
            "active_goals": len(self.get_active_goals()),
            "authorization_level": self.get_authorization_level().value,
            "components": {
                "goal_manager": True,
                "planning_engine": True,
                "task_decomposer": True,
                "autonomous_executor": True,
                "creativity_engine": True,
                "solution_designer": True,
                "code_innovator": True,
            },
        }

    def _record_action(self, action_type: str, details: Dict[str, Any]) -> None:
        """记录操作历史。"""
        self._action_history.append(
            {
                "type": action_type,
                "details": details,
                "timestamp": datetime.now().isoformat(),
            }
        )

        if len(self._action_history) > 1000:
            self._action_history = self._action_history[-500:]
