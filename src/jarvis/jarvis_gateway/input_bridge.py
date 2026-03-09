# -*- coding: utf-8 -*-
"""输入侧网关桥接实现。

提供：
1. 会话级远端输入缓存与等待；
2. 基于 jarvis_utils.input.InputProvider 的 WebSocket/远端输入提供者；
3. 供后续 websocket router 复用的会话注册表。
"""

from __future__ import annotations

from dataclasses import dataclass
from queue import Empty
from queue import Queue
import threading
from typing import Dict
from typing import Optional

from jarvis.jarvis_utils.input import InputProvider
from jarvis.jarvis_utils.input import InputProviderDisconnectedError
from jarvis.jarvis_utils.input import InputProviderTimeoutError
from jarvis.jarvis_utils.input import register_input_provider
from jarvis.jarvis_utils.input import unregister_input_provider


@dataclass(frozen=True)
class RemoteInputMessage:
    """远端输入消息。"""

    text: str


class RemoteInputSession:
    """会话级远端输入缓冲区，支持等待、投递与断连。"""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._queue: Queue[RemoteInputMessage] = Queue()
        self._disconnect_reason: Optional[str] = None
        self._state_lock = threading.Lock()

    def submit_input(self, text: str) -> None:
        with self._state_lock:
            if self._disconnect_reason is not None:
                raise InputProviderDisconnectedError(self._disconnect_reason)
        self._queue.put(RemoteInputMessage(text=text))

    def disconnect(self, reason: str = "remote session disconnected") -> None:
        with self._state_lock:
            if self._disconnect_reason is None:
                self._disconnect_reason = reason
        self._queue.put(RemoteInputMessage(text=""))

    def wait_for_input(self, timeout: Optional[float] = None) -> str:
        while True:
            with self._state_lock:
                disconnect_reason = self._disconnect_reason
            if disconnect_reason is not None and self._queue.empty():
                raise InputProviderDisconnectedError(disconnect_reason)
            try:
                message = self._queue.get(timeout=timeout)
            except Empty as exc:
                raise InputProviderTimeoutError("timed out waiting for remote input") from exc
            with self._state_lock:
                disconnect_reason = self._disconnect_reason
            if disconnect_reason is not None and message.text == "":
                raise InputProviderDisconnectedError(disconnect_reason)
            return message.text


class WebSocketInputProvider(InputProvider):
    """供 WebSocket/远端会话使用的输入提供者。"""

    def __init__(self, session: RemoteInputSession, timeout: Optional[float] = None) -> None:
        self.session = session
        self.timeout = timeout

    def get_multiline_input(
        self, tip: str, preset: Optional[str] = None, preset_cursor: Optional[int] = None
    ) -> str:
        del tip, preset, preset_cursor
        return self.session.wait_for_input(timeout=self.timeout)


class InputSessionRegistry:
    """最小输入会话注册表。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: Dict[str, RemoteInputSession] = {}

    def get_or_create(self, session_id: str) -> RemoteInputSession:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = RemoteInputSession(session_id=session_id)
                self._sessions[session_id] = session
            return session

    def register_provider(self, session_id: str, timeout: Optional[float] = None) -> WebSocketInputProvider:
        session = self.get_or_create(session_id)
        provider = WebSocketInputProvider(session=session, timeout=timeout)
        register_input_provider(session_id, provider)
        return provider

    def unregister_provider(self, session_id: str, disconnect_reason: str = "remote session disconnected") -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        unregister_input_provider(session_id)
        if session is not None:
            session.disconnect(reason=disconnect_reason)

    def submit_input(self, session_id: str, text: str) -> None:
        session = self.get_or_create(session_id)
        session.submit_input(text)
