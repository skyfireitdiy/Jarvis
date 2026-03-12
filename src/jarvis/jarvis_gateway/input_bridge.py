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

    def reconnect(self) -> None:
        """重连时清除断开原因，允许继续等待输入。"""
        with self._state_lock:
            self._disconnect_reason = None

    def wait_for_input(self, timeout: Optional[float] = None) -> str:
        while True:
            with self._state_lock:
                disconnect_reason = self._disconnect_reason
            if disconnect_reason is not None and self._queue.empty():
                raise InputProviderDisconnectedError(disconnect_reason)
            try:
                message = self._queue.get(timeout=timeout)
            except Empty as exc:
                raise InputProviderTimeoutError(
                    "timed out waiting for remote input"
                ) from exc
            with self._state_lock:
                disconnect_reason = self._disconnect_reason
            if disconnect_reason is not None and message.text == "":
                raise InputProviderDisconnectedError(disconnect_reason)
            return message.text


class WebSocketInputProvider(InputProvider):
    """供 WebSocket/远端会话使用的输入提供者。"""

    def __init__(
        self, session: RemoteInputSession, timeout: Optional[float] = None
    ) -> None:
        self.session = session
        self.timeout = timeout

    def get_multiline_input(
        self,
        tip: str,
        preset: Optional[str] = None,
        preset_cursor: Optional[int] = None,
    ) -> str:
        del tip, preset, preset_cursor
        return self.session.wait_for_input(timeout=self.timeout)


class InputSessionRegistry:
    """最小输入会话注册表。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: Dict[str, RemoteInputSession] = {}
        self._pending_input_requests: Dict[str, dict] = {}  # 保存待处理的输入请求

    def get_or_create(self, session_id: str) -> RemoteInputSession:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = RemoteInputSession(session_id=session_id)
                self._sessions[session_id] = session
            return session

    def register_provider(
        self, session_id: str, timeout: Optional[float] = None
    ) -> WebSocketInputProvider:
        session = self.get_or_create(session_id)
        provider = WebSocketInputProvider(session=session, timeout=timeout)
        register_input_provider(session_id, provider)
        return provider

    def unregister_provider(
        self, session_id: str, disconnect_reason: str = "remote session disconnected"
    ) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        unregister_input_provider(session_id)
        if session is not None:
            session.disconnect(reason=disconnect_reason)

    def submit_input(self, session_id: str, text: str) -> None:
        session = self.get_or_create(session_id)
        session.submit_input(text)
        # 提交输入后清除保存的输入请求
        self.clear_input_request(session_id)

    def save_input_request(self, session_id: str, request: dict) -> None:
        """保存输入请求，用于重连后恢复。"""
        with self._lock:
            self._pending_input_requests[session_id] = request
            print(
                f"[INPUT_REGISTRY] Saved input_request for session={session_id}, total={len(self._pending_input_requests)}"
            )

    def get_input_request(self, session_id: str) -> Optional[dict]:
        """获取并清除保存的输入请求。"""
        with self._lock:
            request = self._pending_input_requests.pop(session_id, None)
            print(
                f"[INPUT_REGISTRY] Got input_request for session={session_id}, found={request is not None}, remaining={len(self._pending_input_requests)}"
            )
            return request

    def clear_input_request(self, session_id: str) -> None:
        """清除保存的输入请求。"""
        with self._lock:
            self._pending_input_requests.pop(session_id, None)
