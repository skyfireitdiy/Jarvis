"""通用 LSP WebSocket ↔ 子进程 stdio 桥接。

本模块对具体语言**完全无感知**：它只负责
    1. 按 ``server_id`` 从 :mod:`jarvis.jarvis_web_gateway.lsp_registry` 取清单，
       用清单里的 ``command`` / ``args`` 启动语言服务器进程；
    2. 把浏览器 WebSocket 收到的文本消息按 LSP 分帧规则写入子进程 stdin；
    3. 把子进程 stdout 按 LSP 分帧规则解析出的每条消息原样发回 WebSocket。

**桥接层不解析 JSON-RPC 语义**（不关心 id / method / params），纯字节转发，
因此新增语言无需改动本文件。

LSP 分帧格式（base protocol）::

    Content-Length: <N>\r\n
    [Content-Type: ...]\r\n
    \r\n
    <N 字节 UTF-8 JSON>

进程池按 ``(server_id, workspace_root)`` 复用，空闲超时后回收。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from jarvis.jarvis_web_gateway.lsp_registry import get_lsp_server_spec

logger = logging.getLogger(__name__)

# 进程空闲回收超时（秒）
IDLE_TIMEOUT_SECONDS = 300.0

# 单条 LSP 消息体上限（防御畸形/恶意 Content-Length，16 MiB）
MAX_MESSAGE_BYTES = 16 * 1024 * 1024


# ---------------------------------------------------------------------------
# LSP 分帧编解码
# ---------------------------------------------------------------------------


def encode_lsp_message(message: Dict[str, Any]) -> bytes:
    """把一条 JSON-RPC 消息编码为 LSP 分帧字节。

    Args:
        message: 可 JSON 序列化的字典

    Returns:
        ``b"Content-Length: N\\r\\n\\r\\n" + body``
    """
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


class LspMessageDecoder:
    """增量式 LSP 分帧解码器。

    用于处理流式字节输入：调用方不断 ``feed()`` 新到达的字节，解码器负责
    处理**粘包**（一次 feed 含多条消息）与**半包**（一条消息跨多次 feed）。

    用法::

        decoder = LspMessageDecoder()
        for chunk in stream:
            for message in decoder.feed(chunk):
                handle(message)
    """

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> List[Dict[str, Any]]:
        """喂入新字节，返回本次能完整解析出的全部消息。

        Args:
            data: 新到达的字节（可为空）

        Returns:
            解析出的消息列表（可能为空）。消息体无法解析为 JSON 时跳过并告警，
            但不影响后续消息的解析。
        """
        if data:
            self._buffer.extend(data)

        messages: List[Dict[str, Any]] = []

        while True:
            header_end = self._buffer.find(b"\r\n\r\n")
            if header_end == -1:
                # header 尚未完整，等待更多数据
                break

            header_bytes = bytes(self._buffer[:header_end])
            content_length = self._parse_content_length(header_bytes)

            if content_length is None:
                # header 格式非法：丢弃到分隔符之后，避免死循环
                logger.warning(
                    "[lsp_bridge] 收到无法解析的 LSP header，已丢弃: %r",
                    header_bytes[:200],
                )
                del self._buffer[: header_end + 4]
                continue

            if content_length < 0 or content_length > MAX_MESSAGE_BYTES:
                logger.warning(
                    "[lsp_bridge] 非法 Content-Length=%s，已丢弃该消息", content_length
                )
                del self._buffer[: header_end + 4]
                continue

            body_start = header_end + 4
            body_end = body_start + content_length
            if len(self._buffer) < body_end:
                # body 尚未收全（半包），等待更多数据
                break

            body = bytes(self._buffer[body_start:body_end])
            del self._buffer[:body_end]

            try:
                message = json.loads(body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning("[lsp_bridge] LSP 消息体 JSON 解析失败，已跳过: %s", e)
                continue

            if isinstance(message, dict):
                messages.append(message)
            else:
                logger.warning("[lsp_bridge] LSP 消息体不是 JSON 对象，已跳过")

        return messages

    @staticmethod
    def _parse_content_length(header_bytes: bytes) -> Optional[int]:
        """从 header 中解析 Content-Length；缺失或非法返回 None。

        忽略额外 header 字段（如 Content-Type）。
        """
        try:
            text = header_bytes.decode("ascii", errors="replace")
        except Exception:  # pragma: no cover - decode 已容错
            return None

        for line in text.split("\r\n"):
            if ":" not in line:
                continue
            name, _, value = line.partition(":")
            if name.strip().lower() == "content-length":
                try:
                    return int(value.strip())
                except ValueError:
                    return None
        return None


# ---------------------------------------------------------------------------
# 进程池
# ---------------------------------------------------------------------------


class _LspProcess:
    """一个语言服务器子进程及其读写任务。"""

    def __init__(
        self,
        server_id: str,
        workspace_root: str,
        process: asyncio.subprocess.Process,
    ) -> None:
        self.server_id = server_id
        self.workspace_root = workspace_root
        self.process = process
        # 当前订阅的 WebSocket 发送回调；None 表示无人连接
        self.sender: Optional[Any] = None
        self.reader_task: Optional[asyncio.Task] = None
        self.stderr_task: Optional[asyncio.Task] = None
        self.idle_task: Optional[asyncio.Task] = None
        self.closed = False

    @property
    def key(self) -> Tuple[str, str]:
        return (self.server_id, self.workspace_root)

    def is_alive(self) -> bool:
        return not self.closed and self.process.returncode is None


class LspProcessPool:
    """按 ``(server_id, workspace_root)`` 复用语言服务器进程。

    - 同一 key 的多个 WS 连接共享同一进程（后者接管消息订阅）；
    - 无连接订阅时启动空闲计时，超时后终止进程；
    - 进程异常退出时清理池中记录。
    """

    def __init__(self, idle_timeout: float = IDLE_TIMEOUT_SECONDS) -> None:
        self._idle_timeout = idle_timeout
        self._procs: Dict[Tuple[str, str], _LspProcess] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(
        self,
        server_id: str,
        workspace_root: str,
    ) -> _LspProcess:
        """获取（或创建）指定 key 的进程。

        Raises:
            RuntimeError: 清单不存在或进程启动失败。
        """
        spec = get_lsp_server_spec(server_id)
        if spec is None:
            raise RuntimeError(f"unknown lsp server id: {server_id}")

        key = (server_id, workspace_root)

        async with self._lock:
            existing = self._procs.get(key)
            if existing is not None and existing.is_alive():
                return existing
            if existing is not None:
                # 已死进程，清理记录
                self._procs.pop(key, None)

            proc = await self._spawn(spec, workspace_root)
            self._procs[key] = proc
            return proc

    async def _spawn(self, spec: Dict[str, Any], workspace_root: str) -> _LspProcess:
        """按清单启动子进程并挂上读取任务。"""
        argv = list(spec.get("command") or []) + list(spec.get("args") or [])
        if not argv:
            raise RuntimeError(f"lsp server {spec.get('id')} 的 command 为空")

        env = dict(os.environ)
        # 让语言服务器知道工作区；部分服务器会用到
        env.setdefault("PWD", workspace_root)

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workspace_root if os.path.isdir(workspace_root) else None,
                env=env,
            )
        except FileNotFoundError as e:
            hint = spec.get("installHint") or ""
            raise RuntimeError(
                f"语言服务器未安装: {argv[0]}" + (f"（{hint}）" if hint else "")
            ) from e
        except OSError as e:
            raise RuntimeError(f"启动语言服务器失败: {e}") from e

        logger.info(
            "[lsp_bridge] 启动语言服务器 server_id=%s pid=%s root=%s",
            spec.get("id"),
            process.pid,
            workspace_root,
        )

        proc = _LspProcess(spec.get("id", ""), workspace_root, process)
        proc.reader_task = asyncio.create_task(self._pump_stdout(proc))
        proc.stderr_task = asyncio.create_task(self._pump_stderr(proc))
        return proc

    async def _pump_stdout(self, proc: _LspProcess) -> None:
        """持续读取子进程 stdout，解码后转发给当前订阅者。"""
        decoder = LspMessageDecoder()
        stream = proc.process.stdout
        assert stream is not None
        try:
            while True:
                chunk = await stream.read(65536)
                if not chunk:
                    break
                for message in decoder.feed(chunk):
                    sender = proc.sender
                    if sender is None:
                        continue
                    try:
                        result = sender(message)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as e:
                        logger.warning("[lsp_bridge] 转发消息到 WS 失败: %s", e)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("[lsp_bridge] 读取语言服务器 stdout 出错: %s", e)
        finally:
            logger.info(
                "[lsp_bridge] 语言服务器 stdout 结束 server_id=%s", proc.server_id
            )
            await self._on_process_gone(proc)

    async def _pump_stderr(self, proc: _LspProcess) -> None:
        """持续读取子进程 stderr 并写日志（避免管道写满阻塞子进程）。"""
        stream = proc.process.stderr
        assert stream is not None
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    logger.info("[lsp_bridge][%s stderr] %s", proc.server_id, text)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("[lsp_bridge] 读取语言服务器 stderr 出错: %s", e)

    async def _on_process_gone(self, proc: _LspProcess) -> None:
        """进程结束时从池中移除并取消后台任务。"""
        async with self._lock:
            if self._procs.get(proc.key) is proc:
                self._procs.pop(proc.key, None)
        proc.closed = True
        self._cancel_task(proc.stderr_task)
        self._cancel_task(proc.idle_task)

    async def send(self, proc: _LspProcess, message: Dict[str, Any]) -> None:
        """把一条消息写入子进程 stdin。"""
        stream = proc.process.stdin
        if stream is None or proc.process.returncode is not None:
            raise RuntimeError("语言服务器进程已退出")
        stream.write(encode_lsp_message(message))
        try:
            await stream.drain()
        except (BrokenPipeError, ConnectionResetError) as e:
            raise RuntimeError("语言服务器进程管道已关闭") from e

    def subscribe(self, proc: _LspProcess, sender: Any) -> None:
        """订阅进程输出，并取消空闲回收计时。"""
        proc.sender = sender
        self._cancel_task(proc.idle_task)
        proc.idle_task = None

    def unsubscribe(self, proc: _LspProcess) -> None:
        """取消订阅，并启动空闲回收计时（进程保留供复用）。"""
        if proc.sender is not None:
            proc.sender = None
        if proc.closed:
            return
        self._cancel_task(proc.idle_task)
        proc.idle_task = asyncio.create_task(self._idle_reaper(proc))

    async def _idle_reaper(self, proc: _LspProcess) -> None:
        """空闲超时后终止进程。"""
        try:
            await asyncio.sleep(self._idle_timeout)
        except asyncio.CancelledError:
            return

        if proc.sender is not None or proc.closed:
            return

        logger.info(
            "[lsp_bridge] 空闲回收语言服务器 server_id=%s root=%s",
            proc.server_id,
            proc.workspace_root,
        )
        await self.terminate(proc)

    async def terminate(self, proc: _LspProcess) -> None:
        """终止进程并清理。"""
        if proc.closed:
            return
        proc.closed = True
        async with self._lock:
            if self._procs.get(proc.key) is proc:
                self._procs.pop(proc.key, None)

        self._cancel_task(proc.idle_task)

        process = proc.process
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(
                    "[lsp_bridge] 语言服务器未响应 terminate，强制 kill pid=%s",
                    process.pid,
                )
                try:
                    process.kill()
                except ProcessLookupError:
                    pass

        self._cancel_task(proc.reader_task)
        self._cancel_task(proc.stderr_task)

    async def shutdown(self) -> None:
        """关闭全部进程（用于应用退出）。"""
        async with self._lock:
            procs = list(self._procs.values())
            self._procs.clear()
        await asyncio.gather(
            *(self.terminate(p) for p in procs), return_exceptions=True
        )

    @staticmethod
    def _cancel_task(task: Optional[asyncio.Task]) -> None:
        if task is not None and not task.done():
            task.cancel()


# ---------------------------------------------------------------------------
# workspace root 解析
# ---------------------------------------------------------------------------


def resolve_workspace_root(
    raw_root: Optional[str],
    spec: Dict[str, Any],
    fallback: Optional[str] = None,
) -> str:
    """解析并校验 workspace root。

    规则：
        1. ``raw_root`` 必须是存在的目录，否则忽略；
        2. 否则在 ``fallback`` 中查找含 ``rootMarkers`` 的最近祖先目录；
        3. 都不满足时返回 ``fallback`` 或当前工作目录。

    Args:
        raw_root: 前端通过 query 传入的 root
        spec: 语言服务器清单
        fallback: 备选起点（通常是当前打开文件的所在目录）

    Returns:
        绝对路径字符串。
    """
    if raw_root:
        try:
            candidate = Path(raw_root).expanduser().resolve()
            if candidate.is_dir():
                return str(candidate)
        except (OSError, ValueError):
            pass

    markers = spec.get("rootMarkers") or []
    if fallback and markers:
        try:
            current = Path(fallback).expanduser().resolve()
        except (OSError, ValueError):
            current = None
        if current is not None:
            if current.is_file():
                current = current.parent
            for directory in [current, *current.parents]:
                for marker in markers:
                    if (directory / marker).exists():
                        return str(directory)
            return str(current)

    if fallback:
        try:
            resolved = Path(fallback).expanduser().resolve()
            return str(resolved.parent if resolved.is_file() else resolved)
        except (OSError, ValueError):
            pass

    return os.getcwd()
