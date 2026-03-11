# -*- coding: utf-8 -*-
"""Web Gateway FastAPI 应用。

独立服务：通过 WebSocket 对接 Gateway 输入/输出/执行事件。
"""

from __future__ import annotations

import asyncio
import uuid
import time
from typing import Any
from typing import Callable
from typing import Dict
from typing import Optional
from typing import Tuple

from fastapi import FastAPI
from fastapi import WebSocket
from fastapi import WebSocketDisconnect

from jarvis.jarvis_gateway.events import GatewayExecutionEvent
from jarvis.jarvis_gateway.events import GatewayInputRequest
from jarvis.jarvis_gateway.events import GatewayInputResult
from jarvis.jarvis_gateway.events import GatewayOutputEvent
from jarvis.jarvis_gateway.gateway import BaseGateway
from jarvis.jarvis_gateway.input_bridge import InputSessionRegistry
from jarvis.jarvis_gateway.manager import set_current_gateway
from jarvis.jarvis_gateway.output_bridge import SessionOutputRouter
from jarvis.jarvis_web_gateway.terminal_input_registry import TerminalInputRegistry


class WebGateway(BaseGateway):
    """Web Gateway 实现：桥接输出、输入与执行事件到 WebSocket。"""

    def __init__(
        self,
        router: SessionOutputRouter,
        input_registry: InputSessionRegistry,
        auth_store: Dict[str, Optional[Dict[str, Any]]],
        terminal_input_registry: TerminalInputRegistry,
    ) -> None:
        self._router = router
        self._input_registry = input_registry
        self._auth_store = auth_store
        self._terminal_input_registry = terminal_input_registry
        self._current_session_id: Optional[str] = None

    def emit_output(self, event: GatewayOutputEvent) -> None:
        session_id = _extract_session_id(event.context)
        print(
            f"🔍 [DEBUG] WebGateway.emit_output called, text={repr(event.text[:50]) if event.text else ''}, session_id from context={session_id}"
        )
        # 如果没有 session_id，使用保存的 session 或默认的活跃 session
        if not session_id:
            session_id = self._current_session_id or _resolve_active_session_id(
                self._auth_store
            )
            print(
                f"🔍 [DEBUG] WebGateway.emit_output: Using saved/resolved session_id={session_id}"
            )
        auth_payload = self._auth_store.get(session_id) if session_id else None
        authorized, _ = self._check_auth(auth_payload)
        print(f"🔍 [DEBUG] WebGateway.emit_output: authorized={authorized}")
        if not authorized:
            return
        payload = {
            "text": event.text,
            "output_type": event.output_type,
            "timestamp": event.timestamp,
            "lang": event.lang,
            "traceback": event.traceback,
            "section": event.section,
            "context": dict(event.context) if event.context else {},
        }
        message = {"type": "output", "payload": payload}
        print(
            f"🔍 [DEBUG] WebGateway.emit_output: Publishing output to session_id={session_id}"
        )
        self._router.publish(message, session_id=session_id)

    def request_input(self, request: GatewayInputRequest) -> GatewayInputResult:
        print(f"🔍 [DEBUG] WebGateway.request_input called, tip={request.tip}")
        metadata = dict(request.metadata) if request.metadata else {}
        session_id = metadata.get("session_id")
        print(
            f"🔍 [DEBUG] WebGateway.request_input: session_id from metadata={session_id}"
        )
        if not session_id:
            print("\n⏳ 正在等待浏览器连接 WebSocket...")
            print("   请在浏览器中打开页面: http://localhost:5005\n")
            session_id = _wait_for_active_session_id(self._auth_store)
            print(f"🔍 [DEBUG] WebGateway.request_input: Got session_id={session_id}")
            if session_id:
                print(f"✅ WebSocket 已连接！Session ID: {session_id}\n")
                self._current_session_id = session_id
            if session_id:
                metadata["session_id"] = session_id
            else:
                session_id = "default"
                metadata["session_id"] = session_id
                print("🔍 [DEBUG] WebGateway.request_input: Using default session_id")
        auth_payload = metadata.get("auth") or self._auth_store.get(session_id)
        authorized, reason = self._check_auth(auth_payload)
        if not authorized:
            print(f"🔍 [DEBUG] WebGateway.request_input: Auth failed, reason={reason}")
            return GatewayInputResult(text="", metadata={"error": reason})
        payload = {
            "tip": request.tip,
            "preset": request.preset,
            "preset_cursor": request.preset_cursor,
            "metadata": metadata,
        }
        message = {"type": "input_request", "payload": payload}
        print(
            f"🔍 [DEBUG] WebGateway.request_input: Publishing input_request to session_id={session_id}"
        )
        self._router.publish(message, session_id=session_id)
        session = self._input_registry.get_or_create(session_id)
        print(
            f"🔍 [DEBUG] WebGateway.request_input: Waiting for input from session_id={session_id}"
        )
        text = session.wait_for_input()
        print(
            f"🔍 [DEBUG] WebGateway.request_input: Got input text={repr(text[:50]) if text else ''}"
        )
        return GatewayInputResult(text=text, metadata=metadata)

    def publish_execution_event(
        self,
        event: GatewayExecutionEvent,
        session_id: Optional[str] = None,
    ) -> None:
        payload = dict(event.payload) if event.payload else {}
        session_id = session_id or payload.get("session_id")
        # 如果没有 session_id，使用保存的 session 或默认的活跃 session（与 emit_output 一致）
        if not session_id:
            session_id = self._current_session_id or _resolve_active_session_id(
                self._auth_store
            )
            print(
                f"🔍 [DEBUG] WebGateway.publish_execution_event: Using saved/resolved session_id={session_id}"
            )
        auth_payload = payload.get("auth") or (
            self._auth_store.get(session_id) if session_id else None
        )
        authorized, _ = self._check_auth(auth_payload)
        if not authorized:
            return

        # 🔧 适配前端期望的消息结构
        # 前端期望: { event_type: 'stdout'|'stderr', data: '...', encoded: true/false }
        # 后端原始: { stream: 'stdout', chunk: '...', encoded: true }
        stream = payload.get("stream", "stdout")  # "stdout" 或 "stderr" 或 "tty"
        chunk = payload.get("chunk", "")  # 实际输出内容（可能是 base64 编码的字符串）
        encoded = payload.get("encoded", False)  # 是否经过 base64 编码
        # 🔧 将 'tty' 映射为 'stdout'，以便前端能正确处理
        if stream == "tty":
            stream = "stdout"

        message_payload = {
            "event_type": stream,  # 使用 stream 作为 event_type
            "data": chunk,  # 使用 chunk 作为 data（可能是 base64）
            "encoded": encoded,  # 传递编码标记
            "tool": payload.get("tool"),
            "sequence": payload.get("sequence"),
            "execution_id": payload.get("execution_id"),
        }
        if event.timestamp:
            message_payload["timestamp"] = event.timestamp
        if "message_type" in payload:
            message_payload["message_type"] = payload["message_type"]

        print(
            f"🔍 [DEBUG] WebGateway.publish_execution_event: event_type={stream}, chunk_len={len(chunk)}, encoded={encoded}"
        )
        message = {"type": "execution", "payload": message_payload}
        self._router.publish(message, session_id=session_id)

    def get_execution_input_callback(
        self,
        execution_id: str,
    ) -> Optional[Callable[[Optional[float]], Optional[str]]]:
        return self._terminal_input_registry.get_input_callback(execution_id)

    def get_execution_resize_callback(
        self,
        execution_id: str,
    ) -> Optional[Callable[[], Optional[Tuple[int, int]]]]:
        return self._terminal_input_registry.get_resize_callback(execution_id)


class WebSocketConnectionManager:
    """WebSocket 连接管理。"""

    def __init__(
        self,
        router: SessionOutputRouter,
        input_registry: InputSessionRegistry,
        terminal_input_registry: TerminalInputRegistry,
        gateway: WebGateway,
        auth_store: Dict[str, Optional[Dict[str, Any]]],
    ) -> None:
        self._router = router
        self._input_registry = input_registry
        self._terminal_input_registry = terminal_input_registry
        self._gateway = gateway
        self._auth_store = auth_store

    async def handle(self, websocket: WebSocket) -> None:
        print("🔍 [DEBUG] WebSocketConnectionManager.handle: Connection started")
        await websocket.accept()
        session_id = websocket.query_params.get("session_id") or str(uuid.uuid4())
        connection_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        print(
            f"🔍 [DEBUG] WebSocketConnectionManager.handle: session_id={session_id}, connection_id={connection_id}"
        )
        auth_payload = _extract_auth_from_headers(websocket)
        authorized, reason = self._gateway._check_auth(auth_payload)
        print(
            f"🔍 [DEBUG] WebSocketConnectionManager.handle: Initial auth check, authorized={authorized}"
        )
        if not authorized:
            auth_payload, authorized, reason = await _await_auth_message(
                websocket, self._gateway
            )
            print(
                f"🔍 [DEBUG] WebSocketConnectionManager.handle: Await auth message, authorized={authorized}"
            )
        if not authorized:
            await _send_error(websocket, "AUTH_FAILED", reason or "auth failed")
            await websocket.close()
            return
        self._auth_store[session_id] = auth_payload
        self._router.register(
            connection_id,
            _build_sender(websocket, loop),
            session_id=session_id,
        )
        self._input_registry.register_provider(session_id)
        print(
            f"🔍 [DEBUG] WebSocketConnectionManager.handle: Registered router and provider for session_id={session_id}"
        )
        await websocket.send_json(
            {"type": "ready", "payload": {"session_id": session_id}}
        )
        print(
            f"🔍 [DEBUG] WebSocketConnectionManager.handle: Sent ready message for session_id={session_id}"
        )
        try:
            while True:
                message = await websocket.receive_json()
                await self._handle_message(session_id, message)
        except WebSocketDisconnect:
            print(
                f"🔍 [DEBUG] WebSocketConnectionManager.handle: WebSocket disconnected for session_id={session_id}"
            )
            pass
        finally:
            self._router.unregister(connection_id, session_id=session_id)
            self._input_registry.unregister_provider(session_id)
            self._auth_store.pop(session_id, None)
            print(
                f"🔍 [DEBUG] WebSocketConnectionManager.handle: Cleaned up session_id={session_id}"
            )

    async def _handle_message(self, session_id: str, message: Any) -> None:
        if not isinstance(message, dict):
            return
        message_type = message.get("type")
        payload = message.get("payload") or {}
        print(
            f"🔍 [DEBUG] WebSocketConnectionManager._handle_message: type={message_type}, session_id={session_id}"
        )
        if message_type == "auth":
            auth_payload = _normalize_auth_payload(payload)
            authorized, _ = self._gateway._check_auth(auth_payload)
            if not authorized:
                return
            self._auth_store[session_id] = auth_payload
            return
        if message_type == "input_result":
            text = payload.get("text", "")
            print(
                f"🔍 [DEBUG] WebSocketConnectionManager._handle_message: Received input_result for session_id={session_id}, text={repr(text[:50]) if text else ''}"
            )
            self._input_registry.submit_input(session_id, text)
            return
        if message_type == "terminal_input":
            execution_id = payload.get("execution_id")
            data = payload.get("data", "")
            if not execution_id:
                return
            self._terminal_input_registry.submit_terminal_input(execution_id, data)
            return
        if message_type == "terminal_resize":
            execution_id = payload.get("execution_id")
            rows = payload.get("rows")
            cols = payload.get("cols")
            if not execution_id:
                return
            try:
                rows_int = int(rows)
                cols_int = int(cols)
            except (TypeError, ValueError):
                return
            self._terminal_input_registry.submit_terminal_resize(
                execution_id, rows_int, cols_int
            )
            return


def create_app() -> FastAPI:
    """创建 FastAPI 应用。"""

    router = SessionOutputRouter()
    input_registry = InputSessionRegistry()
    terminal_input_registry = TerminalInputRegistry()
    auth_store: Dict[str, Optional[Dict[str, Any]]] = {}
    gateway = WebGateway(router, input_registry, auth_store, terminal_input_registry)
    manager = WebSocketConnectionManager(
        router, input_registry, terminal_input_registry, gateway, auth_store
    )

    set_current_gateway(gateway)

    app = FastAPI()

    @app.on_event("shutdown")
    def _shutdown() -> None:
        set_current_gateway(None)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await manager.handle(websocket)

    return app


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    """本地启动入口。"""

    import uvicorn

    uvicorn.run(create_app(), host=host, port=port)


def _extract_session_id(context: Optional[Dict[str, Any]]) -> Optional[str]:
    if not context:
        return None
    value = context.get("session_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _resolve_active_session_id(
    auth_store: Dict[str, Optional[Dict[str, Any]]],
) -> Optional[str]:
    """在缺少显式 session_id 时，选择一个可用的会话。

    优先挑选已完成认证的会话（auth_payload 非 None）。
    """
    preferred = None
    for session_id, auth_payload in auth_store.items():
        if auth_payload is not None:
            return session_id
        if preferred is None:
            preferred = session_id
    return preferred


def _wait_for_active_session_id(
    auth_store: Dict[str, Optional[Dict[str, Any]]],
    timeout: Optional[float] = None,
    interval: float = 0.5,
) -> Optional[str]:
    """等待 WebSocket 会话建立，避免首次输入请求丢失。

    Args:
        auth_store: 认证存储，用于查找活跃会话
        timeout: 超时时间（秒），None 表示无限等待
        interval: 检查间隔（秒）
    """
    if timeout is not None:
        deadline = time.time() + max(timeout, 0)
    else:
        deadline = None
    while True:
        session_id = _resolve_active_session_id(auth_store)
        if session_id:
            return session_id
        if deadline is not None and time.time() >= deadline:
            return _resolve_active_session_id(auth_store)
        time.sleep(interval)


def _normalize_auth_payload(payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    return {
        "token": payload.get("token"),
        "password": payload.get("password"),
    }


def _extract_auth_from_headers(websocket: WebSocket) -> Optional[Dict[str, Any]]:
    token = websocket.headers.get("x-jarvis-token")
    password = websocket.headers.get("x-jarvis-password")
    if not token and not password:
        return None
    return {"token": token, "password": password}


def _build_sender(websocket: WebSocket, loop: asyncio.AbstractEventLoop):
    def _sender(message: Dict[str, Any]) -> None:
        asyncio.run_coroutine_threadsafe(websocket.send_json(message), loop)

    return _sender


async def _await_auth_message(
    websocket: WebSocket, gateway: WebGateway
) -> Tuple[Optional[Dict[str, Any]], bool, Optional[str]]:
    try:
        message = await asyncio.wait_for(websocket.receive_json(), timeout=10)
    except Exception:
        return None, False, "gateway auth missing"
    if not isinstance(message, dict) or message.get("type") != "auth":
        return None, False, "gateway auth missing"
    payload = _normalize_auth_payload(message.get("payload") or {})
    authorized, reason = gateway._check_auth(payload)
    return payload, authorized, reason


async def _send_error(websocket: WebSocket, code: str, message: str) -> None:
    await websocket.send_json(
        {"type": "error", "payload": {"code": code, "message": message}}
    )
