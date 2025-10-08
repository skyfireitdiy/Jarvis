# -*- coding: utf-8 -*-
"""
Web STDIO 重定向模块：
- 在 Web 模式下，将 Python 层的标准输出/错误（sys.stdout/sys.stderr）重定向到 WebSocket，通过 WebBridge 广播。
- 适用于工具或第三方库直接使用 print()/stdout/stderr 的输出，从而不经过 PrettyOutput Sink 的场景。

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
            WebBridge.instance().broadcast({
                "type": "stdio",
                "stream": self._stream_name,
                "text": text,
            })
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

    def writelines(self, lines) -> None:
        for ln in lines:
            self.write(ln)

    def __getattr__(self, name: str):
        # 兼容性：必要时委派到原始 stdout/stderr 的属性（尽量避免）
        try:
            return getattr(_original_stdout if self._stream_name == "stdout" else _original_stderr, name)
        except Exception:
            raise AttributeError(name)


def enable_web_stdio_redirect() -> None:
    """启用全局 STDOUT/STDERR 到 WebSocket 的重定向。"""
    global _redirect_enabled
    with _lock:
        if _redirect_enabled:
            return
        try:
            sys.stdout = _WebStreamWrapper("stdout")  # type: ignore[assignment]
            sys.stderr = _WebStreamWrapper("stderr")  # type: ignore[assignment]
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
