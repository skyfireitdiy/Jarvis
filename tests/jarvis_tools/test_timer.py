# -*- coding: utf-8 -*-
"""TimerManager 定时器状态持久化单元测试

覆盖 Bug：工具调用 after/at/loop 创建的定时任务，跨会话恢复后 timer 工具查不到。
根因：get_state() 持久化时排除了 relative（after）任务，导致延时任务无法跨会话恢复。
"""

from datetime import datetime, timedelta

from jarvis.jarvis_tools.timer import TimerManager


def _make_manager():
    """构造一个独立 TimerManager（不污染全局单例）"""
    return TimerManager()


def test_get_state_persists_relative_after_task():
    """after（relative）创建的定时任务应被持久化"""
    m = _make_manager()
    m.add_task(
        task_type="tool_call",
        time_type="relative",
        time_value=3600,
        tool_name="read_code",
        tool_args={"path": "a.py"},
    )
    state = m.get_state()
    time_types = [t["time_type"] for t in state["tasks"]]
    assert "relative" in time_types, "after 创建的 relative 任务应被持久化"


def test_get_state_persists_interval_loop_task():
    """loop（interval）创建的定时任务应被持久化"""
    m = _make_manager()
    m.add_task(
        task_type="tool_call",
        time_type="interval",
        time_value=60,
        tool_name="read_code",
        tool_args={},
        interval_seconds=60,
    )
    state = m.get_state()
    time_types = [t["time_type"] for t in state["tasks"]]
    assert "interval" in time_types


def test_get_state_excludes_cancelled_tasks():
    """已取消的任务不应被持久化"""
    m = _make_manager()
    task = m.add_task(
        task_type="tool_call",
        time_type="relative",
        time_value=3600,
        tool_name="read_code",
        tool_args={},
    )
    m.cancel_task(task.task_id)
    state = m.get_state()
    assert state["tasks"] == []


def test_restore_state_recovers_relative_after_task():
    """跨会话恢复后，after（relative）任务应能被 list_tasks 查到"""
    m = _make_manager()
    m.add_task(
        task_type="tool_call",
        time_type="relative",
        time_value=3600,
        tool_name="read_code",
        tool_args={"path": "a.py"},
    )
    state = m.get_state()

    # 模拟新会话：全新 manager 恢复状态
    m2 = _make_manager()
    m2.restore_state(state)
    tasks = m2.list_tasks()
    assert len(tasks) == 1
    assert tasks[0]["time_type"] == "relative"
    assert tasks[0]["tool_name"] == "read_code"


def _make_interval_state(status: str) -> dict:
    """构造一个 interval 任务的持久化 state，next_fire_time 指向未来"""
    m = _make_manager()
    task = m.add_task(
        task_type="tool_call",
        time_type="interval",
        time_value=60,
        tool_name="read_code",
        tool_args={},
        interval_seconds=60,
    )
    task.status = status
    # 确保 next_fire_time 有效（未来时间），让 restore_state 走到调度分支
    task.next_fire_time = (datetime.now() + timedelta(hours=1)).isoformat()
    return m.get_state()


def test_restore_state_skips_completed_task():
    """已完成（completed）的 interval 任务不应被恢复后继续触发

    回归防护：修复前 restore_state 不检查 status，completed 任务会被 _schedule_task
    强制改回 pending 并复活继续触发。
    """
    state = _make_interval_state(status="completed")
    m = _make_manager()
    m.restore_state(state)
    assert m.list_tasks() == [], "completed 任务不应被恢复"
    assert len(m._tasks) == 0, "completed 任务不应进入调度表"


def test_restore_state_recovers_pending_interval_task():
    """待触发的 pending interval 任务应正常恢复（确保修复未误伤正常任务）"""
    state = _make_interval_state(status="pending")
    m = _make_manager()
    m.restore_state(state)
    tasks = m.list_tasks()
    assert len(tasks) == 1
    assert tasks[0]["time_type"] == "interval"
    assert tasks[0]["status"] == "pending"
