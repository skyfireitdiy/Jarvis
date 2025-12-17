# -*- coding: utf-8 -*-
"""
事件总线（EventBus）

目标（阶段一，最小变更）：
- 提供简单可靠的发布/订阅机制
- 回调异常隔离，避免影响主流程
- 不引入额外依赖，便于在 Agent 中渐进集成
- 支持优先级排序，优先级数字越小，执行越早
"""

from collections import defaultdict
from typing import Any
from typing import Callable
from typing import DefaultDict


class EventBus:
    """
    简单的同步事件总线。
    - subscribe(event, callback, priority=100): 订阅事件，支持优先级
    - emit(event, **kwargs): 广播事件，按优先级顺序执行回调
    - unsubscribe(event, callback): 取消订阅

    优先级说明：
    - 数字越小，优先级越高，执行越早
    - 默认优先级为 100（中等优先级）
    - 建议优先级范围：0-200
    - 相同优先级时，按注册顺序执行（先注册的先执行）
    """

    def __init__(self) -> None:
        # 存储 (priority, order, callback) 元组列表，按优先级和注册顺序排序
        # order 用于相同优先级时保持注册顺序
        self._listeners: DefaultDict[
            str, list[tuple[int, int, Callable[..., None]]]
        ] = defaultdict(list)
        # 注册顺序计数器（每个事件独立计数）
        self._order_counter: DefaultDict[str, int] = defaultdict(int)
        # 缓存排序后的回调列表，避免每次emit都排序
        self._sorted_cache: DefaultDict[str, list[Callable[..., None]]] = defaultdict(
            list
        )
        # 标记是否需要重新排序
        self._dirty: DefaultDict[str, bool] = defaultdict(lambda: False)

    def subscribe(
        self, event: str, callback: Callable[..., None], priority: int = 100
    ) -> None:
        """
        订阅事件。

        参数:
            event: 事件名称
            callback: 回调函数
            priority: 优先级，数字越小优先级越高（默认100）
                     相同优先级时，按注册顺序执行（先注册的先执行）
        """
        if not callable(callback):
            raise TypeError("callback must be callable")
        # 获取当前注册顺序
        order = self._order_counter[event]
        self._order_counter[event] += 1
        # 添加 (priority, order, callback) 元组
        self._listeners[event].append((priority, order, callback))
        # 标记需要重新排序
        self._dirty[event] = True

    def unsubscribe(self, event: str, callback: Callable[..., None]) -> None:
        """
        取消订阅事件。

        参数:
            event: 事件名称
            callback: 要取消的回调函数
        """
        if event not in self._listeners:
            return
        # 查找并移除匹配的回调
        listeners = self._listeners[event]
        for i, (_, _, cb) in enumerate(listeners):
            if cb == callback:
                listeners.pop(i)
                self._dirty[event] = True
                break

    def _get_sorted_callbacks(self, event: str) -> list[Callable[..., None]]:
        """
        获取排序后的回调列表（带缓存）。

        参数:
            event: 事件名称

        返回:
            按优先级排序的回调函数列表（相同优先级时按注册顺序）
        """
        # 如果缓存有效，直接返回
        if not self._dirty[event] and event in self._sorted_cache:
            return self._sorted_cache[event]

        # 按优先级排序（数字越小优先级越高），相同优先级时按注册顺序（order）
        listeners = self._listeners[event]
        sorted_listeners = sorted(listeners, key=lambda x: (x[0], x[1]))
        callbacks = [cb for _, _, cb in sorted_listeners]

        # 更新缓存
        self._sorted_cache[event] = callbacks
        self._dirty[event] = False

        return callbacks

    def emit(self, event: str, **payload: Any) -> None:
        """
        广播事件。回调中的异常将被捕获并忽略，以保证主流程稳定。
        回调按优先级顺序执行（优先级数字越小，执行越早）。

        参数:
            event: 事件名称
            **payload: 事件负载数据
        """
        callbacks = self._get_sorted_callbacks(event)
        for cb in callbacks:
            try:
                cb(**payload)
            except Exception:
                # 避免回调异常中断主流程
                continue
