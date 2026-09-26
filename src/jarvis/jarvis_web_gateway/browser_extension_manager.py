# -*- coding: utf-8 -*-
"""浏览器扩展连接管理：会话注册、指令路由、结果回传。

用户浏览器内的 Chrome/Edge 扩展通过 WebSocket 主动连出到网关，
网关侧用本模块维护会话并把 Agent 的指令下发给插件执行。

协议见 docs/design/browser-extension-agent-control.md 第 4 节。
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# 会话心跳超时（秒）：超过该时长未收到任何消息则清理会话
HEARTBEAT_TIMEOUT = 60.0

# 单条指令默认超时（秒）
DEFAULT_COMMAND_TIMEOUT = 15.0

# 网关侧最新扩展版本提供器：返回网关打包的扩展版本号（读不到时返回 None）。
# 由 app.py 在启动时注入，避免本模块耦合扩展源码目录的定位逻辑。
LatestVersionProvider = Callable[[], Optional[str]]


class BrowserExtensionManager:
    """管理浏览器扩展连接与指令下发。

    会话注册表：session_id -> {
        websocket, user_id, client_id, tabs_meta, connected_at, last_seen
    }
    """

    def __init__(self) -> None:
        # session_id -> 会话信息
        self._sessions: Dict[str, Dict[str, Any]] = {}
        # request_id -> Future，用于按 id 匹配指令响应
        self._pending_commands: Dict[str, asyncio.Future] = {}
        # 心跳巡检任务
        self._cleanup_task: Optional[asyncio.Task] = None
        # 网关打包的扩展最新版本提供器（未注入时返回 None，不影响握手）
        self._latest_version_provider: Optional[LatestVersionProvider] = None

    def set_latest_version_provider(
        self, provider: Optional[LatestVersionProvider]
    ) -> None:
        """注入「网关打包的扩展最新版本」提供器。

        握手时会把结果随 hello_ack 下发给扩展，供其自行判断是否需要升级。
        未注入或读取失败时该字段为 None，扩展侧应忽略。
        """
        self._latest_version_provider = provider

    def _get_latest_version(self) -> Optional[str]:
        """读取网关打包的扩展最新版本；未注入或异常时返回 None。"""
        provider = self._latest_version_provider
        if provider is None:
            return None
        try:
            version = provider()
        except Exception as exc:  # pragma: no cover - 防御性
            logger.warning("[BROWSER-EXT] latest version provider failed: %s", exc)
            return None
        version = str(version or "").strip()
        return version or None

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
                    logger.warning(
                        "[BROWSER-EXT] session heartbeat timeout: %s", session_id
                    )
                    await self.disconnect(session_id)
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # pragma: no cover - 防御性
            logger.exception("[BROWSER-EXT] cleanup loop error: %s", exc)

    async def handle_extension_websocket(
        self,
        websocket: WebSocket,
        user_id: Optional[str] = None,
    ) -> None:
        """处理插件 WebSocket 连接：注册会话、收发消息、断开清理。

        注意：鉴权在 app.py 的端点层完成，本方法不做权限校验。
        ``user_id`` 由端点层从 token 解析后传入，优先于 hello 帧里的 user_id。
        """
        # 插件使用自定义子协议，必须回显其中一个否则浏览器会断开
        await websocket.accept(subprotocol="jarvis-ext")
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
            # 端点层从 token 解析出的 user_id 优先；hello 帧里的 user_id 仅作兼容回退
            session_user_id = user_id if user_id is not None else first.get("user_id")
            tabs_meta = first.get("tabs") or []
            now = time.time()
            self._sessions[session_id] = {
                "websocket": websocket,
                "user_id": session_user_id,
                "client_id": client_id,
                "tabs_meta": tabs_meta,
                "connected_at": now,
                "last_seen": now,
                "extension_version": first.get("extension_version"),
                "browser_info": first.get("browser_info") or {},
            }
            logger.info(
                "[BROWSER-EXT] session connected: session_id=%s client_id=%s user_id=%s tabs=%d",
                session_id,
                client_id,
                user_id,
                len(tabs_meta),
            )

            await websocket.send_json(
                {
                    "type": "hello_ack",
                    "session_id": session_id,
                    "heartbeat_interval": 20,
                    # 网关打包的扩展最新版本：扩展据此自行判断是否需要升级
                    "latest_extension_version": self._get_latest_version(),
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
                if msg_type == "result":
                    self._handle_result(message)
                elif msg_type == "event":
                    self._handle_event(session_id, message)
                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                elif msg_type == "hello":
                    # 重连后重新握手：刷新会话信息
                    if session is not None:
                        session["tabs_meta"] = message.get("tabs") or []
                        session["client_id"] = (
                            str(message.get("client_id") or "").strip() or client_id
                        )
                else:
                    logger.debug("[BROWSER-EXT] unknown message type: %s", msg_type)
        except Exception as exc:
            logger.info(
                "[BROWSER-EXT] session closed: session_id=%s reason=%s",
                session_id,
                exc,
            )
        finally:
            await self.disconnect(session_id)

    def _handle_result(self, message: Dict[str, Any]) -> None:
        """把指令结果投递给等待中的 Future。"""
        request_id = message.get("id")
        if not request_id:
            return
        future = self._pending_commands.get(request_id)
        if future is not None and not future.done():
            future.set_result(message)

    def _handle_event(self, session_id: str, message: Dict[str, Any]) -> None:
        """处理插件主动上报的事件（如标签页变化）。"""
        session = self._sessions.get(session_id)
        if session is None:
            return
        event = message.get("event")
        data = message.get("data") or {}
        if event in ("tab.created", "tab.removed", "tab.updated") and isinstance(
            data, dict
        ):
            raw_tabs = session.get("tabs_meta")
            if isinstance(raw_tabs, list):
                tabs: List[Dict[str, Any]] = [
                    t for t in raw_tabs if isinstance(t, dict)
                ]
                tab_id = data.get("tab_id")
                if event == "tab.removed":
                    tabs = [t for t in tabs if t.get("tab_id") != tab_id]
                elif event == "tab.created":
                    tabs.append(data)
                elif event == "tab.updated":
                    for idx, tab in enumerate(tabs):
                        if tab.get("tab_id") == tab_id:
                            tabs[idx] = {**tab, **data}
                            break
                session["tabs_meta"] = tabs
        logger.debug("[BROWSER-EXT] event from %s: %s", session_id, event)

    async def disconnect(self, session_id: str) -> None:
        """关闭并移除会话，失败所有等待中的指令。"""
        session = self._sessions.pop(session_id, None)
        if session is None:
            return
        websocket = session.get("websocket")
        if websocket is not None:
            try:
                await websocket.close()
            except Exception:
                pass
        # 该会话下所有未完成指令立即失败
        for request_id, future in list(self._pending_commands.items()):
            if future.done():
                continue
            if getattr(future, "_browser_ext_session", None) == session_id:
                future.set_exception(
                    RuntimeError(f"session disconnected: {session_id}")
                )
                self._pending_commands.pop(request_id, None)
        logger.info("[BROWSER-EXT] session removed: %s", session_id)

    # ------------------------------------------------------------------
    # 会话归属校验
    # ------------------------------------------------------------------
    def check_session_access(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> tuple[bool, str]:
        """校验调用方是否有权访问指定浏览器扩展会话。

        规则：
        - 会话不存在 → 拒绝；
        - ``user_id`` 为空、为 ``system`` 或 ``is_admin`` 为真 → 放行（网关内部/管理员）；
        - 否则要求会话的 ``user_id`` 与调用方一致。

        Returns:
            (是否允许, 拒绝原因)；允许时原因为空字符串。
        """
        session = self._sessions.get(session_id)
        if session is None:
            return False, f"browser session not found: {session_id}"
        if not user_id or user_id == "system" or is_admin:
            return True, ""
        if session.get("user_id") != user_id:
            return False, "forbidden: browser session belongs to another user"
        return True, ""

    # ------------------------------------------------------------------
    # 指令下发
    # ------------------------------------------------------------------
    async def send_command(
        self,
        session_id: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = DEFAULT_COMMAND_TIMEOUT,
        user_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> Dict[str, Any]:
        """向指定会话下发指令并等待结果。

        Raises:
            RuntimeError: 会话不存在、无访问权限、连接已失效或指令超时。
        """
        allowed, reason = self.check_session_access(session_id, user_id, is_admin)
        if not allowed:
            raise RuntimeError(reason)
        session = self._sessions.get(session_id)
        if session is None:
            raise RuntimeError(f"browser session not found: {session_id}")
        websocket = session.get("websocket")
        if websocket is None:
            raise RuntimeError(f"browser session has no connection: {session_id}")

        request_id = f"req-{uuid.uuid4()}"
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        # 记录归属会话，便于断线时批量失败
        setattr(future, "_browser_ext_session", session_id)
        self._pending_commands[request_id] = future
        try:
            logger.info(
                "[BROWSER-EXT] send command session_id=%s action=%s request_id=%s",
                session_id,
                action,
                request_id,
            )
            await websocket.send_json(
                {
                    "id": request_id,
                    "type": "command",
                    "action": action,
                    "params": params or {},
                    "timeout_ms": int(timeout * 1000),
                }
            )
            try:
                response = await asyncio.wait_for(future, timeout=timeout)
            except asyncio.TimeoutError as exc:
                raise RuntimeError(
                    f"browser command timed out: session_id={session_id}, "
                    f"action={action}, timeout={timeout}s"
                ) from exc
            if not isinstance(response, dict):
                raise RuntimeError(
                    f"invalid browser command response: session_id={session_id}, "
                    f"action={action}"
                )
            return response
        finally:
            self._pending_commands.pop(request_id, None)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def list_sessions(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出当前在线会话；传入 user_id 时仅返回该用户的会话。"""
        result: List[Dict[str, Any]] = []
        for session_id, session in self._sessions.items():
            if user_id is not None and session.get("user_id") != user_id:
                continue
            result.append(
                {
                    "session_id": session_id,
                    "client_id": session.get("client_id"),
                    "user_id": session.get("user_id"),
                    "connected_at": session.get("connected_at"),
                    "extension_version": session.get("extension_version"),
                    "browser_info": session.get("browser_info") or {},
                    "tabs": session.get("tabs_meta") or [],
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
            "connected_at": session.get("connected_at"),
            "extension_version": session.get("extension_version"),
            "browser_info": session.get("browser_info") or {},
            "tabs": session.get("tabs_meta") or [],
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
browser_extension_manager = BrowserExtensionManager()
