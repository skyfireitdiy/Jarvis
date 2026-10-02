# -*- coding: utf-8 -*-
"""TimerManager tests."""

from __future__ import annotations

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
        assert info["run_at"].endswith("09:00:00")
    finally:
        manager.shutdown()
