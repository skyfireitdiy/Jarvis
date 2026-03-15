# -*- coding: utf-8 -*-
"""输出事件到 WebSocket/网关消息的桥接实现。

本模块刻意不依赖具体 WebSocket 框架，提供：
1. OutputEvent -> 结构化消息序列化；
2. 可插拔消息发布器抽象；
3. 基于 OutputSink 的 WebSocketOutputSink；
4. 面向会话/广播的最小路由器实现。
"""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from datetime import datetime
from itertools import count
import threading
from typing import Any
from typing import Callable
from typing import Dict
from typing import Optional

from jarvis.jarvis_utils.output import OUTPUT_ICONS
from jarvis.jarvis_utils.output import OutputEvent
from jarvis.jarvis_utils.output import OutputSink


class OutputMessagePublisher(ABC):
    """结构化输出消息发布器抽象。"""

    @abstractmethod
    def publish(
        self, message: Dict[str, Any], session_id: Optional[str] = None
    ) -> None:
        raise NotImplementedError


class SessionOutputRouter(OutputMessagePublisher):
    """最小会话输出路由器。

    - session_id 为 None 时执行广播；
    - session_id 有值时仅路由到目标会话订阅者；
    - 订阅者使用回调抽象，后续可由真正的 WebSocket 连接对象适配。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: Dict[str, Dict[str, Callable[[Dict[str, Any]], None]]] = {}

    def register(
        self,
        connection_id: str,
        sender: Callable[[Dict[str, Any]], None],
        session_id: Optional[str] = None,
    ) -> None:
        route_key = session_id or "*"
        with self._lock:
            subscribers = self._subscribers.setdefault(route_key, {})
            subscribers[connection_id] = sender

    def unregister(self, connection_id: str, session_id: Optional[str] = None) -> None:
        route_key = session_id or "*"
        with self._lock:
            subscribers = self._subscribers.get(route_key)
            if not subscribers:
                return
            subscribers.pop(connection_id, None)
            if not subscribers:
                self._subscribers.pop(route_key, None)

    def publish(
        self, message: Dict[str, Any], session_id: Optional[str] = None
    ) -> None:
        callbacks: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        with self._lock:
            for route_key in self._resolve_route_keys(session_id):
                callbacks.update(self._subscribers.get(route_key, {}))

        print(f"[SessionOutputRouter] Publishing message: type={message.get('type')}, session_id={session_id}, subscribers={len(callbacks)}")
        for sender in callbacks.values():
            try:
                sender(dict(message))
            except Exception as e:
                print(f"[SessionOutputRouter] Sender error: {e}")

    @staticmethod
    def _resolve_route_keys(session_id: Optional[str]) -> list[str]:
        if session_id:
            return [session_id, "*"]
        return ["*"]

    def has_active_subscribers(self) -> bool:
        """检查是否有活跃的订阅者连接。"""
        with self._lock:
            return bool(self._subscribers)


def serialize_output_event(
    event: OutputEvent,
    *,
    sequence: Optional[int] = None,
    source: str = "jarvis.output",
) -> Dict[str, Any]:
    """将 OutputEvent 序列化为可通过 WebSocket 发送的结构化消息。"""

    payload: Dict[str, Any] = {
        "type": "output",
        "source": source,
        "emitted_at": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
        "output_type": event.output_type.value,
        "icon": OUTPUT_ICONS.get(event.output_type, ""),
        "text": event.text,
        "section": event.section,
        "timestamp": event.timestamp,
        "lang": event.lang,
        "traceback": event.traceback,
        "context": dict(event.context) if event.context else {},
    }
    if sequence is not None:
        payload["sequence"] = sequence
    return payload


class WebSocketOutputSink(OutputSink):
    """基于 OutputSink 的 WebSocket 输出桥接实现。"""

    _global_sequence = count(1)
    _sequence_lock = threading.Lock()

    def __init__(
        self,
        publisher: OutputMessagePublisher,
        session_id: Optional[str] = None,
        source: str = "jarvis.output",
    ) -> None:
        self.publisher = publisher
        self.session_id = session_id
        self.source = source

    def emit(self, event: OutputEvent) -> None:
        message = serialize_output_event(
            event,
            sequence=self._next_sequence(),
            source=self.source,
        )
        if self.session_id and "session_id" not in message["context"]:
            message["context"]["session_id"] = self.session_id
        self.publisher.publish(message, session_id=self.session_id)

    @classmethod
    def _next_sequence(cls) -> int:
        with cls._sequence_lock:
            return next(cls._global_sequence)
