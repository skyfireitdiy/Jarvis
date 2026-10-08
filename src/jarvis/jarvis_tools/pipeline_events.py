# -*- coding: utf-8 -*-
"""流水线进度事件总线：pipeline_runner 与 web_gateway 之间的解耦桥梁。

pipeline_runner 在状态机迁移点通过 `emit()` 写入结构化事件；web_gateway 的
后台线程通过 `drain()` 取出并广播给前端。两者不直接相互 import。

设计要点：
- **线程安全**：pipeline_runner 在独立线程/子进程运行，web_gateway 在 asyncio
  事件循环，跨线程访问用 `threading.Lock` 保护。
- **有界**：队列用 `deque(maxlen=N)`，无消费者时溢出丢弃最旧事件，避免内存膨胀。
  进度事件可容忍丢帧，最终态以 `pipeline_done` 为准。
- **跨进程桥接**：pipeline_runner 可能运行在 Agent 进程（如用户对话 Agent 调用
  该工具），而事件泵（drain 并广播给前端）运行在 web_gateway 进程。两者是
  不同的 Python 进程，模块级单例不共享。因此 `emit()` 在写本地进程内总线之外，
  还会通过 HTTP 把事件上报到 master 网关（`jglobals.master_url`），由网关侧
  的 `/api/pipeline-events` 接口写入网关进程的事件总线，从而被事件泵读到。
  网关进程内（本地泵已激活）只写本地总线，避免重复上报。
- **纯内存、无 IO、无外部依赖**（远程上报失败静默，不影响执行语义）。
"""
import os
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

# 本地事件泵是否激活：web_gateway 启动事件泵线程时置 True。
# 为 True 表示本进程内就有消费者（drain 并广播给前端），此时无需远程上报，
# 避免网关进程内自己调用 pipeline_runner 时重复上报给自己。
_local_pump_active = False
_local_pump_lock = Lock()


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


def set_local_pump_active(active: bool) -> None:
    """设置本地事件泵激活标志（web_gateway 启动/停止事件泵线程时调用）。

    为 True 时 `emit()` 只写本地进程内总线（本进程即有消费者，事件泵会
    drain 并广播给前端），不再远程上报，避免重复。
    """
    global _local_pump_active
    with _local_pump_lock:
        _local_pump_active = bool(active)


def is_local_pump_active() -> bool:
    """本地事件泵是否激活（本进程内是否有事件消费者）。"""
    with _local_pump_lock:
        return _local_pump_active


def emit_remote(event: Dict[str, Any]) -> bool:
    """把事件通过 HTTP 上报到 master 网关的 /api/pipeline-events。

    用于 pipeline_runner 运行在 Agent 进程（非 web_gateway 进程）时，把事件
    桥接到网关进程的事件总线，从而被事件泵读到并广播给前端。

    返回是否上报成功；任何异常都吞掉（纯副作用，不影响执行语义）。
    """
    if not isinstance(event, dict):
        return False
    try:
        import httpx

        import jarvis.jarvis_utils.globals as jglobals

        master_url = (jglobals.master_url or "").strip().rstrip("/")
        if not master_url:
            return False
        auth_token = os.environ.get("JARVIS_AUTH_TOKEN", "")
        headers = {"Content-Type": "application/json"}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        # 上报超时短、失败静默：进度事件可容忍丢帧，终态以 pipeline_done 为准
        with httpx.Client(timeout=3.0, trust_env=False) as client:
            resp = client.post(
                f"{master_url}/api/pipeline-events",
                json={"events": [event]},
                headers=headers,
            )
            return resp.status_code in (200, 204)
    except Exception:  # pylint: disable=broad-except
        return False
