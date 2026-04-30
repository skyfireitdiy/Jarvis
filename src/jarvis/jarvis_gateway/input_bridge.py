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
from typing import List
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


@dataclass(frozen=True)
class RemoteConfirmMessage:
    """远端确认消息。"""

    confirmed: bool


class RemoteInputSession:
    """会话级远端输入缓冲区，支持等待、投递与断连。"""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._queue: Queue[RemoteInputMessage] = Queue()
        self._disconnect_reason: Optional[str] = None
        self._state_lock = threading.Lock()
        self._is_waiting_for_input: bool = False

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

    def is_waiting_for_input(self) -> bool:
        """检查当前是否正在等待输入。"""
        with self._state_lock:
            return self._is_waiting_for_input

    def wait_for_input(self, timeout: Optional[float] = None) -> str:
        # 设置等待输入状态
        with self._state_lock:
            self._is_waiting_for_input = True
        try:
            # 优先消费全局缓冲区中的消息
            from jarvis.jarvis_utils.globals import get_input_buffer

            buffered_messages = get_input_buffer()
            print(
                f"[WAIT_INPUT] session_id={self.session_id}, buffered_messages={buffered_messages}"
            )
            if buffered_messages:
                # 将所有缓冲消息合并返回
                result = "\n".join(buffered_messages)
                print(f"[WAIT_INPUT] Returning buffered messages: {result}")
                return result

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
        finally:
            # 清除等待输入状态
            with self._state_lock:
                self._is_waiting_for_input = False


class RemoteConfirmSession:
    """会话级远端确认缓冲区，支持等待、投递与断连。"""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._queue: Queue[RemoteConfirmMessage] = Queue()
        self._disconnect_reason: Optional[str] = None
        self._state_lock = threading.Lock()

    def submit_confirm(self, confirmed: bool) -> None:
        with self._state_lock:
            if self._disconnect_reason is not None:
                raise InputProviderDisconnectedError(self._disconnect_reason)
        self._queue.put(RemoteConfirmMessage(confirmed=confirmed))

    def disconnect(self, reason: str = "remote session disconnected") -> None:
        with self._state_lock:
            if self._disconnect_reason is None:
                self._disconnect_reason = reason
        self._queue.put(RemoteConfirmMessage(confirmed=False))

    def reconnect(self) -> None:
        """重连时清除断开原因，允许继续等待确认。"""
        with self._state_lock:
            self._disconnect_reason = None

    def wait_for_confirm(self, timeout: Optional[float] = None) -> bool:
        while True:
            with self._state_lock:
                disconnect_reason = self._disconnect_reason
            if disconnect_reason is not None and self._queue.empty():
                raise InputProviderDisconnectedError(disconnect_reason)
            try:
                message = self._queue.get(timeout=timeout)
            except Empty as exc:
                raise InputProviderTimeoutError(
                    "timed out waiting for remote confirm"
                ) from exc
            with self._state_lock:
                disconnect_reason = self._disconnect_reason
            if disconnect_reason is not None and not message.confirmed:
                raise InputProviderDisconnectedError(disconnect_reason)
            return message.confirmed


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
        self._confirm_sessions: Dict[str, RemoteConfirmSession] = {}  # 确认会话
        self._pending_input_requests: Dict[
            str, List[dict]
        ] = {}  # 保存待处理的输入请求队列（FIFO）
        self._pending_confirm_requests: Dict[
            str, List[dict]
        ] = {}  # 保存待处理的确认请求队列（FIFO）

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
        """保存输入请求到队列，用于重连后恢复。"""
        with self._lock:
            if session_id not in self._pending_input_requests:
                self._pending_input_requests[session_id] = []
            self._pending_input_requests[session_id].append(request)
            queue_len = len(self._pending_input_requests[session_id])
            print(
                f"[INPUT_REGISTRY] Saved input_request for session={session_id}, queue_len={queue_len}, total_sessions={len(self._pending_input_requests)}"
            )

    def get_input_request(self, session_id: str) -> Optional[dict]:
        """从队列头部获取并移除一个输入请求（FIFO）。"""
        with self._lock:
            queue = self._pending_input_requests.get(session_id)
            if not queue:
                print(
                    f"[INPUT_REGISTRY] Got input_request for session={session_id}, found=False, remaining=0"
                )
                return None
            request = queue.pop(0)  # FIFO: 从头部取出
            # 如果队列为空，清理字典条目
            if not queue:
                self._pending_input_requests.pop(session_id, None)
            remaining = len(queue)
            print(
                f"[INPUT_REGISTRY] Got input_request for session={session_id}, found=True, remaining={remaining}"
            )
            return request

    def clear_input_request(self, session_id: str) -> None:
        """清除保存的输入请求。"""
        with self._lock:
            self._pending_input_requests.pop(session_id, None)

    def get_or_create_confirm_session(self, session_id: str) -> RemoteConfirmSession:
        """获取或创建确认会话。"""
        with self._lock:
            session = self._confirm_sessions.get(session_id)
            if session is None:
                session = RemoteConfirmSession(session_id=session_id)
                self._confirm_sessions[session_id] = session
            return session

    def submit_confirm(self, session_id: str, confirmed: bool) -> None:
        """提交确认结果。"""
        session = self.get_or_create_confirm_session(session_id)
        session.submit_confirm(confirmed)
        # 提交确认后清除保存的确认请求
        self.clear_confirm_request(session_id)

    def save_confirm_request(self, session_id: str, request: dict) -> None:
        """保存确认请求到队列，用于重连后恢复。"""
        with self._lock:
            if session_id not in self._pending_confirm_requests:
                self._pending_confirm_requests[session_id] = []
            self._pending_confirm_requests[session_id].append(request)
            queue_len = len(self._pending_confirm_requests[session_id])
            print(
                f"[CONFIRM_REGISTRY] Saved confirm_request for session={session_id}, queue_len={queue_len}, total_sessions={len(self._pending_confirm_requests)}"
            )

    def get_confirm_request(self, session_id: str) -> Optional[dict]:
        """从队列头部获取并移除一个确认请求（FIFO）。"""
        with self._lock:
            queue = self._pending_confirm_requests.get(session_id)
            if not queue:
                print(
                    f"[CONFIRM_REGISTRY] Got confirm_request for session={session_id}, found=False, remaining=0"
                )
                return None
            request = queue.pop(0)  # FIFO: 从头部取出
            # 如果队列为空，清理字典条目
            if not queue:
                self._pending_confirm_requests.pop(session_id, None)
            remaining = len(queue)
            print(
                f"[CONFIRM_REGISTRY] Got confirm_request for session={session_id}, found=True, remaining={remaining}"
            )
            return request

    def clear_confirm_request(self, session_id: str) -> None:
        """清除保存的确认请求。"""
        with self._lock:
            self._pending_confirm_requests.pop(session_id, None)

    def disconnect_confirm_session(
        self, session_id: str, reason: str = "remote session disconnected"
    ) -> None:
        """断开确认会话。"""
        with self._lock:
            session = self._confirm_sessions.pop(session_id, None)
        if session is not None:
            session.disconnect(reason=reason)
