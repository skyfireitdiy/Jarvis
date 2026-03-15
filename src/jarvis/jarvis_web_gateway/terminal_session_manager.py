# -*- coding: utf-8 -*-
"""独立终端会话管理器。

管理与execution无关的独立终端会话，用于实现类似tmux的多标签终端功能。
"""

from __future__ import annotations

import fcntl
import os
import pty
import select
import struct
import subprocess
import termios
import threading
import uuid
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple


@dataclass
class TerminalSession:
    """单个终端会话。"""

    terminal_id: str
    interpreter: str
    working_dir: str
    master_fd: int
    proc: Optional[subprocess.Popen]
    stream_publisher: Optional[Any] = None
    session_id: str = "default"
    _closed: bool = False
    _output_sequence: int = 0
    _sequence_lock: threading.Lock = field(default_factory=threading.Lock)

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

        # 关闭PTY
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
            os.write(self.master_fd, data.encode("utf-8", errors="ignore"))
        except OSError:
            self.close()

    def resize(self, rows: int, cols: int) -> None:
        """调整终端尺寸。"""
        if self.is_closed():
            return
        if rows <= 0 or cols <= 0:
            return
        try:
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
            print(f"[TerminalSession {self.terminal_id}] No stream publisher, skipping output")
            return

        try:
            # base64 编码数据，使其可序列化为 JSON
            import base64
            encoded_data = base64.b64encode(data).decode('utf-8')
            
            # 构建符合前端期望的 WebSocket 消息格式
            # 直接发送 {type: "execution", payload: {...}} 格式
            payload = {
                "event_type": "stdout",  # 前端期望的 event_type
                "data": encoded_data,  # base64 编码的输出数据（字符串）
                "encoded": True,
                "sequence": self.next_sequence(),
                "execution_id": f"terminal_{self.terminal_id}",
            }
            message = {
                "type": "execution",
                "payload": payload
            }
            print(f"[TerminalSession {self.terminal_id}] Publishing output: type={message['type']}, exec_id={payload['execution_id']}, data_len={len(data)}")
            # 直接通过 router 发送消息
            self.stream_publisher.publish(message, session_id=self.session_id)
        except Exception as e:
            print(f"[TerminalSession {self.terminal_id}] Failed to publish output: {e}")


class TerminalSessionManager:
    """独立终端会话管理器。"""

    def __init__(self, max_sessions: int = 5):
        self._max_sessions = max_sessions
        self._lock = threading.RLock()
        self._sessions: Dict[str, TerminalSession] = {}

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
            if len(self._sessions) >= self._max_sessions:
                return None, f"已达到最大终端数量限制（{self._max_sessions}）"

            # 生成terminal_id
            terminal_id = str(uuid.uuid4())[:8]

            try:
                # 创建PTY
                master_fd, slave_fd = pty.openpty()

                # 设置工作目录
                if not os.path.isabs(working_dir):
                    working_dir = os.path.abspath(working_dir)

                # 启动子进程
                env = os.environ.copy()
                if interpreter in ("python", "python2", "python3"):
                    env["PYTHONIOENCODING"] = "utf-8"

                # 构建命令
                # 注意：fish shell 在 PTY 环境中无法正常运行（即使使用 -i 参数）
                # 所以对于 fish shell，fallback 到 bash
                cmd = [interpreter]
                actual_interpreter = interpreter
                if interpreter.endswith('fish'):
                    print("[TerminalSessionManager] Fish shell detected, falling back to bash")
                    cmd = ['bash']
                    actual_interpreter = 'bash'

                proc = subprocess.Popen(
                    cmd,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    cwd=working_dir,
                    env=env,
                    preexec_fn=os.setsid,
                )

                # 关闭slave_fd（子进程已经持有）
                os.close(slave_fd)

                # 创建会话对象
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

                # 启动输出读取线程
                thread = threading.Thread(
                    target=self._read_output,
                    args=(session,),
                    daemon=True,
                    name=f"terminal-{terminal_id}",
                )
                thread.start()

                return terminal_id, None

            except Exception as e:
                # 清理资源
                try:
                    os.close(master_fd)
                except Exception:
                    pass
                try:
                    os.close(slave_fd)
                except Exception:
                    pass
                return None, f"创建终端失败: {str(e)}"

    def _read_output(self, session: TerminalSession) -> None:
        """读取终端输出的线程函数。"""
        print(f"[TerminalSessionManager] Starting output reader for terminal {session.terminal_id}")
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
                    print(f"[TerminalSessionManager] EOF on terminal {session.terminal_id}")
                    break

                output_count += 1
                print(f"[TerminalSessionManager] Read chunk {output_count} ({len(data)} bytes) from terminal {session.terminal_id}")
                print(f"[TerminalSessionManager] Data preview: {data[:100]!r}")
                # 发布输出
                session._publish_output(data)

            except OSError as e:
                print(f"[TerminalSessionManager] OSError on terminal {session.terminal_id}: {e}")
                break
            except Exception as e:
                print(f"[TerminalSessionManager] Exception on terminal {session.terminal_id}: {e}")
                break
        print(f"[TerminalSessionManager] Output reader stopped for terminal {session.terminal_id}")

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
            session = self._sessions.pop(terminal_id, None)
            if session is None:
                return False
            
            # 发送 terminal_closed 消息通知前端
            if session.stream_publisher is not None:
                try:
                    message = {
                        "type": "terminal_closed",
                        "payload": {
                            "terminal_id": terminal_id,
                        },
                    }
                    print(f"[TerminalSessionManager] Sending terminal_closed for {terminal_id}")
                    session.stream_publisher.publish(message, session_id=session.session_id)
                except Exception as e:
                    print(f"[TerminalSessionManager] Failed to send terminal_closed: {e}")
            
            session.close()
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
