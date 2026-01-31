"""任务分解器测试"""

import pytest

from jarvis.jarvis_autonomous.goal_manager import Goal
from jarvis.jarvis_autonomous.task_decomposer import (
    DecomposedTask,
    TaskComplexity,
    TaskDecomposer,
)


class TestDecomposedTask:
    """DecomposedTask测试"""

    def test_task_creation(self) -> None:
        """测试任务创建"""
        task = DecomposedTask(
            name="测试任务",
            description="任务描述",
            expected_output="预期输出",
        )
        assert task.name == "测试任务"
        assert task.agent_type == "main"

    def test_to_task_info(self) -> None:
        """测试转换为task_list_manager格式"""
        task = DecomposedTask(
            name="任务",
            description="描述",
            expected_output="输出",
            agent_type="sub",
            dependencies=["前置任务"],
        )
        info = task.to_task_info()
        assert info["task_name"] == "任务"
        assert info["task_desc"] == "描述"
        assert info["agent_type"] == "sub"
        assert "前置任务" in info["dependencies"]


class TestTaskDecomposer:
    """TaskDecomposer测试"""

    @pytest.fixture
    def decomposer(self) -> TaskDecomposer:
        """创建任务分解器"""
        return TaskDecomposer()

    def test_analyze_complexity_simple(self, decomposer: TaskDecomposer) -> None:
        """测试简单任务复杂度分析"""
        goal = Goal(
            id="goal-1",
            title="修复小bug",
            description="修复一个简单的显示问题",
        )
        complexity = decomposer.analyze_complexity(goal)
        assert complexity == TaskComplexity.SIMPLE

    def test_analyze_complexity_medium(self, decomposer: TaskDecomposer) -> None:
        """测试中等任务复杂度分析"""
        goal = Goal(
            id="goal-2",
            title="实现新功能",
            description="开发一个新的用户模块",
        )
        complexity = decomposer.analyze_complexity(goal)
        assert complexity == TaskComplexity.MEDIUM

    def test_analyze_complexity_complex(self, decomposer: TaskDecomposer) -> None:
        """测试复杂任务复杂度分析"""
        goal = Goal(
            id="goal-3",
            title="系统重构",
            description="重构整个架构",
        )
        complexity = decomposer.analyze_complexity(goal)
        assert complexity == TaskComplexity.COMPLEX

    def test_select_strategy_bug(self, decomposer: TaskDecomposer) -> None:
        """测试Bug修复策略选择"""
        goal = Goal(
            id="goal-1",
            title="修复登录bug",
            description="用户无法登录",
        )
        strategy = decomposer.select_strategy(goal)
        assert strategy == "bug_investigation"

    def test_select_strategy_refactoring(self, decomposer: TaskDecomposer) -> None:
        """测试重构策略选择"""
        goal = Goal(
            id="goal-2",
            title="重构代码",
            description="优化代码结构",
        )
        strategy = decomposer.select_strategy(goal)
        assert strategy == "code_refactoring"

    def test_select_strategy_documentation(self, decomposer: TaskDecomposer) -> None:
        """测试文档策略选择"""
        goal = Goal(
            id="goal-3",
            title="编写文档",
            description="编写API文档",
        )
        strategy = decomposer.select_strategy(goal)
        assert strategy == "documentation"

    def test_decompose_feature(self, decomposer: TaskDecomposer) -> None:
        """测试功能开发分解"""
        goal = Goal(
            id="goal-1",
            title="实现用户认证",
            description="实现完整的用户认证功能",
        )
        tasks = decomposer.decompose(goal)
        assert len(tasks) == 5  # feature_development有5个步骤
        # 验证依赖关系
        assert len(tasks[0].dependencies) == 0
        assert len(tasks[1].dependencies) > 0

    def test_decompose_bug_fix(self, decomposer: TaskDecomposer) -> None:
        """测试Bug修复分解"""
        goal = Goal(
            id="goal-2",
            title="修复bug",
            description="修复登录问题",
        )
        tasks = decomposer.decompose(goal)
        assert len(tasks) == 4  # bug_investigation有4个步骤

    def test_decompose_with_custom_tasks(self, decomposer: TaskDecomposer) -> None:
        """测试自定义任务分解"""
        goal = Goal(
            id="goal-3",
            title="自定义任务",
            description="描述",
        )
        custom_tasks = [
            {"name": "步骤1", "desc": "描述1", "output": "输出1"},
            {"name": "步骤2", "desc": "描述2", "output": "输出2"},
        ]
        tasks = decomposer.decompose(goal, custom_tasks=custom_tasks)
        assert len(tasks) == 2
        assert tasks[0].name == "步骤1"

    def test_to_task_list_format(self, decomposer: TaskDecomposer) -> None:
        """测试转换为task_list_manager格式"""
        goal = Goal(
            id="goal-1",
            title="测试",
            description="描述",
        )
        tasks = decomposer.decompose(goal)
        result = decomposer.to_task_list_format(tasks, background="背景信息")
        assert result["action"] == "add_tasks"
        assert result["background"] == "背景信息"
        assert len(result["tasks_info"]) > 0

    def test_estimate_total_effort(self, decomposer: TaskDecomposer) -> None:
        """测试工作量估算"""
        tasks = [
            DecomposedTask(
                name="任务1", description="", expected_output="", estimated_effort="low"
            ),
            DecomposedTask(
                name="任务2",
                description="",
                expected_output="",
                estimated_effort="medium",
            ),
        ]
        effort = decomposer.estimate_total_effort(tasks)
        assert "低" in effort or "中" in effort

    def test_get_available_strategies(self, decomposer: TaskDecomposer) -> None:
        """测试获取可用策略"""
        strategies = decomposer.get_available_strategies()
        assert len(strategies) >= 4
        strategy_names = [s["name"] for s in strategies]
        assert "feature_development" in strategy_names
        assert "bug_investigation" in strategy_names
