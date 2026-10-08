# -*- coding: utf-8 -*-
"""流水线进度事件总线：pipeline_runner 与 web_gateway 之间的解耦桥梁。

pipeline_runner 在状态机迁移点通过 `emit()` 写入结构化事件；web_gateway 的
后台线程通过 `drain()` 取出并广播给前端。两者不直接相互 import。

设计要点：
- **线程安全**：pipeline_runner 在独立线程/子进程运行，web_gateway 在 asyncio
  事件循环，跨线程访问用 `threading.Lock` 保护。
- **有界**：队列用 `deque(maxlen=N)`，无消费者时溢出丢弃最旧事件，避免内存膨胀。
  进度事件可容忍丢帧，最终态以 `pipeline_done` 为准。
- **纯内存、无 IO、无外部依赖**。
"""
from collections import deque
from threading import Lock
from typing import Any
from typing import Dict
from typing import List

# 事件队列上限：无消费者时最多驻留的事件数（超出丢弃最旧）
_MAX_EVENTS = 2000

# 全局单例
_bus: "PipelineEventBus | None" = None
_bus_lock = Lock()


class PipelineEventBus:
    """线程安全、有界的流水线事件队列。"""

    def __init__(self, max_events: int = _MAX_EVENTS) -> None:
        self._events: deque = deque(maxlen=max_events)
        self._lock = Lock()

    def emit(self, event: Dict[str, Any]) -> None:
        """生产者：写入一条事件（满则丢弃最旧）。"""
        if not isinstance(event, dict):
            return
        with self._lock:
            self._events.append(event)

    def drain(self) -> List[Dict[str, Any]]:
        """消费者：取出并清空当前所有事件（保持写入顺序）。"""
        with self._lock:
            events = list(self._events)
            self._events.clear()
            return events

    def has_events(self) -> bool:
        """是否还有未消费的事件。"""
        with self._lock:
            return len(self._events) > 0


def get_event_bus() -> PipelineEventBus:
    """获取全局事件总线单例（懒初始化，线程安全）。"""
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = PipelineEventBus()
    return _bus
