"""目标管理器测试"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from jarvis.jarvis_autonomous.goal_manager import (
    Goal,
    GoalManager,
    GoalPriority,
    GoalProgress,
    GoalStatus,
)


class TestGoal:
    """Goal数据类测试"""

    def test_goal_creation(self) -> None:
        """测试目标创建"""
        goal = Goal(
            id="test-1",
            title="测试目标",
            description="这是一个测试目标",
        )
        assert goal.id == "test-1"
        assert goal.title == "测试目标"
        assert goal.status == GoalStatus.ACTIVE
        assert goal.priority == GoalPriority.MEDIUM

    def test_goal_to_dict(self) -> None:
        """测试目标转换为字典"""
        goal = Goal(
            id="test-1",
            title="测试目标",
            description="描述",
            priority=GoalPriority.HIGH,
            tags=["test", "demo"],
        )
        data = goal.to_dict()
        assert data["id"] == "test-1"
        assert data["priority"] == "high"
        assert data["tags"] == ["test", "demo"]

    def test_goal_from_dict(self) -> None:
        """测试从字典创建目标"""
        data = {
            "id": "test-1",
            "title": "测试目标",
            "description": "描述",
            "priority": "high",
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "tags": ["test"],
        }
        goal = Goal.from_dict(data)
        assert goal.id == "test-1"
        assert goal.priority == GoalPriority.HIGH


class TestGoalProgress:
    """GoalProgress数据类测试"""

    def test_progress_creation(self) -> None:
        """测试进度创建"""
        progress = GoalProgress(
            goal_id="test-1",
            progress_percentage=50.0,
            completed_tasks=5,
            total_tasks=10,
        )
        assert progress.progress_percentage == 50.0
        assert progress.completed_tasks == 5

    def test_progress_to_dict(self) -> None:
        """测试进度转换为字典"""
        progress = GoalProgress(
            goal_id="test-1",
            progress_percentage=75.0,
            completed_tasks=3,
            total_tasks=4,
            notes="进展顺利",
        )
        data = progress.to_dict()
        assert data["progress_percentage"] == 75.0
        assert data["notes"] == "进展顺利"


class TestGoalManager:
    """GoalManager测试"""

    @pytest.fixture
    def temp_storage(self) -> Path:
        """创建临时存储目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def manager(self, temp_storage: Path) -> GoalManager:
        """创建目标管理器"""
        return GoalManager(storage_dir=str(temp_storage))

    def test_create_goal(self, manager: GoalManager) -> None:
        """测试创建目标"""
        goal = manager.create_goal(
            title="实现新功能",
            description="实现用户登录功能",
            priority=GoalPriority.HIGH,
        )
        assert goal.id is not None
        assert goal.title == "实现新功能"
        assert goal.priority == GoalPriority.HIGH

    def test_get_goal(self, manager: GoalManager) -> None:
        """测试获取目标"""
        created = manager.create_goal(
            title="测试目标",
            description="描述",
        )
        retrieved = manager.get_goal(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id

    def test_update_goal(self, manager: GoalManager) -> None:
        """测试更新目标"""
        goal = manager.create_goal(
            title="原标题",
            description="原描述",
        )
        updated = manager.update_goal(
            goal.id,
            title="新标题",
            status=GoalStatus.COMPLETED,
        )
        assert updated is not None
        assert updated.title == "新标题"
        assert updated.status == GoalStatus.COMPLETED

    def test_delete_goal(self, manager: GoalManager) -> None:
        """测试删除目标"""
        goal = manager.create_goal(
            title="待删除",
            description="描述",
        )
        result = manager.delete_goal(goal.id)
        assert result is True
        assert manager.get_goal(goal.id) is None

    def test_list_goals(self, manager: GoalManager) -> None:
        """测试列出目标"""
        manager.create_goal(title="目标1", description="描述1")
        manager.create_goal(
            title="目标2", description="描述2", priority=GoalPriority.HIGH
        )
        manager.create_goal(title="目标3", description="描述3", tags=["important"])

        all_goals = manager.list_goals()
        assert len(all_goals) == 3

        high_priority = manager.list_goals(priority=GoalPriority.HIGH)
        assert len(high_priority) == 1

        tagged = manager.list_goals(tags=["important"])
        assert len(tagged) == 1

    def test_update_progress(self, manager: GoalManager) -> None:
        """测试更新进度"""
        goal = manager.create_goal(
            title="进度测试",
            description="描述",
        )
        progress = manager.update_progress(
            goal.id,
            progress_percentage=50.0,
            completed_tasks=5,
            total_tasks=10,
        )
        assert progress is not None
        assert progress.progress_percentage == 50.0

        # 验证目标已更新
        updated_goal = manager.get_goal(goal.id)
        assert updated_goal is not None
        assert updated_goal.progress is not None
        assert updated_goal.progress.progress_percentage == 50.0

    def test_auto_complete_on_100_percent(self, manager: GoalManager) -> None:
        """测试100%进度自动完成"""
        goal = manager.create_goal(
            title="自动完成测试",
            description="描述",
        )
        manager.update_progress(
            goal.id,
            progress_percentage=100.0,
            completed_tasks=10,
            total_tasks=10,
        )
        updated_goal = manager.get_goal(goal.id)
        assert updated_goal is not None
        assert updated_goal.status == GoalStatus.COMPLETED

    def test_get_active_goals(self, manager: GoalManager) -> None:
        """测试获取活跃目标"""
        manager.create_goal(
            title="活跃目标", description="描述", priority=GoalPriority.HIGH
        )
        manager.create_goal(
            title="低优先级", description="描述", priority=GoalPriority.LOW
        )
        completed = manager.create_goal(title="已完成", description="描述")
        manager.update_goal(completed.id, status=GoalStatus.COMPLETED)

        active = manager.get_active_goals()
        assert len(active) == 2
        # 验证按优先级排序
        assert active[0].priority == GoalPriority.HIGH

    def test_goal_hierarchy(self, manager: GoalManager) -> None:
        """测试目标层级"""
        parent = manager.create_goal(
            title="父目标",
            description="父目标描述",
        )
        child1 = manager.create_goal(
            title="子目标1",
            description="子目标1描述",
            parent_goal_id=parent.id,
        )
        child2 = manager.create_goal(
            title="子目标2",
            description="子目标2描述",
            parent_goal_id=parent.id,
        )

        # 验证父目标的子目标列表
        updated_parent = manager.get_goal(parent.id)
        assert updated_parent is not None
        assert child1.id in updated_parent.sub_goal_ids
        assert child2.id in updated_parent.sub_goal_ids

        # 验证层级结构
        hierarchy = manager.get_goal_hierarchy(parent.id)
        assert len(hierarchy["sub_goals"]) == 2

    def test_extract_goal_from_text(self, manager: GoalManager) -> None:
        """测试从文本提取目标"""
        text = "我想实现一个用户认证系统，支持OAuth2.0"
        result = manager.extract_goal_from_text(text)
        assert result is not None
        assert "title" in result
        assert "description" in result

    def test_suggest_next_actions(self, manager: GoalManager) -> None:
        """测试建议下一步行动"""
        goal = manager.create_goal(
            title="测试目标",
            description="描述",
        )
        suggestions = manager.suggest_next_actions(goal.id)
        assert len(suggestions) > 0

    def test_persistence(self, temp_storage: Path) -> None:
        """测试持久化"""
        # 创建管理器并添加目标
        manager1 = GoalManager(storage_dir=str(temp_storage))
        goal = manager1.create_goal(
            title="持久化测试",
            description="描述",
        )

        # 创建新管理器，验证数据已加载
        manager2 = GoalManager(storage_dir=str(temp_storage))
        loaded = manager2.get_goal(goal.id)
        assert loaded is not None
        assert loaded.title == "持久化测试"
