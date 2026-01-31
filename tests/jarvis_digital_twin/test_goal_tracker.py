"""目标追踪器测试模块"""

from jarvis.jarvis_digital_twin.user_profile.goal_tracker import (
    GoalTracker,
    TrackedGoal,
    GoalType,
    GoalStatus,
    GoalProgress,
)


class TestGoalProgress:
    """GoalProgress数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        progress = GoalProgress()
        assert progress.percentage == 0.0
        assert progress.completed_milestones == 0
        assert progress.total_milestones == 0
        assert progress.last_activity == ""
        assert progress.last_updated == ""

    def test_update_with_milestone(self) -> None:
        """测试里程碑更新"""
        progress = GoalProgress(total_milestones=5)
        progress.update(milestone_completed=True)
        assert progress.completed_milestones == 1
        assert progress.percentage == 20.0
        assert progress.last_updated != ""

    def test_update_without_milestone(self) -> None:
        """测试无里程碑更新"""
        progress = GoalProgress(total_milestones=5)
        progress.update(milestone_completed=False)
        assert progress.completed_milestones == 0
        assert progress.percentage == 0.0
        assert progress.last_updated != ""

    def test_update_milestone_cap(self) -> None:
        """测试里程碑上限"""
        progress = GoalProgress(total_milestones=2, completed_milestones=2)
        progress.update(milestone_completed=True)
        assert progress.completed_milestones == 2  # 不超过总数


class TestTrackedGoal:
    """TrackedGoal数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        goal = TrackedGoal()
        assert goal.id != ""
        assert goal.goal_type == GoalType.SHORT_TERM
        assert goal.description == ""
        assert goal.confidence == 0.5
        assert goal.status == GoalStatus.ACTIVE
        assert goal.source == ""
        assert goal.tags == []
        assert goal.parent_goal_id is None
        assert goal.sub_goal_ids == []

    def test_to_dict(self) -> None:
        """测试转换为字典"""
        goal = TrackedGoal(
            description="测试目标",
            goal_type=GoalType.LONG_TERM,
            confidence=0.8,
            tags=["test"],
        )
        data = goal.to_dict()
        assert data["description"] == "测试目标"
        assert data["goal_type"] == "long_term"
        assert data["confidence"] == 0.8
        assert data["tags"] == ["test"]

    def test_from_dict(self) -> None:
        """测试从字典创建"""
        data = {
            "id": "test-id",
            "description": "测试目标",
            "goal_type": "medium_term",
            "confidence": 0.9,
            "status": "completed",
            "progress": {
                "percentage": 100.0,
                "completed_milestones": 3,
                "total_milestones": 3,
            },
        }
        goal = TrackedGoal.from_dict(data)
        assert goal.id == "test-id"
        assert goal.description == "测试目标"
        assert goal.goal_type == GoalType.MEDIUM_TERM
        assert goal.confidence == 0.9
        assert goal.status == GoalStatus.COMPLETED
        assert goal.progress.percentage == 100.0


class TestGoalTracker:
    """GoalTracker类测试"""

    def test_init(self) -> None:
        """测试初始化"""
        tracker = GoalTracker()
        assert tracker._goals == {}
        assert tracker._goal_history == []

    def test_track_goal_basic(self) -> None:
        """测试基本目标追踪"""
        tracker = GoalTracker()
        goal = tracker.track_goal(
            description="完成项目",
            goal_type=GoalType.SHORT_TERM,
        )
        assert goal.description == "完成项目"
        assert goal.goal_type == GoalType.SHORT_TERM
        assert goal.id in tracker._goals

    def test_track_goal_with_all_params(self) -> None:
        """测试带所有参数的目标追踪"""
        tracker = GoalTracker()
        goal = tracker.track_goal(
            description="学习Python",
            goal_type=GoalType.LONG_TERM,
            confidence=0.9,
            source="explicit",
            context={"reason": "职业发展"},
            tags=["学习", "编程"],
            total_milestones=10,
        )
        assert goal.description == "学习Python"
        assert goal.goal_type == GoalType.LONG_TERM
        assert goal.confidence == 0.9
        assert goal.source == "explicit"
        assert goal.context == {"reason": "职业发展"}
        assert goal.tags == ["学习", "编程"]
        assert goal.progress.total_milestones == 10

    def test_track_goal_with_parent(self) -> None:
        """测试带父目标的追踪"""
        tracker = GoalTracker()
        parent = tracker.track_goal(description="主目标")
        child = tracker.track_goal(description="子目标", parent_goal_id=parent.id)
        assert child.parent_goal_id == parent.id
        assert child.id in tracker._goals[parent.id].sub_goal_ids

    def test_infer_goals_from_context_with_intent(self) -> None:
        """测试从上下文推断目标（有意图）"""
        tracker = GoalTracker()
        result = tracker.infer_goals_from_context("我想要今天完成这个功能")
        assert len(result.inferred_goals) == 1
        assert result.inferred_goals[0].goal_type == GoalType.SHORT_TERM
        assert result.inferred_goals[0].source == "inferred"

    def test_infer_goals_from_context_without_intent(self) -> None:
        """测试从上下文推断目标（无意图）"""
        tracker = GoalTracker()
        result = tracker.infer_goals_from_context("今天天气真好")
        assert len(result.inferred_goals) == 0

    def test_infer_goals_long_term(self) -> None:
        """测试推断长期目标"""
        tracker = GoalTracker()
        result = tracker.infer_goals_from_context("我计划今年学会Rust编程语言")
        assert len(result.inferred_goals) == 1
        assert result.inferred_goals[0].goal_type == GoalType.LONG_TERM

    def test_infer_goals_medium_term(self) -> None:
        """测试推断中期目标"""
        tracker = GoalTracker()
        result = tracker.infer_goals_from_context("我打算这个月完成代码重构")
        assert len(result.inferred_goals) == 1
        assert result.inferred_goals[0].goal_type == GoalType.MEDIUM_TERM

    def test_get_current_goals_all(self) -> None:
        """测试获取所有当前目标"""
        tracker = GoalTracker()
        tracker.track_goal("目标1", GoalType.SHORT_TERM)
        tracker.track_goal("目标2", GoalType.LONG_TERM)
        goals = tracker.get_current_goals()
        assert len(goals) == 2

    def test_get_current_goals_by_type(self) -> None:
        """测试按类型获取目标"""
        tracker = GoalTracker()
        tracker.track_goal("短期目标", GoalType.SHORT_TERM)
        tracker.track_goal("长期目标", GoalType.LONG_TERM)
        goals = tracker.get_current_goals(goal_type=GoalType.SHORT_TERM)
        assert len(goals) == 1
        assert goals[0].description == "短期目标"

    def test_get_current_goals_by_status(self) -> None:
        """测试按状态获取目标"""
        tracker = GoalTracker()
        goal1 = tracker.track_goal("活跃目标")
        goal2 = tracker.track_goal("已完成目标")
        tracker.update_goal_status(goal2.id, GoalStatus.COMPLETED)
        goals = tracker.get_current_goals(status=GoalStatus.ACTIVE)
        assert len(goals) == 1
        assert goals[0].id == goal1.id

    def test_get_current_goals_by_confidence(self) -> None:
        """测试按置信度获取目标"""
        tracker = GoalTracker()
        tracker.track_goal("高置信度", confidence=0.9)
        tracker.track_goal("低置信度", confidence=0.3)
        goals = tracker.get_current_goals(min_confidence=0.5)
        assert len(goals) == 1
        assert goals[0].description == "高置信度"

    def test_update_goal_progress_milestone(self) -> None:
        """测试更新目标进度（里程碑）"""
        tracker = GoalTracker()
        goal = tracker.track_goal("测试目标", total_milestones=4)
        updated = tracker.update_goal_progress(goal.id, milestone_completed=True)
        assert updated is not None
        assert updated.progress.completed_milestones == 1
        assert updated.progress.percentage == 25.0

    def test_update_goal_progress_percentage(self) -> None:
        """测试更新目标进度（百分比）"""
        tracker = GoalTracker()
        goal = tracker.track_goal("测试目标")
        updated = tracker.update_goal_progress(goal.id, new_percentage=50.0)
        assert updated is not None
        assert updated.progress.percentage == 50.0

    def test_update_goal_progress_auto_complete(self) -> None:
        """测试进度100%自动完成"""
        tracker = GoalTracker()
        goal = tracker.track_goal("测试目标")
        updated = tracker.update_goal_progress(goal.id, new_percentage=100.0)
        assert updated is not None
        assert updated.status == GoalStatus.COMPLETED

    def test_update_goal_progress_nonexistent(self) -> None:
        """测试更新不存在的目标"""
        tracker = GoalTracker()
        result = tracker.update_goal_progress("nonexistent-id")
        assert result is None

    def test_get_goal_by_id(self) -> None:
        """测试根据ID获取目标"""
        tracker = GoalTracker()
        goal = tracker.track_goal("测试目标")
        found = tracker.get_goal_by_id(goal.id)
        assert found is not None
        assert found.id == goal.id

    def test_get_goal_by_id_nonexistent(self) -> None:
        """测试获取不存在的目标"""
        tracker = GoalTracker()
        found = tracker.get_goal_by_id("nonexistent-id")
        assert found is None

    def test_update_goal_status(self) -> None:
        """测试更新目标状态"""
        tracker = GoalTracker()
        goal = tracker.track_goal("测试目标")
        updated = tracker.update_goal_status(goal.id, GoalStatus.PAUSED)
        assert updated is not None
        assert updated.status == GoalStatus.PAUSED

    def test_remove_goal(self) -> None:
        """测试移除目标"""
        tracker = GoalTracker()
        goal = tracker.track_goal("测试目标")
        result = tracker.remove_goal(goal.id)
        assert result is True
        assert goal.id not in tracker._goals

    def test_remove_goal_with_parent(self) -> None:
        """测试移除有父目标的目标"""
        tracker = GoalTracker()
        parent = tracker.track_goal("父目标")
        child = tracker.track_goal("子目标", parent_goal_id=parent.id)
        tracker.remove_goal(child.id)
        assert child.id not in tracker._goals[parent.id].sub_goal_ids

    def test_remove_goal_nonexistent(self) -> None:
        """测试移除不存在的目标"""
        tracker = GoalTracker()
        result = tracker.remove_goal("nonexistent-id")
        assert result is False

    def test_get_goals_by_tag(self) -> None:
        """测试根据标签获取目标"""
        tracker = GoalTracker()
        tracker.track_goal("目标1", tags=["work", "urgent"])
        tracker.track_goal("目标2", tags=["personal"])
        goals = tracker.get_goals_by_tag("work")
        assert len(goals) == 1
        assert goals[0].description == "目标1"

    def test_get_sub_goals(self) -> None:
        """测试获取子目标"""
        tracker = GoalTracker()
        parent = tracker.track_goal("父目标")
        child1 = tracker.track_goal("子目标1", parent_goal_id=parent.id)
        child2 = tracker.track_goal("子目标2", parent_goal_id=parent.id)
        sub_goals = tracker.get_sub_goals(parent.id)
        assert len(sub_goals) == 2
        assert child1.id in [g.id for g in sub_goals]
        assert child2.id in [g.id for g in sub_goals]

    def test_get_goal_statistics(self) -> None:
        """测试获取目标统计"""
        tracker = GoalTracker()
        tracker.track_goal("短期", GoalType.SHORT_TERM, confidence=0.8)
        tracker.track_goal("长期", GoalType.LONG_TERM, confidence=0.6)
        stats = tracker.get_goal_statistics()
        assert stats["total_goals"] == 2
        assert stats["by_type"]["short_term"] == 1
        assert stats["by_type"]["long_term"] == 1
        assert stats["average_confidence"] == 0.7

    def test_get_goal_statistics_empty(self) -> None:
        """测试空目标统计"""
        tracker = GoalTracker()
        stats = tracker.get_goal_statistics()
        assert stats["total_goals"] == 0
        assert stats["average_confidence"] == 0.0

    def test_get_history(self) -> None:
        """测试获取历史记录"""
        tracker = GoalTracker()
        goal = tracker.track_goal("测试目标")
        tracker.update_goal_progress(goal.id, new_percentage=50.0)
        history = tracker.get_history()
        assert len(history) == 2
        assert history[0]["action"] == "update_progress"
        assert history[1]["action"] == "track"

    def test_get_history_with_limit(self) -> None:
        """测试获取有限历史记录"""
        tracker = GoalTracker()
        tracker.track_goal("目标1")
        tracker.track_goal("目标2")
        tracker.track_goal("目标3")
        history = tracker.get_history(limit=2)
        assert len(history) == 2

    def test_clear_all_goals(self) -> None:
        """测试清除所有目标"""
        tracker = GoalTracker()
        tracker.track_goal("目标1")
        tracker.track_goal("目标2")
        count = tracker.clear_all_goals()
        assert count == 2
        assert len(tracker._goals) == 0

    def test_infer_goal_type_keywords(self) -> None:
        """测试目标类型关键词推断"""
        tracker = GoalTracker()
        assert tracker._infer_goal_type("今天完成") == GoalType.SHORT_TERM
        assert tracker._infer_goal_type("这个月完成") == GoalType.MEDIUM_TERM
        assert tracker._infer_goal_type("今年完成") == GoalType.LONG_TERM
        assert tracker._infer_goal_type("完成任务") == GoalType.SHORT_TERM  # 默认

    def test_calculate_confidence(self) -> None:
        """测试置信度计算"""
        tracker = GoalTracker()
        # 无意图关键词，无时间关键词
        conf1 = tracker._calculate_confidence("天气真好")
        # 有意图关键词
        conf2 = tracker._calculate_confidence("我想要完成这个任务")
        # 多个意图关键词 + 时间关键词
        conf3 = tracker._calculate_confidence("我想要并且计划今天完成")
        assert conf1 < conf2 < conf3

    def test_extract_goal_description(self) -> None:
        """测试目标描述提取"""
        tracker = GoalTracker()
        desc = tracker._extract_goal_description("  测试描述  ")
        assert desc == "测试描述"

    def test_extract_goal_description_long(self) -> None:
        """测试长描述截断"""
        tracker = GoalTracker()
        long_text = "a" * 300
        desc = tracker._extract_goal_description(long_text)
        assert len(desc) <= 203  # 200 + "..."
        assert desc.endswith("...")
