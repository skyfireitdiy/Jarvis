# -*- coding: utf-8 -*-
"""守护进程（jarvis-daemon）连接管理：会话注册、能力查询与调用、结果回传。

用户机器上的 jarvis-daemon 通过 WebSocket 主动连出到网关的
``/api/daemon/ws``（子协议 ``jarvis-daemon``），网关侧用本模块维护会话，
并把 Agent 的能力调用请求下发给守护进程执行。

与浏览器扩展（``browser_extension_manager``）是两条完全独立的链路：
端点、子协议、会话表互不共用。

协议（与 daemon/internal/wsclient/client.go 对齐）：
    - 首帧 ``hello``（含 client_id / node_id / hostname / platform / daemon_version）
    - 网关回 ``hello_ack``（含 session_id / heartbeat_interval）
    - 心跳 ``ping`` / ``pong``
    - 能力查询 ``capability.list`` → ``capability.list.result``
    - 能力调用 ``capability.call`` → ``capability.call.result``
    - 兼容旧信封 ``command`` → ``result``
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# 会话心跳超时（秒）：超过该时长未收到任何消息则清理会话
HEARTBEAT_TIMEOUT = 60.0

# 单次能力调用默认超时（秒）
DEFAULT_CALL_TIMEOUT = 30.0

# 能力列表查询默认超时（秒）
DEFAULT_LIST_TIMEOUT = 15.0

# 守护进程连接使用的 WS 子协议
DAEMON_SUBPROTOCOL = "jarvis-daemon"


class DaemonCapabilityManager:
    """管理守护进程连接与能力调用。

    会话注册表：session_id -> {
        websocket, user_id, client_id, node_id, hostname, platform,
        daemon_version, capabilities, connected_at, last_seen
    }

    ``user_id`` 由网关从 WS 子协议中的 token 解析得到，用于多用户隔离：
    能力查询/调用前必须校验会话归属，避免任意有效 token 跨用户执行本机能力。
    """

    def __init__(self) -> None:
        # session_id -> 会话信息
        self._sessions: Dict[str, Dict[str, Any]] = {}
        # request_id -> Future，用于按 id 匹配能力调用响应
        self._pending_calls: Dict[str, asyncio.Future] = {}
        # session_id -> Future，用于匹配无 id 的能力列表响应
        self._pending_lists: Dict[str, asyncio.Future] = {}
        # 心跳巡检任务
        self._cleanup_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # 会话生命周期
    # ------------------------------------------------------------------
    def _ensure_cleanup_task(self) -> None:
        """惰性启动心跳超时巡检任务。"""
        if self._cleanup_task is None or self._cleanup_task.done():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            self._cleanup_task = loop.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        """周期性清理心跳超时的会话。"""
        try:
            while True:
                await asyncio.sleep(10)
                now = time.time()
                stale: List[str] = []
                for session_id, session in list(self._sessions.items()):
                    last_seen = session.get("last_seen") or session.get(
                        "connected_at", now
                    )
                    if now - last_seen > HEARTBEAT_TIMEOUT:
                        stale.append(session_id)
                for session_id in stale:
                    logger.warning("[DAEMON] session heartbeat timeout: %s", session_id)
                    await self.disconnect(session_id)
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # pragma: no cover - 防御性
            logger.exception("[DAEMON] cleanup loop error: %s", exc)

    async def handle_daemon_websocket(
        self,
        websocket: WebSocket,
        user_id: Optional[str] = None,
    ) -> None:
        """处理守护进程 WebSocket 连接：注册会话、收发消息、断开清理。

        注意：鉴权在 app.py 的端点层完成，本方法不做权限校验；
        ``user_id`` 由端点层从 token 解析后传入，用于后续会话归属校验。
        """
        # 守护进程使用自定义子协议，必须回显否则客户端会断开
        await websocket.accept(subprotocol=DAEMON_SUBPROTOCOL)
        session_id = str(uuid.uuid4())
        self._ensure_cleanup_task()
        try:
            # 首帧必须是 hello
            try:
                first = await asyncio.wait_for(websocket.receive_json(), timeout=10)
            except Exception:
                await self._send_error(
                    websocket, "INVALID_MESSAGE", "first message must be hello"
                )
                await websocket.close(code=4400)
                return
            if not isinstance(first, dict) or first.get("type") != "hello":
                await self._send_error(
                    websocket, "INVALID_MESSAGE", "first message must be hello"
                )
                await websocket.close(code=4400)
                return

            client_id = str(first.get("client_id") or "").strip() or session_id
            # 守护进程上报的是自身（用户侧服务）的系统信息；浏览器信息由浏览器
            # 扩展另行上报，不在此处理。兼容旧版：旧版把 hostname/platform 放在
            # browser_info 里，故仍保留该回退路径。
            system_info = first.get("system_info") or {}
            if not isinstance(system_info, dict):
                system_info = {}
            browser_info = first.get("browser_info") or {}
            if not isinstance(browser_info, dict):
                browser_info = {}
            hostname = str(
                system_info.get("hostname") or browser_info.get("hostname") or ""
            ).strip()
            now = time.time()
            # 同一台机器上的 daemon 重启后 client_id 会变（含 PID），旧连接在心跳
            # 超时（最长约 70s）前仍留在会话表里，导致 list_sessions 出现幽灵条目、
            # 能力调用可能被路由到已失效的旧连接。这里以 (user_id, hostname) 作为
            # 稳定身份，在注册新会话前主动清理同机器的旧会话。
            # hostname 为空时无法可靠识别身份，不做清理以免误杀。
            if hostname:
                await self._replace_stale_sessions(session_id, user_id, hostname)
            # 守护进程可在 hello 中直接携带能力列表（新版 daemon 会这么做）。
            # 这样会话一注册就带有能力，无需再依赖运行时 capability.list 往返；
            # 旧版 daemon 不带该字段时回退为空列表，仍可通过主动查询获取。
            hello_capabilities = first.get("capabilities")
            if not isinstance(hello_capabilities, list):
                hello_capabilities = []
            # 守护进程可在 hello 中携带构建信息（版本/编译时间/Go 版本/目标平台）。
            # 编译时间取自 daemon exe 的 mtime（见 daemon/internal/buildinfo）。
            # 旧版 daemon 不带该字段时回退为空字典。
            hello_build_info = first.get("build_info")
            if not isinstance(hello_build_info, dict):
                hello_build_info = {}
            self._sessions[session_id] = {
                "websocket": websocket,
                "user_id": user_id,
                "client_id": client_id,
                "node_id": str(first.get("node_id") or "").strip() or client_id,
                "hostname": str(
                    system_info.get("hostname") or browser_info.get("hostname") or ""
                ).strip(),
                "platform": str(
                    system_info.get("os_name")
                    or system_info.get("platform")
                    or browser_info.get("platform")
                    or ""
                ).strip(),
                "system_info": system_info,
                "daemon_version": first.get("extension_version"),
                "build_info": hello_build_info,
                "capabilities": hello_capabilities,
                "connected_at": now,
                "last_seen": now,
            }
            logger.info(
                "[DAEMON] session connected: session_id=%s client_id=%s node_id=%s user_id=%s",
                session_id,
                client_id,
                self._sessions[session_id]["node_id"],
                user_id,
            )
            # 诊断日志：便于端到端排查「系统信息是否收到」。
            # 若此处 system_info 为空，说明 daemon 未上报或上报字段名不符；
            # 若此处有值但 /api/daemon/sessions 看不到，问题在返回层。
            logger.info(
                "[DAEMON] hello system_info: received=%s hostname=%r platform=%r fields=%d",
                bool(system_info),
                self._sessions[session_id]["hostname"],
                self._sessions[session_id]["platform"],
                len(system_info),
            )

            await websocket.send_json(
                {
                    "type": "hello_ack",
                    "session_id": session_id,
                    "heartbeat_interval": 20,
                }
            )

            # 消息循环
            while True:
                message = await websocket.receive_json()
                if not isinstance(message, dict):
                    continue
                session = self._sessions.get(session_id)
                if session is not None:
                    session["last_seen"] = time.time()
                msg_type = message.get("type")
                if msg_type == "capability.list.result":
                    self._handle_capability_list_result(session_id, message)
                elif msg_type == "capability.call.result":
                    self._handle_capability_call_result(message)
                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                elif msg_type == "hello":
                    # 重连后重新握手：刷新会话信息
                    if session is not None:
                        session["client_id"] = (
                            str(message.get("client_id") or "").strip() or client_id
                        )
                        session["node_id"] = (
                            str(message.get("node_id") or "").strip()
                            or session["client_id"]
                        )
                else:
                    logger.debug("[DAEMON] unknown message type: %s", msg_type)
        except Exception as exc:
            logger.info(
                "[DAEMON] session closed: session_id=%s reason=%s",
                session_id,
                exc,
            )
        finally:
            await self.disconnect(session_id)

    def _handle_capability_list_result(
        self, session_id: str, message: Dict[str, Any]
    ) -> None:
        """缓存能力列表并唤醒等待中的查询。"""
        capabilities = message.get("capabilities")
        if not isinstance(capabilities, list):
            capabilities = []
        session = self._sessions.get(session_id)
        if session is not None:
            session["capabilities"] = capabilities
        future = self._pending_lists.get(session_id)
        if future is not None and not future.done():
            future.set_result(capabilities)

    def _handle_capability_call_result(self, message: Dict[str, Any]) -> None:
        """把能力调用结果投递给等待中的 Future。"""
        request_id = message.get("id")
        if not request_id:
            return
        future = self._pending_calls.get(request_id)
        if future is not None and not future.done():
            future.set_result(message)

    async def _replace_stale_sessions(
        self,
        new_session_id: str,
        user_id: Optional[str],
        hostname: str,
    ) -> None:
        """清理同一台机器（同 user_id + 同 hostname）遗留的旧会话。

        daemon 重启后 ``client_id`` 会变（含 PID），旧连接在心跳超时前仍留在
        会话表中。以 ``(user_id, hostname)`` 作为稳定身份，在注册新会话前把
        旧会话一并断开，避免幽灵条目与调用错路由。
        """
        stale: List[str] = []
        for session_id, session in list(self._sessions.items()):
            if session_id == new_session_id:
                continue
            if session.get("user_id") != user_id:
                continue
            if str(session.get("hostname") or "").strip() != hostname:
                continue
            stale.append(session_id)
        for session_id in stale:
            logger.info(
                "[DAEMON] replace stale session: old=%s new=%s hostname=%s",
                session_id,
                new_session_id,
                hostname,
            )
            await self.disconnect(session_id)

    async def disconnect(self, session_id: str) -> None:
        """关闭并移除会话，失败所有等待中的调用。"""
        session = self._sessions.pop(session_id, None)
        if session is None:
            return
        websocket = session.get("websocket")
        if websocket is not None:
            try:
                await websocket.close()
            except Exception:
                pass
        # 该会话下所有未完成调用立即失败
        for request_id, future in list(self._pending_calls.items()):
            if future.done():
                continue
            if getattr(future, "_daemon_session", None) == session_id:
                future.set_exception(
                    RuntimeError(f"daemon session disconnected: {session_id}")
                )
                self._pending_calls.pop(request_id, None)
        list_future = self._pending_lists.pop(session_id, None)
        if list_future is not None and not list_future.done():
            list_future.set_exception(
                RuntimeError(f"daemon session disconnected: {session_id}")
            )
        logger.info("[DAEMON] session removed: %s", session_id)

    # ------------------------------------------------------------------
    # 会话归属校验
    # ------------------------------------------------------------------
    def check_session_access(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> tuple[bool, str]:
        """校验调用方是否有权访问指定守护进程会话。

        规则：
        - 会话不存在 → 拒绝；
        - ``user_id`` 为空、为 ``system`` 或 ``is_admin`` 为真 → 放行（网关内部/管理员）；
        - 否则要求会话的 ``user_id`` 与调用方一致。

        Returns:
            (是否允许, 拒绝原因)；允许时原因为空字符串。
        """
        session = self._sessions.get(session_id)
        if session is None:
            return False, f"daemon session not found: {session_id}"
        if not user_id or user_id == "system" or is_admin:
            return True, ""
        if session.get("user_id") != user_id:
            return False, "forbidden: daemon session belongs to another user"
        return True, ""

    # ------------------------------------------------------------------
    # 能力查询与调用
    # ------------------------------------------------------------------
    async def list_capabilities(
        self,
        session_id: str,
        timeout: float = DEFAULT_LIST_TIMEOUT,
        user_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> List[Dict[str, Any]]:
        """查询指定守护进程的能力列表。

        Raises:
            RuntimeError: 会话不存在、无访问权限、连接已失效或查询超时。
        """
        allowed, reason = self.check_session_access(session_id, user_id, is_admin)
        if not allowed:
            raise RuntimeError(reason)
        session = self._sessions.get(session_id)
        if session is None:
            raise RuntimeError(f"daemon session not found: {session_id}")
        websocket = session.get("websocket")
        if websocket is None:
            raise RuntimeError(f"daemon session has no connection: {session_id}")

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending_lists[session_id] = future
        try:
            logger.info("[DAEMON] list capabilities session_id=%s", session_id)
            await websocket.send_json({"type": "capability.list"})
            try:
                capabilities = await asyncio.wait_for(future, timeout=timeout)
            except asyncio.TimeoutError as exc:
                raise RuntimeError(
                    f"daemon capability list timed out: session_id={session_id}, "
                    f"timeout={timeout}s"
                ) from exc
            return list(capabilities or [])
        finally:
            self._pending_lists.pop(session_id, None)

    async def call_capability(
        self,
        session_id: str,
        name: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = DEFAULT_CALL_TIMEOUT,
        user_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> Dict[str, Any]:
        """调用指定守护进程的一项能力并等待结果。

        Returns:
            dict: {"success": bool, "data": any, "error": str}

        Raises:
            RuntimeError: 会话不存在、无访问权限、连接已失效或调用超时。
        """
        allowed, reason = self.check_session_access(session_id, user_id, is_admin)
        if not allowed:
            raise RuntimeError(reason)
        session = self._sessions.get(session_id)
        if session is None:
            raise RuntimeError(f"daemon session not found: {session_id}")
        websocket = session.get("websocket")
        if websocket is None:
            raise RuntimeError(f"daemon session has no connection: {session_id}")

        call_id = f"call-{uuid.uuid4()}"
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        # 记录归属会话，便于断线时批量失败
        setattr(future, "_daemon_session", session_id)
        self._pending_calls[call_id] = future
        try:
            logger.info(
                "[DAEMON] call capability session_id=%s name=%s call_id=%s",
                session_id,
                name,
                call_id,
            )
            await websocket.send_json(
                {
                    "type": "capability.call",
                    "id": call_id,
                    "name": name,
                    "params": params or {},
                }
            )
            try:
                response = await asyncio.wait_for(future, timeout=timeout)
            except asyncio.TimeoutError as exc:
                raise RuntimeError(
                    f"daemon capability call timed out: session_id={session_id}, "
                    f"name={name}, timeout={timeout}s"
                ) from exc
            if not isinstance(response, dict):
                raise RuntimeError(
                    f"invalid daemon capability response: session_id={session_id}, "
                    f"name={name}"
                )
            return {
                "success": bool(response.get("success")),
                "data": response.get("data"),
                "error": response.get("error") or "",
            }
        finally:
            self._pending_calls.pop(call_id, None)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def list_sessions(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出当前在线的守护进程会话；传入 user_id 时仅返回该用户的会话。"""
        result: List[Dict[str, Any]] = []
        for session_id, session in self._sessions.items():
            if user_id is not None and session.get("user_id") != user_id:
                continue
            result.append(
                {
                    "session_id": session_id,
                    "client_id": session.get("client_id"),
                    "user_id": session.get("user_id"),
                    "node_id": session.get("node_id"),
                    "hostname": session.get("hostname"),
                    "platform": session.get("platform"),
                    "system_info": session.get("system_info") or {},
                    "daemon_version": session.get("daemon_version"),
                    "build_info": session.get("build_info") or {},
                    "capabilities": session.get("capabilities") or [],
                    "connected_at": session.get("connected_at"),
                }
            )
        return result

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取单个会话信息（不含 websocket 对象）。"""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        return {
            "session_id": session_id,
            "client_id": session.get("client_id"),
            "user_id": session.get("user_id"),
            "node_id": session.get("node_id"),
            "hostname": session.get("hostname"),
            "platform": session.get("platform"),
            "system_info": session.get("system_info") or {},
            "daemon_version": session.get("daemon_version"),
            "build_info": session.get("build_info") or {},
            "capabilities": session.get("capabilities") or [],
            "connected_at": session.get("connected_at"),
        }

    # ------------------------------------------------------------------
    # 工具函数
    # ------------------------------------------------------------------
    @staticmethod
    async def _send_error(websocket: WebSocket, code: str, message: str) -> None:
        try:
            await websocket.send_json(
                {"type": "error", "payload": {"code": code, "message": message}}
            )
        except Exception:
            pass


# 全局单例，供 app.py 与工具层共用
daemon_capability_manager = DaemonCapabilityManager()
