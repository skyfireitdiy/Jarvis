# -*- coding: utf-8 -*-
"""Web Gateway FastAPI 应用。

独立服务：通过 WebSocket 对接 Gateway 输入/输出/执行事件。
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
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


class WebGateway(BaseGateway):
    """Web Gateway 实现：桥接输出、输入与执行事件到 WebSocket。"""

    def __init__(
        self,
        router: SessionOutputRouter,
        input_registry: InputSessionRegistry,
        auth_store: Dict[str, Optional[Dict[str, Any]]],
    ) -> None:
        self._router = router
        self._input_registry = input_registry
        self._auth_store = auth_store

    def emit_output(self, event: GatewayOutputEvent) -> None:
        session_id = _extract_session_id(event.context)
        auth_payload = self._auth_store.get(session_id) if session_id else None
        authorized, _ = self._check_auth(auth_payload)
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
        self._router.publish(message, session_id=session_id)

    def request_input(self, request: GatewayInputRequest) -> GatewayInputResult:
        metadata = dict(request.metadata) if request.metadata else {}
        session_id = metadata.get("session_id")
        if not session_id:
            session_id = _resolve_active_session_id(self._auth_store)
            if session_id:
                metadata["session_id"] = session_id
            else:
                session_id = "default"
                metadata["session_id"] = session_id
        auth_payload = metadata.get("auth") or self._auth_store.get(session_id)
        authorized, reason = self._check_auth(auth_payload)
        if not authorized:
            return GatewayInputResult(text="", metadata={"error": reason})
        payload = {
            "tip": request.tip,
            "preset": request.preset,
            "preset_cursor": request.preset_cursor,
            "metadata": metadata,
        }
        message = {"type": "input_request", "payload": payload}
        self._router.publish(message, session_id=session_id)
        session = self._input_registry.get_or_create(session_id)
        text = session.wait_for_input()
        return GatewayInputResult(text=text, metadata=metadata)

    def publish_execution_event(
        self,
        event: GatewayExecutionEvent,
        session_id: Optional[str] = None,
    ) -> None:
        payload = dict(event.payload) if event.payload else {}
        session_id = session_id or payload.get("session_id")
        auth_payload = payload.get("auth") or (
            self._auth_store.get(session_id) if session_id else None
        )
        authorized, _ = self._check_auth(auth_payload)
        if not authorized:
            return
        message_payload = {"event_type": event.event_type, **payload}
        if event.timestamp:
            message_payload["timestamp"] = event.timestamp
        message = {"type": "execution", "payload": message_payload}
        self._router.publish(message, session_id=session_id)


class WebSocketConnectionManager:
    """WebSocket 连接管理。"""

    def __init__(
        self,
        router: SessionOutputRouter,
        input_registry: InputSessionRegistry,
        gateway: WebGateway,
        auth_store: Dict[str, Optional[Dict[str, Any]]],
    ) -> None:
        self._router = router
        self._input_registry = input_registry
        self._gateway = gateway
        self._auth_store = auth_store

    async def handle(self, websocket: WebSocket) -> None:
        await websocket.accept()
        session_id = websocket.query_params.get("session_id") or str(uuid.uuid4())
        connection_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        auth_payload = _extract_auth_from_headers(websocket)
        authorized, reason = self._gateway._check_auth(auth_payload)
        if not authorized:
            auth_payload, authorized, reason = await _await_auth_message(
                websocket, self._gateway
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
        await websocket.send_json({"type": "ready", "payload": {"session_id": session_id}})
        try:
            while True:
                message = await websocket.receive_json()
                await self._handle_message(session_id, message)
        except WebSocketDisconnect:
            pass
        finally:
            self._router.unregister(connection_id, session_id=session_id)
            self._input_registry.unregister_provider(session_id)
            self._auth_store.pop(session_id, None)

    async def _handle_message(self, session_id: str, message: Any) -> None:
        if not isinstance(message, dict):
            return
        message_type = message.get("type")
        payload = message.get("payload") or {}
        if message_type == "auth":
            auth_payload = _normalize_auth_payload(payload)
            authorized, _ = self._gateway._check_auth(auth_payload)
            if not authorized:
                return
            self._auth_store[session_id] = auth_payload
            return
        if message_type == "input_result":
            text = payload.get("text", "")
            self._input_registry.submit_input(session_id, text)


def create_app() -> FastAPI:
    """创建 FastAPI 应用。"""

    router = SessionOutputRouter()
    input_registry = InputSessionRegistry()
    auth_store: Dict[str, Optional[Dict[str, Any]]] = {}
    gateway = WebGateway(router, input_registry, auth_store)
    manager = WebSocketConnectionManager(router, input_registry, gateway, auth_store)

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
    await websocket.send_json({"type": "error", "payload": {"code": code, "message": message}})
