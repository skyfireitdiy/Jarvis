# -*- coding: utf-8 -*-
"""会话实时保存守护进程（守护子进程 + 管道方案）。

背景
----
``save_session`` 只在 commit/手动/任务结束时落盘，Agent 进程被意外 kill
（OOM/崩溃/手动 kill）时最近会话会丢失。本模块提供"实时保存 + 自动恢复"：

- 主 Agent 启动时 ``fork`` 一个守护子进程，通过管道把会话快照发过去；
- 守护子进程把最新快照保存在**内存**中（不落盘，避免污染会话目录）；
- 主 Agent 正常退出时发送"正常退出"控制消息，守护子进程清理内存并退出，
  **不落盘**（正常退出路径已由 ``save_session`` 负责落盘）；
- 主 Agent 被意外 kill 时管道写端关闭，守护子进程读到 EOF，判定为意外
  退出，按 ``save_session`` 的格式把内存中的最新快照落盘，供下次恢复。

设计要点
--------
- 快照内容由**主进程**构造（复用 ``SessionManager.build_session_snapshot``），
  守护子进程只负责"存内存 + 写盘"，逻辑极简。
- 落盘使用 ``atomic_write_json``，与 ``save_session`` 完全一致，保证
  ``restore_session_from_file`` 可直接恢复。
- 仅主 Agent（``allow_savesession=True``）启用；Windows 无 ``os.fork``，
  自动降级为不启用（不影响现有功能）。
"""

import json
import os
import struct
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

# 管道消息类型
_MSG_SNAPSHOT = b"S"  # 会话快照（覆盖内存中的最新快照）
_MSG_QUIT = b"Q"  # 正常退出通知（清理内存，不落盘）

# 长度前缀：8 字节无符号大端整数
_LEN_FMT = ">Q"
_LEN_SIZE = struct.calcsize(_LEN_FMT)


class SessionDaemon:
    """父进程侧：管理守护子进程与管道通信。

    仅当 ``os.fork`` 可用时启用；否则 ``start()`` 返回 False，所有发送
    操作变为空操作，Agent 行为退回到"仅 save_session"。
    """

    def __init__(self) -> None:
        self._pid: Optional[int] = None
        self._write_fd: Optional[int] = None
        self._enabled = hasattr(os, "fork")

    @property
    def enabled(self) -> bool:
        """守护进程是否已启用并成功启动。"""
        return self._pid is not None and self._write_fd is not None

    def start(self) -> bool:
        """启动守护子进程。

        返回:
            bool: 是否成功启动（Windows 或异常时返回 False）。
        """
        if not self._enabled:
            return False
        if self.enabled:
            return True
        try:
            read_fd, write_fd = os.pipe()
            pid = os.fork()
            if pid == 0:
                # 子进程：只负责读管道 + 落盘，绝不返回父进程上下文
                self._daemon_loop(read_fd, write_fd)
                # 理论上 _daemon_loop 不会返回；兜底强制退出，避免执行
                # 父进程继承来的 atexit / __del__ 等清理逻辑
                os._exit(0)
            # 父进程：关闭读端，保留写端
            os.close(read_fd)
            self._pid = pid
            self._write_fd = write_fd
            return True
        except Exception:
            # fork/pipe 失败时降级为不启用，不影响主流程
            try:
                if self._write_fd is not None:
                    os.close(self._write_fd)
            except Exception:
                pass
            self._pid = None
            self._write_fd = None
            return False

    def send_snapshot(self, files: List[Dict[str, Any]]) -> bool:
        """把一份会话快照发送给守护子进程（覆盖其内存中的最新快照）。

        参数:
            files: 落盘计划，每项为
                {"path": str, "data": Any, "indent": Optional[int],
                 "use_safe_encoder": bool}

        返回:
            bool: 是否成功发送。
        """
        if not self.enabled:
            return False
        return self._send(_MSG_SNAPSHOT, {"files": files})

    def send_quit(self) -> None:
        """通知守护子进程"正常退出"，令其清理内存且不落盘。

        发送后关闭写端并回收子进程，避免僵尸进程。
        """
        if not self.enabled:
            return
        try:
            self._send(_MSG_QUIT, None)
        except Exception:
            pass
        self._close_and_reap()

    def _send(self, msg_type: bytes, payload: Optional[Dict[str, Any]]) -> bool:
        """按 [类型][长度][JSON] 协议向管道写入一条消息。"""
        write_fd = self._write_fd
        if write_fd is None:
            return False
        try:
            if payload is None:
                body = b""
            else:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            frame = msg_type + struct.pack(_LEN_FMT, len(body)) + body
            os.write(write_fd, frame)
            return True
        except Exception:
            # 管道已关闭（守护进程可能已退出），忽略
            return False

    def _close_and_reap(self) -> None:
        """关闭写端并回收子进程。"""
        if self._write_fd is not None:
            try:
                os.close(self._write_fd)
            except Exception:
                pass
            self._write_fd = None
        if self._pid is not None:
            try:
                os.waitpid(self._pid, 0)
            except Exception:
                pass
            self._pid = None

    # ------------------------------------------------------------------
    # 守护子进程侧
    # ------------------------------------------------------------------
    def _daemon_loop(self, read_fd: int, write_fd: int) -> None:
        """守护子进程主循环：阻塞读管道，EOF 时落盘。

        参数:
            read_fd: 管道读端
            write_fd: 管道写端（子进程需先关闭，否则 EOF 永不触发）
        """
        # 子进程必须关闭写端，否则父进程退出后管道不会 EOF
        try:
            os.close(write_fd)
        except Exception:
            pass

        latest_files: Optional[List[Dict[str, Any]]] = None
        normal_exit = False

        try:
            while True:
                msg_type = self._read_exact(read_fd, 1)
                if msg_type is None:
                    # EOF：父进程（写端）已消失
                    break
                raw_len = self._read_exact(read_fd, _LEN_SIZE)
                if raw_len is None:
                    break
                body_len = struct.unpack(_LEN_FMT, raw_len)[0]
                body = self._read_exact(read_fd, body_len) if body_len else b""
                if body is None:
                    break

                if msg_type == _MSG_QUIT:
                    normal_exit = True
                    break
                if msg_type == _MSG_SNAPSHOT:
                    try:
                        payload = json.loads(body.decode("utf-8"))
                        files = payload.get("files")
                        if isinstance(files, list):
                            latest_files = files
                    except Exception:
                        # 单条快照解析失败不影响后续
                        pass
        except Exception:
            pass
        finally:
            try:
                os.close(read_fd)
            except Exception:
                pass

        # 正常退出：不落盘（正常路径已由 save_session 落盘）
        if normal_exit or not latest_files:
            return

        # 意外退出：把内存中的最新快照落盘
        self._write_files(latest_files)

    @staticmethod
    def _read_exact(fd: int, n: int) -> Optional[bytes]:
        """从 fd 精确读取 n 字节；EOF 时返回 None。"""
        chunks = []
        remaining = n
        while remaining > 0:
            try:
                chunk = os.read(fd, remaining)
            except OSError:
                return None
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    @staticmethod
    def _write_files(files: List[Dict[str, Any]]) -> None:
        """把快照中的文件原子写入磁盘（与 save_session 格式一致）。"""
        # 延迟导入，避免子进程在极早期触发重依赖
        from jarvis.jarvis_utils.utils import atomic_write_json

        try:
            from jarvis.jarvis_agent import SafeEncoder

            safe_default = SafeEncoder().default
        except Exception:
            safe_default = None

        for item in files:
            try:
                path = item.get("path")
                if not path:
                    continue
                data = item.get("data")
                indent = item.get("indent")
                default = safe_default if item.get("use_safe_encoder") else None
                atomic_write_json(
                    path,
                    data,
                    indent=indent,
                    ensure_ascii=False,
                    default=default,
                )
            except Exception:
                # 单个文件写入失败不影响其他文件
                continue


def build_snapshot_files(
    session_file: str, files: List[Any]
) -> List[Dict[str, Any]]:
    """把 ``build_session_snapshot`` 的返回值转换为可 JSON 传输的落盘计划。

    参数:
        session_file: 主会话文件路径（未使用，保留用于扩展）
        files: ``[(path, data, default_encoder), ...]``

    返回:
        [{"path":..., "data":..., "indent":..., "use_safe_encoder":...}, ...]
    """
    # 各文件的缩进与 save_session 保持一致
    plan: List[Dict[str, Any]] = []
    for path, data, default in files:
        name = os.path.basename(path)
        if name.endswith("_state.json") or name.endswith("_tasklist.json"):
            indent: Optional[int] = 2
        else:
            indent = 4
        plan.append(
            {
                "path": path,
                "data": data,
                "indent": indent,
                "use_safe_encoder": default is not None,
            }
        )
    return plan
