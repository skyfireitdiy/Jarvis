# -*- coding: utf-8 -*-
"""
Web STDIO 重定向模块：
- 在 Web 模式下，将 Python 层的标准输出/错误（sys.stdout/sys.stderr）重定向到 WebSocket，通过 WebBridge 广播。
- 适用于工具或第三方库直接使用 PrettyOutput.auto_print()/stdout/stderr 的输出，从而不经过 PrettyOutput Sink 的场景。

注意：
- 这是进程级重定向，可能带来重复输出（PrettyOutput 已通过 Sink 广播一次，console.print 也会走到 stdout）。若需要避免重复，可在前端针对 'stdio' 类型进行独立显示或折叠。
- 对于子进程输出（subprocess），通常由调用方决定是否捕获和打印；若直接透传到父进程的 stdout/stderr，也会被此重定向捕获。

前端消息结构（通过 WebBridge.broadcast）：
  { "type": "stdio", "stream": "stdout" | "stderr", "text": "..." }

使用：
  from jarvis.jarvis_agent.stdio_redirect import enable_web_stdio_redirect, disable_web_stdio_redirect
  enable_web_stdio_redirect()
  # ... 运行期间输出将通过 WS 广播 ...
  disable_web_stdio_redirect()
"""

from __future__ import annotations

import sys
import threading
from typing import Any, List
from typing import Optional

from jarvis.jarvis_agent.web_bridge import WebBridge

_original_stdout = sys.stdout
_original_stderr = sys.stderr
_redirect_enabled = False
_lock = threading.Lock()


class _WebStreamWrapper:
    """文件类兼容包装器，将 write() 的内容通过 WebBridge 广播。"""

    def __init__(self, stream_name: str) -> None:
        self._stream_name = stream_name
        try:
            self._encoding = getattr(_original_stdout, "encoding", "utf-8")
        except Exception:
            self._encoding = "utf-8"

    def write(self, s: object) -> int:
        try:
            text = s if isinstance(s, str) else str(s)
        except Exception:
            text = repr(s)
        try:
            WebBridge.instance().broadcast(
                {
                    "type": "stdio",
                    "stream": self._stream_name,
                    "text": text,
                }
            )
        except Exception:
            # 广播异常不影响主流程
            pass
        # 返回写入长度以兼容部分调用方
        try:
            return len(text)
        except Exception:
            return 0

    def flush(self) -> None:
        # 无需实际刷新；保持接口兼容
        pass

    def isatty(self) -> bool:
        return False

    @property
    def encoding(self) -> str:
        return self._encoding

    def writelines(self, lines: List[str]) -> None:
        for ln in lines:
            self.write(ln)

    def __getattr__(self, name: str) -> Any:
        # 兼容性：必要时委派到原始 stdout/stderr 的属性（尽量避免）
        try:
            return getattr(
                _original_stdout if self._stream_name == "stdout" else _original_stderr,
                name,
            )
        except Exception:
            raise AttributeError(name)


def enable_web_stdio_redirect() -> None:
    """启用全局 STDOUT/STDERR 到 WebSocket 的重定向。"""
    global _redirect_enabled
    with _lock:
        if _redirect_enabled:
            return
        try:
            sys.stdout = _WebStreamWrapper("stdout")
            sys.stderr = _WebStreamWrapper("stderr")
            _redirect_enabled = True
        except Exception:
            # 回退：保持原始输出
            sys.stdout = _original_stdout
            sys.stderr = _original_stderr
            _redirect_enabled = False


def disable_web_stdio_redirect() -> None:
    """禁用全局 STDOUT/STDERR 重定向，恢复原始输出。"""
    global _redirect_enabled
    with _lock:
        try:
            sys.stdout = _original_stdout
            sys.stderr = _original_stderr
        except Exception:
            pass
        _redirect_enabled = False


# ---------------------------
# Web STDIN 重定向（浏览器 -> 后端）
# ---------------------------
# 目的：
# - 将前端 xterm 的按键数据通过 WS 送回服务端，并作为 sys.stdin 的数据源
# - 使得 Python 层的 input()/sys.stdin.readline() 等可以从浏览器获得输入
# - 仅适用于部分交互式场景（非真正 PTY 行为），可满足基础行缓冲输入
from queue import Queue  # noqa: E402

_original_stdin = sys.stdin
_stdin_enabled = False
_stdin_wrapper: Optional[_WebInputWrapper] = None


class _WebInputWrapper:
    """文件类兼容包装器：作为 sys.stdin 的替身，从队列中读取浏览器送来的数据。"""

    def __init__(self) -> None:
        self._queue: "Queue[str]" = Queue()
        self._buffer: str = ""
        self._lock = threading.Lock()
        try:
            self._encoding = getattr(_original_stdin, "encoding", "utf-8")
        except Exception:
            self._encoding = "utf-8"

    # 外部注入：由 WebSocket 端点调用
    def feed(self, data: str) -> None:
        try:
            s = data if isinstance(data, str) else str(data)
        except Exception:
            s = repr(data)
        # 将回车转换为换行，方便基于 readline 的读取
        s = s.replace("\r", "\n")
        self._queue.put_nowait(s)

    # 基础读取：尽可能兼容常用调用
    def read(self, size: int = -1) -> str:
        # size < 0 表示尽可能多地读取（直到当前缓冲区内容）
        if size == 0:
            return ""

        while True:
            with self._lock:
                if size > 0 and len(self._buffer) >= size:
                    out = self._buffer[:size]
                    self._buffer = self._buffer[size:]
                    return out
                if size < 0 and self._buffer:
                    out = self._buffer
                    self._buffer = ""
                    return out
            # 需要更多数据，阻塞等待
            try:
                chunk = self._queue.get(timeout=None)
            except Exception:
                chunk = ""
            if not isinstance(chunk, str):
                chunk = str(chunk)  # type: ignore
            with self._lock:
                self._buffer += chunk

    def readline(self, size: int = -1) -> str:
        # 读取到换行符为止（包含换行），可选 size 限制
        while True:
            with self._lock:
                idx = self._buffer.find("\n")
                if idx != -1:
                    # 找到换行
                    end_index = idx + 1
                    if size > 0:
                        end_index = min(end_index, size)
                    out = self._buffer[:end_index]
                    self._buffer = self._buffer[end_index:]
                    return out
                # 未找到换行，但如果指定了 size 且缓冲已有足够数据，则返回
                if size > 0 and len(self._buffer) >= size:
                    out = self._buffer[:size]
                    self._buffer = self._buffer[size:]
                    return out
            # 更多数据
            try:
                chunk = self._queue.get(timeout=None)
            except Exception:
                chunk = ""
            if not isinstance(chunk, str):
                chunk = str(chunk)  # type: ignore
            with self._lock:
                self._buffer += chunk

    def readlines(self, hint: int = -1) -> List[str]:
        lines = []
        total = 0
        while True:
            ln = self.readline()
            if not ln:
                break
            lines.append(ln)
            total += len(ln)
            if hint > 0 and total >= hint:
                break
        return lines

    def writable(self) -> bool:
        return False

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        # 伪装为 TTY，可改善部分库的行为（注意并非真正 PTY）
        return True

    @property
    def encoding(self) -> str:
        return self._encoding

    def __getattr__(self, name: str) -> Any:
        # 尽量代理到原始 stdin 的属性以增强兼容性
        try:
            return getattr(_original_stdin, name)
        except Exception:
            raise AttributeError(name)


def enable_web_stdin_redirect() -> None:
    """启用 Web STDIN 重定向：将 sys.stdin 替换为浏览器数据源。"""
    global _stdin_enabled, _stdin_wrapper, _original_stdin
    with _lock:
        if _stdin_enabled:
            return
        try:
            # 记录原始 stdin（若尚未记录）
            if "_original_stdin" not in globals() or _original_stdin is None:
                _original_stdin = sys.stdin
            _stdin_wrapper = _WebInputWrapper()
            sys.stdin = _stdin_wrapper
            _stdin_enabled = True
        except Exception:
            # 回退：保持原始输入
            try:
                sys.stdin = _original_stdin
            except Exception:
                pass
            _stdin_enabled = False


def disable_web_stdin_redirect() -> None:
    """禁用 Web STDIN 重定向，恢复原始输入。"""
    global _stdin_enabled, _stdin_wrapper
    with _lock:
        try:
            sys.stdin = _original_stdin
        except Exception:
            pass
        _stdin_wrapper = None
        _stdin_enabled = False


def feed_web_stdin(data: str) -> None:
    """向 Web STDIN 注入数据（由 WebSocket /stdio 端点调用）。"""
    try:
        if _stdin_enabled and _stdin_wrapper is not None:
            _stdin_wrapper.feed(data)
    except Exception:
        # 注入失败不影响主流程
        pass
