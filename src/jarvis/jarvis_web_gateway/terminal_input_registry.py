# -*- coding: utf-8 -*-
"""TTY 终端输入注册表。

提供按 execution_id 隔离的输入缓冲区，并生成适配 execute_script 的 input_callback。
"""

from __future__ import annotations

from dataclasses import dataclass
from queue import Empty
from queue import Queue
import threading
from typing import Callable
from typing import Dict
from typing import Optional
from typing import Tuple


@dataclass(frozen=True)
class TerminalInputMessage:
    """终端输入消息。"""

    data: str


@dataclass(frozen=True)
class TerminalResizeMessage:
    """终端尺寸变更消息。"""

    rows: int
    cols: int


class TerminalInputSession:
    """单个 execution_id 对应的输入缓冲区。"""

    def __init__(self, execution_id: str) -> None:
        self.execution_id = execution_id
        self._queue: Queue[TerminalInputMessage] = Queue()
        self._resize_queue: Queue[TerminalResizeMessage] = Queue()
        self._closed = False
        self._state_lock = threading.Lock()

    def submit_input(self, data: str) -> None:
        if not data:
            return
        with self._state_lock:
            if self._closed:
                return
        self._queue.put(TerminalInputMessage(data=data))

    def close(self) -> None:
        with self._state_lock:
            self._closed = True
        self._queue.put(TerminalInputMessage(data=""))
        self._resize_queue.put(TerminalResizeMessage(rows=0, cols=0))

    def read_input(self, timeout: float) -> Optional[str]:
        with self._state_lock:
            if self._closed:
                return None
        try:
            message = self._queue.get(timeout=timeout)
        except Empty:
            return None
        if not message.data:
            return None
        return message.data

    def submit_resize(self, rows: int, cols: int) -> None:
        if rows <= 0 or cols <= 0:
            return
        with self._state_lock:
            if self._closed:
                return
        self._resize_queue.put(TerminalResizeMessage(rows=rows, cols=cols))

    def read_latest_resize(self) -> Optional[Tuple[int, int]]:
        with self._state_lock:
            if self._closed:
                return None
        latest: Optional[Tuple[int, int]] = None
        while True:
            try:
                message = self._resize_queue.get_nowait()
            except Empty:
                break
            latest = (message.rows, message.cols)
        return latest


class TerminalInputRegistry:
    """execution_id -> 输入会话注册表。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: Dict[str, TerminalInputSession] = {}

    def register_execution(self, execution_id: str) -> TerminalInputSession:
        with self._lock:
            session = self._sessions.get(execution_id)
            if session is None:
                session = TerminalInputSession(execution_id=execution_id)
                self._sessions[execution_id] = session
            return session

    def submit_terminal_input(self, execution_id: str, data: str) -> None:
        session = self.register_execution(execution_id)
        session.submit_input(data)

    def submit_terminal_resize(self, execution_id: str, rows: int, cols: int) -> None:
        session = self.register_execution(execution_id)
        session.submit_resize(rows, cols)

    def get_input_callback(self, execution_id: str) -> Callable[[float], Optional[str]]:
        session = self.register_execution(execution_id)

        def _callback(timeout: float) -> Optional[str]:
            return session.read_input(timeout)

        return _callback

    def get_resize_callback(
        self, execution_id: str
    ) -> Callable[[], Optional[Tuple[int, int]]]:
        session = self.register_execution(execution_id)

        def _callback() -> Optional[Tuple[int, int]]:
            return session.read_latest_resize()

        return _callback

    def unregister_execution(self, execution_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(execution_id, None)
        if session is not None:
            session.close()
