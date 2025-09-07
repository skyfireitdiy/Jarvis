# -*- coding: utf-8 -*-
"""
事件总线（EventBus）

目标（阶段一，最小变更）：
- 提供简单可靠的发布/订阅机制
- 回调异常隔离，避免影响主流程
- 不引入额外依赖，便于在 Agent 中渐进集成
"""
from collections import defaultdict
from typing import Callable, DefaultDict, Dict, List



class EventBus:
    """
    简单的同步事件总线。
    - subscribe(event, callback): 订阅事件
    - emit(event, **kwargs): 广播事件
    - unsubscribe(event, callback): 取消订阅
    """

    def __init__(self) -> None:
        self._listeners: DefaultDict[str, List[Callable[..., None]]] = defaultdict(list)

    def subscribe(self, event: str, callback: Callable[..., None]) -> None:
        if not callable(callback):
            raise TypeError("callback must be callable")
        self._listeners[event].append(callback)

    def unsubscribe(self, event: str, callback: Callable[..., None]) -> None:
        if event not in self._listeners:
            return
        try:
            self._listeners[event].remove(callback)
        except ValueError:
            pass

    def emit(self, event: str, **payload: Dict) -> None:
        """
        广播事件。回调中的异常将被捕获并忽略，以保证主流程稳定。
        """
        for cb in list(self._listeners.get(event, [])):
            try:
                cb(**payload)
            except Exception:
                # 避免回调异常中断主流程
                continue
