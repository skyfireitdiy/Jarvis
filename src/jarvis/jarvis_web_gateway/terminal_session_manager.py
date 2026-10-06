# -*- coding: utf-8 -*-
"""独立终端会话管理器。

管理与execution无关的独立终端会话，用于实现类似tmux的多标签终端功能。
"""

from __future__ import annotations


from jarvis.jarvis_utils.exception_utils import save_exception
import os
import shutil
from collections import deque
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
    owner_id: str = ""
    access_acl: Dict[str, List[str]] = field(default_factory=dict)
    # 已接管（attach）本会话的用户 session_id 集合，用于把实时输出推送给
    # 所有有权限的观看者（owner / ACL 用户 / 被放行的 admin 用户）
    attached_session_ids: set = field(default_factory=set)
    created_at: float = field(default_factory=lambda: __import__("time").time())
    _closed: bool = False
    _output_sequence: int = 0
    _sequence_lock: threading.Lock = field(default_factory=threading.Lock)
    # 输出环形缓冲（断开期间缓存输出，重连后可回放），容量约 1MB
    _output_buffer: deque = field(default_factory=lambda: deque(maxlen=1024 * 1024))
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
                except Exception as e:
                    save_exception(
                        e,
                        module="jarvis_web_gateway.terminal_session_manager",
                        function="close",
                    )
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
        except Exception as e:
            save_exception(
                e,
                module="jarvis_web_gateway.terminal_session_manager",
                function="resize",
            )
            pass

    def _get_access_session_ids(self) -> List[str]:
        """返回有权接收本终端实时输出的 WebSocket 会话ID列表。

        包含 owner 与被分享（read/interact）用户，使实时输出能推送给
        所有有权限的用户（而不只是 owner），修复被分享用户看不到
        终端实时内容的问题。
        """
        ids: List[str] = []
        if self.owner_id:
            ids.append(f"session_{self.owner_id}")
        acl = self.access_acl or {}
        for uid in acl.get("interact", []) + acl.get("read", []):
            if uid and f"session_{uid}" not in ids:
                ids.append(f"session_{uid}")
        # 已接管本会话的用户（含被放行的 admin 用户），使其实时输出也能送达
        for sid in self.attached_session_ids:
            if sid and sid not in ids:
                ids.append(sid)
        # 兼容子节点终端：创建时未传 owner_id（owner_id 为空），此时回退到
        # self.session_id，避免 _get_access_session_ids 为空导致输出无人接收
        # （表现为"只有标签和空的 xterm"）
        if not ids and self.session_id and self.session_id != "default":
            ids.append(self.session_id)
        return ids

    def _publish_output(self, data: bytes) -> None:
        """发布终端输出到WebSocket。"""
        if self.stream_publisher is None:
            print(
                f"[TerminalSession {self.terminal_id}] No stream publisher, skipping output"
            )
            return

        # 写入输出环形缓冲，供断开重连后回放
        self._output_buffer.append(data)

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
            # 推送给 owner 与被分享（read/interact）用户，使所有有权限的用户
            # 都能收到实时输出（而不只是 owner 的 session_id）
            for sid in self._get_access_session_ids():
                self.stream_publisher.publish(message, session_id=sid)
        except Exception as e:
            print(f"[TerminalSession {self.terminal_id}] Failed to publish output: {e}")

    def get_output_buffer(self) -> List[bytes]:
        """获取输出环形缓冲中的全部数据（按时间顺序）。

        用于断开重连后回放输出。返回的是原始 bytes 列表，调用方需自行
        base64 编码后按前端期望的格式发送。
        """
        with self._sequence_lock:
            return list(self._output_buffer)


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
        owner_id: str = "",
    ) -> Tuple[Optional[str], Optional[str]]:
        """创建新的终端会话。

        Args:
            interpreter: 解释器路径（bash, python等）
            working_dir: 工作目录
            stream_publisher: 流输出发布器
            session_id: WebSocket会话ID
            owner_id: 会话所有者用户ID

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
                        owner_id,
                    )
                else:
                    return self._create_session_unix(
                        terminal_id,
                        interpreter,
                        working_dir,
                        stream_publisher,
                        session_id,
                        owner_id,
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
        owner_id: str = "",
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
                owner_id=owner_id,
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
            except Exception as inner_e:
                save_exception(
                    inner_e,
                    module="jarvis_web_gateway.terminal_session_manager",
                    function="_create_session_unix",
                )
                pass
            try:
                os.close(slave_fd)
            except Exception as inner_e:
                save_exception(
                    inner_e,
                    module="jarvis_web_gateway.terminal_session_manager",
                    function="_create_session_unix",
                )
                pass
            return None, f"创建终端失败: {str(e)}"

    def _create_session_windows(
        self,
        terminal_id: str,
        interpreter: str,
        working_dir: str,
        stream_publisher: Optional[Any],
        session_id: str,
        owner_id: str = "",
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
                owner_id=owner_id,
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

    def list_sessions_for_user(self, session_id: str) -> List[Dict[str, Any]]:
        """列出指定用户（WebSocket会话ID）可访问的活跃终端会话。

        返回该用户拥有的会话 + 被分享给该用户的会话（带 access 级别）。

        Args:
            session_id: WebSocket会话ID（即用户标识）

        Returns:
            会话信息列表，含 session_id/created_at/access 等归属与访问信息
        """
        with self._lock:
            sessions = []
            for terminal_id, session in self._sessions.items():
                access = self._access_level(session, session_id)
                if access is None:
                    continue
                sessions.append(
                    {
                        "terminal_id": terminal_id,
                        "interpreter": session.interpreter,
                        "working_dir": session.working_dir,
                        "is_closed": session.is_closed(),
                        "session_id": session.session_id,
                        "created_at": session.created_at,
                        "owner_id": session.owner_id,
                        "access": access,
                        "access_acl": session.access_acl or {},
                    }
                )
            return sessions

    def _access_level(self, session: TerminalSession, user_id: str) -> Optional[str]:
        """计算用户对会话的访问级别。

        兼容 ``session_{user_id}`` 格式的会话ID，自动提取真实 user_id 进行匹配；
        system 用户与 admin 用户视为 owner 放行。

        Returns:
            "owner" / "interact" / "read" / None（无访问权限）
        """
        # 兼容 session_{user_id} 格式，提取真实 user_id
        if user_id and user_id.startswith("session_"):
            user_id = user_id[len("session_") :]
        if not user_id:
            return None
        # system 用户放行
        if user_id == "system":
            return "owner"
        # admin 用户放行
        if self._is_admin_user(user_id):
            return "owner"
        if session.owner_id and user_id == session.owner_id:
            return "owner"
        acl = session.access_acl or {}
        if user_id in acl.get("interact", []):
            return "interact"
        if user_id in acl.get("read", []):
            return "read"
        return None

    def _is_admin_user(self, user_id: str) -> bool:
        """判断用户是否为 admin（通过 UserManager 查询）。"""
        try:
            from jarvis.jarvis_utils.config import get_data_dir
            from jarvis.jarvis_web_gateway.user_manager import UserManager

            user_mgr = UserManager(get_data_dir())
            user = user_mgr.get_user(user_id)
            return bool(user and user.get("is_admin"))
        except Exception:
            return False

    def get_all_admin_session_ids(self) -> List[str]:
        """返回所有 admin 用户的 WebSocket session_id 列表。

        用于终端创建/关闭事件广播：admin 用户经 _access_level 放行（视为
        owner），能看到所有终端，因此终端事件应实时推送给所有在线的 admin 用户，
        使其他设备（管理员）能实时看到新终端出现/关闭。
        """
        try:
            from jarvis.jarvis_utils.config import get_data_dir
            from jarvis.jarvis_web_gateway.user_manager import UserManager

            user_mgr = UserManager(get_data_dir())
            sids: List[str] = []
            for u in user_mgr.list_users(limit=100000):
                if u.get("is_admin"):
                    uid = u.get("user_id")
                    if uid:
                        sids.append(f"session_{uid}")
            return sids
        except Exception:
            return []

    def _get_admin_user_id(self) -> Optional[str]:
        """获取 admin 用户的 user_id（用于 set_access_acl 过滤）。"""
        try:
            from jarvis.jarvis_utils.config import get_data_dir
            from jarvis.jarvis_web_gateway.user_manager import UserManager

            user_mgr = UserManager(get_data_dir())
            admin_user = user_mgr.get_user_by_username("admin")
            return admin_user["user_id"] if admin_user else None
        except Exception:
            return None

    def attach_session(self, terminal_id: str, session_id: str) -> Optional[str]:
        """将终端会话接管/关联到指定用户（WebSocket会话ID）。

        校验会话归属：仅当会话属于该用户（owner）或被分享给该用户
        （read/interact）时才允许接管，防止越权访问他人会话。

        Args:
            terminal_id: 终端ID
            session_id: WebSocket会话ID（即用户标识，可为 session_{user_id} 格式）

        Returns:
            access 级别字符串（"owner"/"interact"/"read"），无权限或不存在时返回 None
        """
        with self._lock:
            session = self._sessions.get(terminal_id)
            if session is None:
                return None
            access = self._access_level(session, session_id)
            if access is not None:
                # 记录已接管本会话的用户，使 _get_access_session_ids 能把
                # 实时输出推送给所有有权限的观看者（含被放行的 admin 用户）
                session.attached_session_ids.add(session_id)
            return access

    def check_access(
        self, terminal_id: str, user_id: str, need_interact: bool
    ) -> Optional[str]:
        """校验用户对会话的访问级别。

        Args:
            terminal_id: 终端ID
            user_id: 用户ID
            need_interact: 是否需要交互级别（兼容参数，返回值为实际访问级别）

        Returns:
            access 级别字符串（"owner"/"interact"/"read"），无权限或不存在时返回 None
        """
        with self._lock:
            session = self._sessions.get(terminal_id)
            if session is None:
                return None
            return self._access_level(session, user_id)

    def set_access_acl(
        self, terminal_id: str, owner_id: str, acl: Dict[str, List[str]]
    ) -> bool:
        """设置会话的访问控制列表（仅 owner 可操作）。

        自动过滤 owner 自身与 admin 用户（这两个用户对会话有完全控制权限）。

        Args:
            terminal_id: 终端ID
            owner_id: 操作者用户ID（须为会话 owner）
            acl: 访问控制列表 {read: [...], interact: [...]}

        Returns:
            是否设置成功
        """
        with self._lock:
            session = self._sessions.get(terminal_id)
            if session is None:
                return False
            if not session.owner_id or session.owner_id != owner_id:
                return False
            # 过滤 owner 自身与 admin 用户，去重
            admin_user_id = self._get_admin_user_id()
            normalized = {"read": [], "interact": []}
            for level in ("read", "interact"):
                users = acl.get(level, []) or []
                seen = set()
                for u in users:
                    if not u or u == session.owner_id or u in seen:
                        continue
                    if admin_user_id and u == admin_user_id:
                        continue
                    seen.add(u)
                    normalized[level].append(u)
            session.access_acl = normalized
            return True

    def get_session_info(self, terminal_id: str) -> Optional[Dict[str, Any]]:
        """获取会话信息（含 owner 与 ACL）。

        Args:
            terminal_id: 终端ID

        Returns:
            会话信息字典或None
        """
        with self._lock:
            session = self._sessions.get(terminal_id)
            if session is None:
                return None
            return {
                "terminal_id": terminal_id,
                "interpreter": session.interpreter,
                "working_dir": session.working_dir,
                "is_closed": session.is_closed(),
                "session_id": session.session_id,
                "created_at": session.created_at,
                "owner_id": session.owner_id,
                "access_acl": session.access_acl or {},
            }

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
