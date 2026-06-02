# -*- coding: utf-8 -*-
"""独立终端会话管理器。

管理与execution无关的独立终端会话，用于实现类似tmux的多标签终端功能。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import uuid
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

# Platform-specific imports
if os.name == "nt":
    import queue as _queue
else:
    import fcntl
    import pty
    import select
    import struct
    import termios


@dataclass
class TerminalSession:
    """单个终端会话。"""

    terminal_id: str
    interpreter: str
    working_dir: str
    master_fd: Optional[int] = None  # Unix only
    proc: Optional[subprocess.Popen] = None
    stream_publisher: Optional[Any] = None
    session_id: str = "default"
    _closed: bool = False
    _output_sequence: int = 0
    _sequence_lock: threading.Lock = field(default_factory=threading.Lock)
    # Windows-specific fields
    _output_queue: Optional[Any] = field(default=None)  # queue.Queue on Windows
    _output_thread: Optional[threading.Thread] = field(default=None)

    def next_sequence(self) -> int:
        """获取下一个输出序列号。"""
        with self._sequence_lock:
            self._output_sequence += 1
            return self._output_sequence

    def close(self) -> None:
        """关闭终端会话。"""
        with self._sequence_lock:
            if self._closed:
                return
            self._closed = True

        # 关闭PTY (Unix)
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass

        # 终止进程
        if self.proc is not None:
            try:
                if self.proc.poll() is None:
                    self.proc.terminate()
                    try:
                        self.proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.proc.kill()
                        self.proc.wait()
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass

    def is_closed(self) -> bool:
        """检查会话是否已关闭。"""
        with self._sequence_lock:
            if self._closed:
                return True
            return self.proc is not None and self.proc.poll() is not None

    def write_input(self, data: str) -> None:
        """向终端写入输入。"""
        if self.is_closed():
            return
        try:
            if os.name == "nt":
                # Windows: write to subprocess stdin
                if self.proc is not None and self.proc.stdin is not None:
                    self.proc.stdin.write(data.encode("utf-8", errors="ignore"))
                    self.proc.stdin.flush()
            else:
                # Unix: write to PTY master fd
                if self.master_fd is not None:
                    os.write(self.master_fd, data.encode("utf-8", errors="ignore"))
        except OSError:
            self.close()

    def resize(self, rows: int, cols: int) -> None:
        """调整终端尺寸。"""
        if self.is_closed():
            return
        if rows <= 0 or cols <= 0:
            return
        if os.name == "nt":
            # Windows: resize not supported via subprocess, no-op
            return
        try:
            if self.master_fd is not None:
                fcntl.ioctl(
                    self.master_fd,
                    termios.TIOCSWINSZ,
                    struct.pack("HHHH", rows, cols, 0, 0),
                )
        except Exception:
            pass

    def _publish_output(self, data: bytes) -> None:
        """发布终端输出到WebSocket。"""
        if self.stream_publisher is None:
            print(
                f"[TerminalSession {self.terminal_id}] No stream publisher, skipping output"
            )
            return

        try:
            # base64 编码数据，使其可序列化为 JSON
            import base64

            encoded_data = base64.b64encode(data).decode("utf-8")

            # 构建符合前端期望的 WebSocket 消息格式
            # 直接发送 {type: "execution", payload: {...}} 格式
            payload = {
                "event_type": "stdout",  # 前端期望的 event_type
                "data": encoded_data,  # base64 编码的输出数据（字符串）
                "encoded": True,
                "sequence": self.next_sequence(),
                "execution_id": f"terminal_{self.terminal_id}",
            }
            message = {"type": "execution", "payload": payload}
            print(
                f"[TerminalSession {self.terminal_id}] Publishing output: type={message['type']}, exec_id={payload['execution_id']}, data_len={len(data)}"
            )
            # 直接通过 router 发送消息
            self.stream_publisher.publish(message, session_id=self.session_id)
        except Exception as e:
            print(f"[TerminalSession {self.terminal_id}] Failed to publish output: {e}")


class TerminalSessionManager:
    """独立终端会话管理器。"""

    def __init__(self, max_sessions: Optional[int] = None):
        self._max_sessions = max_sessions
        self._lock = threading.RLock()
        self._sessions: Dict[str, TerminalSession] = {}
        self._closing_sessions: set[str] = set()  # 正在关闭的会话ID集合，防止重复调用

    def create_session(
        self,
        interpreter: str = "bash",
        working_dir: str = ".",
        stream_publisher: Optional[Any] = None,
        session_id: str = "default",
    ) -> Tuple[Optional[str], Optional[str]]:
        """创建新的终端会话。

        Args:
            interpreter: 解释器路径（bash, python等）
            working_dir: 工作目录
            stream_publisher: 流输出发布器
            session_id: WebSocket会话ID

        Returns:
            (terminal_id, error_message)
        """
        with self._lock:
            # 检查会话数量限制
            if (
                self._max_sessions is not None
                and len(self._sessions) >= self._max_sessions
            ):
                return None, f"已达到最大终端数量限制（{self._max_sessions}）"

            # 生成terminal_id
            terminal_id = str(uuid.uuid4())[:8]

            try:
                # 检查解释器是否存在
                if not shutil.which(interpreter):
                    fallback = "cmd.exe" if os.name == "nt" else "bash"
                    print(
                        f"[TerminalSessionManager] Interpreter not found: {interpreter}, falling back to {fallback}"
                    )
                    interpreter = fallback

                # 设置工作目录
                if not os.path.isabs(working_dir):
                    working_dir = os.path.abspath(working_dir)

                if os.name == "nt":
                    return self._create_session_windows(
                        terminal_id,
                        interpreter,
                        working_dir,
                        stream_publisher,
                        session_id,
                    )
                else:
                    return self._create_session_unix(
                        terminal_id,
                        interpreter,
                        working_dir,
                        stream_publisher,
                        session_id,
                    )

            except Exception as e:
                return None, f"创建终端失败: {str(e)}"

    def _create_session_unix(
        self,
        terminal_id: str,
        interpreter: str,
        working_dir: str,
        stream_publisher: Optional[Any],
        session_id: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Unix/Linux: 使用PTY创建终端会话。"""
        master_fd, slave_fd = pty.openpty()

        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        if interpreter in ("python", "python2", "python3"):
            env["PYTHONIOENCODING"] = "utf-8"

        # fish 在 PTY 环境中无法直接启动，可以通过 bash -c exec fish 启动
        if interpreter.endswith("fish"):
            print(
                "[TerminalSessionManager] Fish shell detected, using bash -c exec fish"
            )
            cmd = ["bash", "-c", f"exec {interpreter} -i"]
            actual_interpreter = interpreter
        else:
            cmd = [interpreter]
            actual_interpreter = interpreter

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=working_dir,
                env=env,
                preexec_fn=os.setsid,
            )

            os.close(slave_fd)

            session = TerminalSession(
                terminal_id=terminal_id,
                interpreter=actual_interpreter,
                working_dir=working_dir,
                master_fd=master_fd,
                proc=proc,
                stream_publisher=stream_publisher,
                session_id=session_id,
            )

            self._sessions[terminal_id] = session

            thread = threading.Thread(
                target=self._read_output_unix,
                args=(session,),
                daemon=True,
                name=f"terminal-{terminal_id}",
            )
            thread.start()

            return terminal_id, None

        except Exception as e:
            try:
                os.close(master_fd)
            except Exception:
                pass
            try:
                os.close(slave_fd)
            except Exception:
                pass
            return None, f"创建终端失败: {str(e)}"

    def _create_session_windows(
        self,
        terminal_id: str,
        interpreter: str,
        working_dir: str,
        stream_publisher: Optional[Any],
        session_id: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Windows: 使用subprocess+pipe创建终端会话。"""
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"

        try:
            proc = subprocess.Popen(
                [interpreter],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=working_dir,
                env=env,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )

            output_queue = _queue.Queue()

            session = TerminalSession(
                terminal_id=terminal_id,
                interpreter=interpreter,
                working_dir=working_dir,
                master_fd=None,
                proc=proc,
                stream_publisher=stream_publisher,
                session_id=session_id,
                _output_queue=output_queue,
            )

            self._sessions[terminal_id] = session

            # 启动输出读取线程
            def read_output() -> None:
                while not session.is_closed():
                    try:
                        if proc.stdout is None:
                            break
                        data = proc.stdout.read(4096)
                        if not data:
                            break
                        output_queue.put(data)
                    except Exception:
                        break

            output_thread = threading.Thread(
                target=read_output,
                daemon=True,
                name=f"terminal-reader-{terminal_id}",
            )
            output_thread.start()
            session._output_thread = output_thread

            # 启动发布线程
            publish_thread = threading.Thread(
                target=self._read_output_windows,
                args=(session,),
                daemon=True,
                name=f"terminal-pub-{terminal_id}",
            )
            publish_thread.start()

            return terminal_id, None

        except Exception as e:
            return None, f"创建终端失败: {str(e)}"

    def _read_output_unix(self, session: TerminalSession) -> None:
        """Unix/Linux: 读取PTY输出的线程函数。"""
        assert session.master_fd is not None, "master_fd must be set for Unix sessions"
        print(
            f"[TerminalSessionManager] Starting output reader for terminal {session.terminal_id}"
        )
        output_count = 0
        while not session.is_closed():
            try:
                # 使用select等待数据
                ready, _, _ = select.select([session.master_fd], [], [], 0.1)
                if not ready:
                    continue

                # 读取数据
                data = os.read(session.master_fd, 4096)
                if not data:
                    print(
                        f"[TerminalSessionManager] EOF on terminal {session.terminal_id}"
                    )
                    break

                output_count += 1
                print(
                    f"[TerminalSessionManager] Read chunk {output_count} ({len(data)} bytes) from terminal {session.terminal_id}"
                )
                print(f"[TerminalSessionManager] Data preview: {data[:100]!r}")
                # 发布输出
                session._publish_output(data)

            except OSError as e:
                print(
                    f"[TerminalSessionManager] OSError on terminal {session.terminal_id}: {e}"
                )
                break
            except Exception as e:
                print(
                    f"[TerminalSessionManager] Exception on terminal {session.terminal_id}: {e}"
                )
                break
        print(
            f"[TerminalSessionManager] Output reader stopped for terminal {session.terminal_id}"
        )

        # 检查进程退出状态
        if session.proc is not None:
            return_code = session.proc.poll()
            print(f"[TerminalSessionManager] Process exit code: {return_code}")

        # 进程结束，清理会话
        self.close_session(session.terminal_id)

    def _read_output_windows(self, session: TerminalSession) -> None:
        """Windows: 从queue读取输出并发布到WebSocket。"""
        assert session._output_queue is not None, (
            "output_queue must be set for Windows sessions"
        )
        print(
            f"[TerminalSessionManager] Starting Windows output publisher for terminal {session.terminal_id}"
        )
        while not session.is_closed():
            try:
                data = session._output_queue.get(timeout=0.1)
                if data:
                    session._publish_output(data)
            except Exception:  # queue.Empty or timeout
                continue
        print(
            f"[TerminalSessionManager] Windows output publisher stopped for terminal {session.terminal_id}"
        )

        # 检查进程退出状态
        if session.proc is not None:
            return_code = session.proc.poll()
            print(f"[TerminalSessionManager] Process exit code: {return_code}")

        # 进程结束，清理会话
        self.close_session(session.terminal_id)

    def write_input(self, terminal_id: str, data: str) -> bool:
        """向终端写入输入。

        Args:
            terminal_id: 终端ID
            data: 输入数据

        Returns:
            是否成功
        """
        with self._lock:
            session = self._sessions.get(terminal_id)
            if session is None:
                return False
            session.write_input(data)
            return True

    def resize(self, terminal_id: str, rows: int, cols: int) -> bool:
        """调整终端尺寸。

        Args:
            terminal_id: 终端ID
            rows: 行数
            cols: 列数

        Returns:
            是否成功
        """
        with self._lock:
            session = self._sessions.get(terminal_id)
            if session is None:
                return False
            session.resize(rows, cols)
            return True

    def close_session(self, terminal_id: str) -> bool:
        """关闭终端会话。

        Args:
            terminal_id: 终端ID

        Returns:
            是否成功
        """
        with self._lock:
            # 检查是否已经在关闭过程中（防止重复调用）
            if terminal_id in self._closing_sessions:
                return False

            session = self._sessions.pop(terminal_id, None)
            if session is None:
                # 会话不存在，从关闭集合中移除
                self._closing_sessions.discard(terminal_id)
                return False

            # 标记为正在关闭
            self._closing_sessions.add(terminal_id)

            # 发送 terminal_closed 消息通知前端
            if session.stream_publisher is not None:
                try:
                    message = {
                        "type": "terminal_closed",
                        "payload": {
                            "terminal_id": terminal_id,
                        },
                    }
                    print(
                        f"[TerminalSessionManager] Sending terminal_closed for {terminal_id}"
                    )
                    session.stream_publisher.publish(
                        message, session_id=session.session_id
                    )
                except Exception as e:
                    print(
                        f"[TerminalSessionManager] Failed to send terminal_closed: {e}"
                    )

            session.close()

            # 从关闭集合中移除
            self._closing_sessions.discard(terminal_id)
            return True

    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有活跃的终端会话。

        Returns:
            会话信息列表
        """
        with self._lock:
            sessions = []
            for terminal_id, session in self._sessions.items():
                sessions.append(
                    {
                        "terminal_id": terminal_id,
                        "interpreter": session.interpreter,
                        "working_dir": session.working_dir,
                        "is_closed": session.is_closed(),
                    }
                )
            return sessions

    def get_session(self, terminal_id: str) -> Optional[TerminalSession]:
        """获取终端会话。

        Args:
            terminal_id: 终端ID

        Returns:
            会话对象或None
        """
        with self._lock:
            return self._sessions.get(terminal_id)

    def cleanup(self) -> None:
        """清理所有会话。"""
        with self._lock:
            for session in self._sessions.values():
                session.close()
            self._sessions.clear()
