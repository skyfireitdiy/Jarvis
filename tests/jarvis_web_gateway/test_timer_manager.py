# -*- coding: utf-8 -*-
"""TimerManager tests."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from datetime import timedelta

from jarvis.jarvis_web_gateway.timer_manager import TimerManager


TEST_TIMEOUT_SECONDS = 1.0


def test_schedule_after_executes_callback_once() -> None:
    manager = TimerManager()
    executed = threading.Event()
    run_count = 0
    run_count_lock = threading.Lock()

    def callback() -> None:
        nonlocal run_count
        with run_count_lock:
            run_count += 1
        executed.set()

    try:
        manager.schedule_after(0.05, callback)
        assert executed.wait(TEST_TIMEOUT_SECONDS) is True
        with run_count_lock:
            assert run_count == 1
    finally:
        manager.shutdown()


def test_schedule_at_executes_callback_at_target_time() -> None:
    manager = TimerManager()
    executed = threading.Event()

    def callback() -> None:
        executed.set()

    try:
        run_at = datetime.now() + timedelta(milliseconds=50)
        manager.schedule_at(run_at, callback)
        assert executed.wait(TEST_TIMEOUT_SECONDS) is True
    finally:
        manager.shutdown()


def test_schedule_every_repeats_until_cancelled() -> None:
    manager = TimerManager()
    executed = threading.Event()
    run_count = 0
    run_count_lock = threading.Lock()

    def callback() -> None:
        nonlocal run_count
        with run_count_lock:
            run_count += 1
            if run_count >= 3:
                executed.set()

    try:
        task_id = manager.schedule_every(0.02, callback)
        assert executed.wait(TEST_TIMEOUT_SECONDS) is True
        assert manager.cancel(task_id) is True
        with run_count_lock:
            assert run_count >= 3
    finally:
        manager.shutdown()


def test_shutdown_prevents_future_scheduling() -> None:
    manager = TimerManager()

    manager.shutdown()

    assert manager.is_shutdown() is True

    try:
        manager.schedule_after(0.01, lambda: None)
    except RuntimeError as error:
        assert str(error) == "TimerManager is shut down"
    else:
        raise AssertionError("schedule_after should raise after shutdown")


def test_cancel_prevents_task_execution() -> None:
    manager = TimerManager()
    executed = threading.Event()

    try:
        task_id = manager.schedule_after(0.05, executed.set)
        assert manager.cancel(task_id) is True
        time.sleep(0.12)
        assert executed.is_set() is False
    finally:
        manager.shutdown()


def test_schedule_cron_computes_first_run_at() -> None:
    manager = TimerManager()
    try:
        task_id = manager.schedule_cron("0 9 * * *", lambda: None)
        info = manager.get_task(task_id)
        assert info is not None
        assert info["cron_expr"] == "0 9 * * *"
        assert info["is_recurring"] is True
        # 首次触发为下一个 9:00
        assert info["run_at"].endswith("09:00:00")
    finally:
        manager.shutdown()


def test_schedule_cron_invalid_expression_raises() -> None:
    manager = TimerManager()
    try:
        try:
            manager.schedule_cron("not a cron", lambda: None)
        except ValueError as error:
            assert "invalid cron expression" in str(error)
        else:
            raise AssertionError("schedule_cron should raise on invalid cron")
    finally:
        manager.shutdown()


def test_schedule_cron_persists_cron_expr() -> None:
    manager = TimerManager()
    try:
        task_id = manager.schedule_cron("0 9 * * *", lambda: None)
        info = manager.get_task(task_id)
        assert info is not None
        assert info["cron_expr"] == "0 9 * * *"
        assert info["interval_seconds"] is None
    finally:
        manager.shutdown()


def test_restore_cron_task() -> None:
    def factory(metadata):
        return lambda: None

    manager = TimerManager(task_factory=factory)
    try:
        task_id = manager.restore_task(
            {
                "task_id": "cron-task-1",
                "run_at": "2026-10-03T09:00:00",
                "cron_expr": "0 9 * * *",
                "interval_seconds": None,
                "metadata": {"action": {"type": "run_shell_command", "params": {}}},
            }
        )
        info = manager.get_task(task_id)
        assert info is not None
        assert info["cron_expr"] == "0 9 * * *"
        assert info["is_recurring"] is True
        # 恢复时 run_at 取「传入值」与「当前时间」的较大值，避免安排到过去；
        # 传入的 09:00 可能已过期，故用 max 计算期望值，保证断言与时间无关。
        expected_ts = max(
            datetime.fromisoformat("2026-10-03T09:00:00").timestamp(),
            time.time(),
        )
        assert (
            abs(datetime.fromisoformat(info["run_at"]).timestamp() - expected_ts) < 1.0
        )
    finally:
        manager.shutdown()


def test_persist_disabled_does_not_load_or_write_file(
    tmp_path, monkeypatch
) -> None:
    """persist_enabled=False 时：不加载持久化文件、不写回文件。

    对应 Agent 进程（custom_app 模式）场景：多个 TimerManager 共享同一
    持久化文件会互相覆盖，导致主网关删除的任务被写回（复活）、新建任务被
    覆盖（丢失）。禁用持久化后 Agent 进程的 TimerManager 仅作内存态使用。
    """
    persist_file = tmp_path / ".jarvis_timers.json"
    # 预置一个已持久化的任务，验证 persist_enabled=False 时不会被加载
    persist_file.write_text(
        json.dumps(
            [
                {
                    "task_id": "ghost-task",
                    "run_at": "2026-10-13T16:00:00",
                    "interval_seconds": 300.0,
                    "cron_expr": None,
                    "is_recurring": True,
                    "cancelled": False,
                    "metadata": {
                        "action": {
                            "type": "run_shell_command",
                            "params": {
                                "command": "echo hi",
                                "working_dir": "/tmp",
                                "interpreter": "bash",
                            },
                        },
                        "schedule": {"type": "interval", "interval_seconds": 300.0},
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    manager = TimerManager(persist_enabled=False)
    monkeypatch.setattr(
        type(manager), "PERSISTENCE_FILE", persist_file
    )
    try:
        # 1) 不加载持久化文件中的任务
        manager.load_persisted_tasks()
        assert manager.list_tasks() == []

        # 2) 调度任务后不写回文件
        manager.schedule_after(3600, lambda: None)
        assert persist_file.read_text(encoding="utf-8").strip() != "[]"
        # 文件内容应保持为预置的 ghost-task，未被本实例覆盖
        loaded = json.loads(persist_file.read_text(encoding="utf-8"))
        assert [t["task_id"] for t in loaded] == ["ghost-task"]
    finally:
        manager.shutdown()


def test_persist_enabled_still_loads_and_writes(tmp_path, monkeypatch) -> None:
    """persist_enabled=True（默认，主网关模式）行为不变：加载并写回文件。"""
    persist_file = tmp_path / ".jarvis_timers.json"
    persist_file.write_text("[]", encoding="utf-8")

    manager = TimerManager(persist_enabled=True)
    monkeypatch.setattr(type(manager), "PERSISTENCE_FILE", persist_file)
    try:
        manager.schedule_after(3600, lambda: None)
        loaded = json.loads(persist_file.read_text(encoding="utf-8"))
        assert len(loaded) == 1
    finally:
        manager.shutdown()


def test_schedule_every_persist_false_does_not_write_file(
    tmp_path, monkeypatch
) -> None:
    """schedule_every(persist=False) 不写入持久化文件。

    内置任务（如插件更新检测）每次启动重新注册，不落盘：
    避免重启后 load_persisted_tasks 用 task_factory 恢复时，因内置任务
    没有可序列化的 action 元数据而恢复失败。
    """
    persist_file = tmp_path / ".jarvis_timers.json"
    persist_file.write_text("[]", encoding="utf-8")

    manager = TimerManager(persist_enabled=True)
    monkeypatch.setattr(type(manager), "PERSISTENCE_FILE", persist_file)
    try:
        manager.schedule_every(3600, lambda: None, persist=False)
        loaded = json.loads(persist_file.read_text(encoding="utf-8"))
        assert loaded == []
        # 任务本身已注册（仅不落盘）
        assert len(manager.list_tasks()) == 1
    finally:
        manager.shutdown()


def test_schedule_every_persist_true_writes_file(tmp_path, monkeypatch) -> None:
    """schedule_every 默认 persist=True，行为不变：写入持久化文件。"""
    persist_file = tmp_path / ".jarvis_timers.json"
    persist_file.write_text("[]", encoding="utf-8")

    manager = TimerManager(persist_enabled=True)
    monkeypatch.setattr(type(manager), "PERSISTENCE_FILE", persist_file)
    try:
        manager.schedule_every(3600, lambda: None)
        loaded = json.loads(persist_file.read_text(encoding="utf-8"))
        assert len(loaded) == 1
    finally:
        manager.shutdown()
