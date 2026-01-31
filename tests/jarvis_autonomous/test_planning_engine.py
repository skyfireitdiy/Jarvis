"""计划制定引擎测试"""

import pytest

from jarvis.jarvis_autonomous.goal_manager import Goal
from jarvis.jarvis_autonomous.planning_engine import (
    Plan,
    PlanningEngine,
    PlanStatus,
    PlanTemplate,
)


class TestPlanTemplate:
    """PlanTemplate测试"""

    def test_template_creation(self) -> None:
        """测试模板创建"""
        template = PlanTemplate(
            name="测试模板",
            description="测试描述",
            steps=[
                {"name": "步骤1", "desc": "描述1"},
                {"name": "步骤2", "desc": "描述2"},
            ],
        )
        assert template.name == "测试模板"
        assert len(template.steps) == 2

    def test_template_to_dict(self) -> None:
        """测试模板转换为字典"""
        template = PlanTemplate(
            name="模板",
            description="描述",
            steps=[{"name": "步骤"}],
        )
        data = template.to_dict()
        assert data["name"] == "模板"
        assert len(data["steps"]) == 1


class TestPlan:
    """Plan测试"""

    def test_plan_creation(self) -> None:
        """测试计划创建"""
        plan = Plan(
            id="plan-1",
            goal_id="goal-1",
            name="测试计划",
            description="计划描述",
        )
        assert plan.id == "plan-1"
        assert plan.status == PlanStatus.DRAFT

    def test_plan_to_dict(self) -> None:
        """测试计划转换为字典"""
        plan = Plan(
            id="plan-1",
            goal_id="goal-1",
            name="计划",
            description="描述",
            status=PlanStatus.ACTIVE,
        )
        data = plan.to_dict()
        assert data["status"] == "active"

    def test_plan_from_dict(self) -> None:
        """测试从字典创建计划"""
        from datetime import datetime

        data = {
            "id": "plan-1",
            "goal_id": "goal-1",
            "name": "计划",
            "description": "描述",
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        plan = Plan.from_dict(data)
        assert plan.status == PlanStatus.ACTIVE


class TestPlanningEngine:
    """PlanningEngine测试"""

    @pytest.fixture
    def engine(self) -> PlanningEngine:
        """创建计划引擎"""
        return PlanningEngine()

    @pytest.fixture
    def sample_goal(self) -> Goal:
        """创建示例目标"""
        return Goal(
            id="goal-1",
            title="实现用户登录功能",
            description="实现一个完整的用户登录功能，包括表单验证和错误处理",
        )

    def test_create_plan(self, engine: PlanningEngine, sample_goal: Goal) -> None:
        """测试创建计划"""
        plan, task_list = engine.create_plan(sample_goal)
        assert plan.goal_id == sample_goal.id
        assert task_list.main_goal == sample_goal.title
        assert len(task_list.tasks) > 0

    def test_create_plan_with_template(
        self, engine: PlanningEngine, sample_goal: Goal
    ) -> None:
        """测试使用模板创建计划"""
        plan, task_list = engine.create_plan(
            sample_goal, template_name="software_development"
        )
        assert len(task_list.tasks) == 5  # software_development模板有5个步骤

    def test_create_plan_bug_fix(self, engine: PlanningEngine) -> None:
        """测试Bug修复计划"""
        goal = Goal(
            id="goal-2",
            title="修复登录bug",
            description="修复用户无法登录的问题",
        )
        plan, task_list = engine.create_plan(goal)
        # 应该自动选择bug_fix模板
        assert len(task_list.tasks) == 3

    def test_create_plan_refactoring(self, engine: PlanningEngine) -> None:
        """测试重构计划"""
        goal = Goal(
            id="goal-3",
            title="重构用户模块",
            description="重构用户模块，提高代码质量",
        )
        plan, task_list = engine.create_plan(goal)
        # 应该自动选择refactoring模板
        assert len(task_list.tasks) == 4

    def test_create_plan_research(self, engine: PlanningEngine) -> None:
        """测试研究计划"""
        goal = Goal(
            id="goal-4",
            title="技术调研",
            description="研究新的认证方案",
        )
        plan, task_list = engine.create_plan(goal)
        # 应该自动选择research模板
        assert len(task_list.tasks) == 4

    def test_get_plan(self, engine: PlanningEngine, sample_goal: Goal) -> None:
        """测试获取计划"""
        plan, _ = engine.create_plan(sample_goal)
        retrieved = engine.get_plan(plan.id)
        assert retrieved is not None
        assert retrieved.id == plan.id

    def test_get_plans_for_goal(
        self, engine: PlanningEngine, sample_goal: Goal
    ) -> None:
        """测试获取目标的所有计划"""
        engine.create_plan(sample_goal)
        engine.create_plan(sample_goal)  # 创建第二个计划
        plans = engine.get_plans_for_goal(sample_goal.id)
        assert len(plans) == 2

    def test_update_plan_status(
        self, engine: PlanningEngine, sample_goal: Goal
    ) -> None:
        """测试更新计划状态"""
        plan, _ = engine.create_plan(sample_goal)
        updated = engine.update_plan_status(plan.id, PlanStatus.ACTIVE)
        assert updated is not None
        assert updated.status == PlanStatus.ACTIVE

    def test_generate_tasks_info(
        self, engine: PlanningEngine, sample_goal: Goal
    ) -> None:
        """测试生成任务信息"""
        tasks_info = engine.generate_tasks_info(sample_goal)
        assert len(tasks_info) > 0
        # 验证格式兼容task_list_manager
        for task in tasks_info:
            assert "task_name" in task
            assert "task_desc" in task
            assert "expected_output" in task
            assert "agent_type" in task

    def test_get_available_templates(self, engine: PlanningEngine) -> None:
        """测试获取可用模板"""
        templates = engine.get_available_templates()
        assert len(templates) >= 4
        template_names = [t["name"] for t in templates]
        assert "software_development" in template_names
        assert "bug_fix" in template_names

    def test_task_dependencies(self, engine: PlanningEngine, sample_goal: Goal) -> None:
        """测试任务依赖关系"""
        _, task_list = engine.create_plan(sample_goal)
        tasks = list(task_list.tasks.values())
        # 第一个任务没有依赖
        assert len(tasks[0].dependencies) == 0
        # 后续任务依赖前一个任务
        for i in range(1, len(tasks)):
            assert len(tasks[i].dependencies) > 0
