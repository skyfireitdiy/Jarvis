# -*- coding: utf-8 -*-
"""execute_script 中断后补发 tool_stream_end 测试

对应 NLSpec：.jarvis/.df/specs/interrupt-close-xterm.md

根因：前端 execution 终端只在收到 ``tool_stream_end`` 时销毁 xterm；
Unix 交互式 PTY 中断分支直接 return 未发送该消息，导致 xterm 一直挂起。

覆盖点：
- Unix 交互式 PTY：无超时 / 有超时两条中断分支都补发 ``reason="interrupted"``
- Windows PTY：中断后补发 ``reason="interrupted"``（而非 completed/error）
- 幂等：同一 execution 只发送一次 ``tool_stream_end``
- 正常完成/超时/异常路径行为不变（reason 不被篡改）
"""
import sys
import threading
import time
from typing import Any, Dict, List, Optional

import pytest

from jarvis.jarvis_tools import execute_script as execute_script_module
from jarvis.jarvis_tools.execute_script import ExecutionStreamPublisher
from jarvis.jarvis_tools.execute_script import ScriptTool


class _Recorder(ExecutionStreamPublisher):
    """记录所有发布的执行流事件。"""

    def __init__(self) -> None:
        self.messages: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def publish(
        self, message: Dict[str, Any], session_id: Optional[str] = None
    ) -> None:
        del session_id
        with self._lock:
            self.messages.append(dict(message))

    def types(self) -> List[str]:
        return [m.get("message_type") for m in self.messages]

    def ends(self) -> List[Dict[str, Any]]:
        return [m for m in self.messages if m.get("message_type") == "tool_stream_end"]


def _arm_interrupt_after(monkeypatch, delay: float = 0.3) -> None:
    """在 delay 秒后置位中断标志，模拟用户点击「中断」。"""
    from jarvis.jarvis_utils import globals as jarvis_globals

    def _trigger() -> None:
        time.sleep(delay)
        jarvis_globals.set_interrupt(True)

    threading.Thread(target=_trigger, daemon=True).start()


@pytest.fixture(autouse=True)
def _reset_interrupt():
    from jarvis.jarvis_utils import globals as jarvis_globals

    jarvis_globals.set_interrupt(False)
    yield
    jarvis_globals.set_interrupt(False)


# ---------------------------------------------------------------------------
# Unix 交互式 PTY
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="Unix PTY 路径")
def test_unix_interrupt_without_timeout_sends_tool_stream_end(monkeypatch):
    """无超时分支：中断后必须补发 tool_stream_end(reason=interrupted)。"""
    _arm_interrupt_after(monkeypatch)
    recorder = _Recorder()

    tool = ScriptTool()
    result = tool._execute_on_unix_interactive_pty(
        argv=["bash", "-c", "sleep 30"],
        env={"TERM": "xterm-256color", "PATH": "/usr/bin:/bin"},
        get_timeout=lambda: None,
        stream_publisher=recorder,
        session_id="s1",
        execution_id="exec-1",
    )

    assert result["success"] is False
    assert "中断" in result["stderr"]
    ends = recorder.ends()
    assert len(ends) == 1, f"应只发送一次 tool_stream_end，实际 {recorder.types()}"
    end = ends[0]
    assert end["reason"] == "interrupted"
    assert end["execution_id"] == "exec-1"
    assert end["stream"] == "tty"
    assert isinstance(end["exit_code"], int)
    assert "tool_stream_start" in recorder.types()


@pytest.mark.skipif(sys.platform == "win32", reason="Unix PTY 路径")
def test_unix_interrupt_with_timeout_sends_tool_stream_end(monkeypatch):
    """有超时分支：中断后同样补发 tool_stream_end(reason=interrupted)。"""
    _arm_interrupt_after(monkeypatch)
    recorder = _Recorder()

    tool = ScriptTool()
    result = tool._execute_on_unix_interactive_pty(
        argv=["bash", "-c", "sleep 30"],
        env={"TERM": "xterm-256color", "PATH": "/usr/bin:/bin"},
        get_timeout=lambda: 60,
        stream_publisher=recorder,
        session_id="s1",
        execution_id="exec-2",
    )

    assert result["success"] is False
    assert "中断" in result["stderr"]
    ends = recorder.ends()
    assert len(ends) == 1, f"应只发送一次 tool_stream_end，实际 {recorder.types()}"
    assert ends[0]["reason"] == "interrupted"
    assert ends[0]["execution_id"] == "exec-2"


@pytest.mark.skipif(sys.platform == "win32", reason="Unix PTY 路径")
def test_unix_interrupt_end_is_idempotent(monkeypatch):
    """中断与进程自然结束几乎同时发生时，tool_stream_end 只发一次。"""
    recorder = _Recorder()
    tool = ScriptTool()

    # 进程几乎立刻结束，同时中断标志已置位：两条路径都可能想发结束消息
    from jarvis.jarvis_utils import globals as jarvis_globals

    jarvis_globals.set_interrupt(True)
    result = tool._execute_on_unix_interactive_pty(
        argv=["bash", "-c", "true"],
        env={"TERM": "xterm-256color", "PATH": "/usr/bin:/bin"},
        get_timeout=lambda: None,
        stream_publisher=recorder,
        session_id="s1",
        execution_id="exec-3",
    )

    assert isinstance(result, dict)
    ends = recorder.ends()
    assert len(ends) == 1, f"tool_stream_end 应只发送一次，实际 {recorder.types()}"


@pytest.mark.skipif(sys.platform == "win32", reason="Unix PTY 路径")
def test_unix_normal_completion_reason_unchanged():
    """正常完成路径不受影响：reason 仍为 completed。"""
    recorder = _Recorder()
    tool = ScriptTool()
    result = tool._execute_on_unix_interactive_pty(
        argv=["bash", "-c", "echo hi"],
        env={"TERM": "xterm-256color", "PATH": "/usr/bin:/bin"},
        get_timeout=lambda: None,
        stream_publisher=recorder,
        session_id="s1",
        execution_id="exec-4",
    )

    assert result["success"] is True
    ends = recorder.ends()
    assert len(ends) == 1
    assert ends[0]["reason"] == "completed"
    assert ends[0]["exit_code"] == 0


@pytest.mark.skipif(sys.platform == "win32", reason="Unix PTY 路径")
def test_unix_timeout_reason_unchanged():
    """超时路径不受影响：reason 仍为 timeout。"""
    recorder = _Recorder()
    tool = ScriptTool()
    result = tool._execute_on_unix_interactive_pty(
        argv=["bash", "-c", "sleep 30"],
        env={"TERM": "xterm-256color", "PATH": "/usr/bin:/bin"},
        get_timeout=lambda: 0.5,
        stream_publisher=recorder,
        session_id="s1",
        execution_id="exec-5",
    )

    assert result["success"] is False
    assert "超时" in result["stderr"]
    ends = recorder.ends()
    assert len(ends) == 1
    assert ends[0]["reason"] == "timeout"


# ---------------------------------------------------------------------------
# Windows PTY（用假的 winpty.PtyProcess 驱动，可在 Unix 上运行）
# ---------------------------------------------------------------------------


class _FakePtyProcess:
    """模拟 winpty.PtyProcess：read 阻塞直到被 terminate。"""

    def __init__(self) -> None:
        self._alive = True
        self._terminated = threading.Event()
        self.exitstatus = None
        self.returncode = None

    def isalive(self) -> bool:
        return self._alive

    def read(self, size: int) -> str:
        del size
        self._terminated.wait(0.05)
        if not self._alive:
            raise EOFError()
        return ""

    def write(self, data: str) -> None:
        del data

    def set_size(self, cols: int, rows: int) -> None:
        del cols, rows

    def terminate(self) -> None:
        self._alive = False
        self.exitstatus = -2
        self.returncode = -2
        self._terminated.set()

    def kill(self) -> None:
        self.terminate()

    def wait(self) -> None:
        self._terminated.wait(1)


def _install_fake_winpty(monkeypatch) -> _FakePtyProcess:
    fake_proc = _FakePtyProcess()

    class _FakePtyProcessCls:
        @staticmethod
        def spawn(argv, cwd=None, env=None):
            del argv, cwd, env
            return fake_proc

    fake_module = type(sys)("winpty")
    fake_module.PtyProcess = _FakePtyProcessCls  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "winpty", fake_module)
    return fake_proc


@pytest.mark.skipif(sys.platform == "win32", reason="用假 winpty 在 Unix 上验证逻辑")
def test_windows_interrupt_sends_tool_stream_end(monkeypatch):
    """Windows PTY 中断后补发 tool_stream_end(reason=interrupted)。"""
    _install_fake_winpty(monkeypatch)
    _arm_interrupt_after(monkeypatch)
    recorder = _Recorder()

    tool = ScriptTool()
    result = tool._execute_on_windows_interactive_pty(
        argv=["powershell", "-File", "x.ps1"],
        env={},
        get_timeout=lambda: None,
        stream_publisher=recorder,
        session_id="s1",
        execution_id="exec-win-1",
    )

    assert result["success"] is False
    assert "中断" in result["stderr"]
    ends = recorder.ends()
    assert len(ends) == 1, f"应只发送一次 tool_stream_end，实际 {recorder.types()}"
    assert ends[0]["reason"] == "interrupted"
    assert ends[0]["execution_id"] == "exec-win-1"


@pytest.mark.skipif(sys.platform == "win32", reason="用假 winpty 在 Unix 上验证逻辑")
def test_windows_normal_completion_reason_unchanged(monkeypatch):
    """Windows PTY 正常完成路径不受影响：reason 为 completed。"""
    fake_proc = _install_fake_winpty(monkeypatch)
    recorder = _Recorder()

    def _finish() -> None:
        time.sleep(0.2)
        fake_proc.exitstatus = 0
        fake_proc.returncode = 0
        fake_proc._alive = False
        fake_proc._terminated.set()

    threading.Thread(target=_finish, daemon=True).start()

    tool = ScriptTool()
    result = tool._execute_on_windows_interactive_pty(
        argv=["powershell", "-File", "x.ps1"],
        env={},
        get_timeout=lambda: None,
        stream_publisher=recorder,
        session_id="s1",
        execution_id="exec-win-2",
    )

    assert result["success"] is True
    ends = recorder.ends()
    assert len(ends) == 1
    assert ends[0]["reason"] == "completed"


def test_module_exports_interrupt_reason_constant():
    """中断 reason 常量固定为 interrupted（消息契约）。"""
    assert execute_script_module.INTERRUPT_REASON == "interrupted"
