# -*- coding: utf-8 -*-
"""Web Gateway 内部定时器管理器。"""

from __future__ import annotations

import heapq
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional


logger = logging.getLogger(__name__)

TimerCallback = Callable[[], None]


@dataclass
class TimerTask:
    """定时任务定义。"""

    task_id: str
    callback: TimerCallback
    run_at: float
    interval_seconds: Optional[float] = None
    cancelled: bool = False

    @property
    def is_recurring(self) -> bool:
        """是否为循环任务。"""
        return self.interval_seconds is not None


@dataclass(order=True)
class ScheduledTask:
    """堆中使用的调度任务。"""

    run_at: float
    sequence: int
    task_id: str


class TimerManager:
    """定时器管理器。

    支持：
    - 绝对时间一次任务
    - 相对延迟一次任务
    - 固定间隔循环任务
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._tasks: Dict[str, TimerTask] = {}
        self._queue: List[ScheduledTask] = []
        self._sequence = 0
        self._shutdown = False
        self._worker = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="web-gateway-timer",
        )
        self._worker.start()

    def schedule_at(self, run_at: datetime, callback: TimerCallback) -> str:
        """注册绝对时间一次任务。"""
        return self._schedule_task(run_at=run_at.timestamp(), callback=callback)

    def schedule_after(self, delay_seconds: float, callback: TimerCallback) -> str:
        """注册相对延迟一次任务。"""
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be >= 0")
        return self._schedule_task(run_at=time.time() + delay_seconds, callback=callback)

    def schedule_every(self, interval_seconds: float, callback: TimerCallback) -> str:
        """注册循环定时任务。"""
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")
        return self._schedule_task(
            run_at=time.time() + interval_seconds,
            callback=callback,
            interval_seconds=interval_seconds,
        )

    def cancel(self, task_id: str) -> bool:
        """取消指定任务。"""
        with self._condition:
            task = self._tasks.get(task_id)
            if task is None or task.cancelled:
                return False
            task.cancelled = True
            self._tasks.pop(task_id, None)
            self._condition.notify_all()
            return True

    def shutdown(self) -> None:
        """关闭定时器管理器并停止后续调度。"""
        with self._condition:
            if self._shutdown:
                return
            self._shutdown = True
            self._tasks.clear()
            self._queue.clear()
            self._condition.notify_all()

        if self._worker.is_alive():
            self._worker.join(timeout=1.0)

    def is_shutdown(self) -> bool:
        """检查管理器是否已关闭。"""
        with self._lock:
            return self._shutdown

    def _schedule_task(
        self,
        run_at: float,
        callback: TimerCallback,
        interval_seconds: Optional[float] = None,
    ) -> str:
        with self._condition:
            if self._shutdown:
                raise RuntimeError("TimerManager is shut down")

            task_id = str(uuid.uuid4())
            timer_task = TimerTask(
                task_id=task_id,
                callback=callback,
                run_at=run_at,
                interval_seconds=interval_seconds,
            )
            self._tasks[task_id] = timer_task
            heapq.heappush(
                self._queue,
                ScheduledTask(
                    run_at=run_at,
                    sequence=self._next_sequence(),
                    task_id=task_id,
                ),
            )
            self._condition.notify_all()
            return task_id

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def _run_loop(self) -> None:
        while True:
            task_to_run = self._wait_for_next_task()
            if task_to_run is None:
                return
            self._execute_task(task_to_run)

    def _wait_for_next_task(self) -> Optional[TimerTask]:
        with self._condition:
            while True:
                if self._shutdown:
                    return None

                if not self._queue:
                    self._condition.wait()
                    continue

                scheduled_task = self._queue[0]
                timer_task = self._tasks.get(scheduled_task.task_id)
                if timer_task is None or timer_task.cancelled:
                    heapq.heappop(self._queue)
                    continue

                now = time.time()
                wait_seconds = scheduled_task.run_at - now
                if wait_seconds > 0:
                    self._condition.wait(timeout=wait_seconds)
                    continue

                heapq.heappop(self._queue)
                return timer_task

    def _execute_task(self, timer_task: TimerTask) -> None:
        if timer_task.cancelled:
            return

        try:
            timer_task.callback()
        except Exception:
            logger.exception("Timer task execution failed: %s", timer_task.task_id)

        if not timer_task.is_recurring:
            with self._condition:
                self._tasks.pop(timer_task.task_id, None)
            return

        with self._condition:
            if self._shutdown or timer_task.cancelled:
                self._tasks.pop(timer_task.task_id, None)
                return

            assert timer_task.interval_seconds is not None
            timer_task.run_at = time.time() + timer_task.interval_seconds
            heapq.heappush(
                self._queue,
                ScheduledTask(
                    run_at=timer_task.run_at,
                    sequence=self._next_sequence(),
                    task_id=timer_task.task_id,
                ),
            )
            self._condition.notify_all()
