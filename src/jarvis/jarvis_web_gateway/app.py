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
from fastapi.middleware.cors import CORSMiddleware

from jarvis.jarvis_gateway.events import GatewayConfirmRequest
from jarvis.jarvis_gateway.events import GatewayConfirmResult
from jarvis.jarvis_gateway.events import GatewayExecutionEvent
from jarvis.jarvis_gateway.events import GatewayInputRequest
from jarvis.jarvis_gateway.events import GatewayInputResult
from jarvis.jarvis_gateway.events import GatewayOutputEvent
from jarvis.jarvis_gateway.gateway import BaseGateway
from jarvis.jarvis_gateway.input_bridge import InputSessionRegistry
from jarvis.jarvis_gateway.manager import set_current_gateway
from jarvis.jarvis_gateway.output_bridge import SessionOutputRouter
from jarvis.jarvis_web_gateway.agent_manager import AgentManager
from jarvis.jarvis_web_gateway.terminal_input_registry import TerminalInputRegistry
from jarvis.jarvis_utils.globals import set_interrupt


# 全局 AgentManager，用于状态变更回调
_global_agent_manager: Optional[AgentManager] = None


def _on_agent_status_change(agent_id: str, status: str, data: Any) -> None:
    """Agent 状态变更回调，发送 WebSocket 通知。

    Args:
        agent_id: Agent ID
        status: 新状态 ("running", "stopped", "error")
        data: 额外数据
    """
    # TODO: 实现 WebSocket 广播，向所有连接的前端发送状态变更通知
    # 这里需要修改 WebSocketConnectionManager 来支持广播
    pass


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
        # 如果没有 session_id，使用保存的 session 或默认的活跃 session
        if not session_id:
            session_id = self._current_session_id or _resolve_active_session_id(
                self._auth_store
            )
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
            session_id = _wait_for_active_session_id(self._auth_store)
            if session_id:
                self._current_session_id = session_id
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
            "mode": request.mode or "multi",  # 默认多行模式
            "preset": request.preset,
            "preset_cursor": request.preset_cursor,
            "metadata": metadata,
        }
        message = {"type": "input_request", "payload": payload}
        self._router.publish(message, session_id=session_id)
        # 保存输入请求，用于重连后恢复
        self._input_registry.save_input_request(session_id, message)
        session = self._input_registry.get_or_create(session_id)
        text = session.wait_for_input()
        return GatewayInputResult(text=text, metadata=metadata)

    def request_confirm(self, request: GatewayConfirmRequest) -> GatewayConfirmResult:
        metadata = dict(request.metadata) if request.metadata else {}
        session_id = metadata.get("session_id")
        if not session_id:
            session_id = _wait_for_active_session_id(self._auth_store)
            if session_id:
                self._current_session_id = session_id
            if session_id:
                metadata["session_id"] = session_id
            else:
                session_id = "default"
                metadata["session_id"] = session_id
        auth_payload = metadata.get("auth") or self._auth_store.get(session_id)
        authorized, reason = self._check_auth(auth_payload)
        if not authorized:
            return GatewayConfirmResult(
                confirmed=request.default if request.default is not None else False,
                metadata={"error": reason}
            )
        payload = {
            "message": request.message,
            "default": request.default,
            "metadata": metadata,
        }
        message = {"type": "confirm", "payload": payload}
        self._router.publish(message, session_id=session_id)
        # 保存确认请求，用于重连后恢复
        self._input_registry.save_confirm_request(session_id, message)
        session = self._input_registry.get_or_create_confirm_session(session_id)
        confirmed = session.wait_for_confirm()
        return GatewayConfirmResult(confirmed=confirmed, metadata=metadata)

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
        await websocket.accept()
        session_id = "default"  # 固定使用 default session，简化重连逻辑
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

        # 检查是否已有活跃连接，如果有则拒绝新连接
        if self._router.has_active_subscribers():
            await _send_error(
                websocket, "CONNECTION_REJECTED", "Already have an active connection"
            )
            await websocket.close()
            return

        self._router.register(
            connection_id,
            _build_sender(websocket, loop),
            session_id=session_id,
        )
        self._input_registry.register_provider(session_id)
        await websocket.send_json(
            {"type": "ready", "payload": {"session_id": session_id}}
        )
        # 恢复待处理的输入请求
        pending_request = self._input_registry.get_input_request(session_id)
        print(
            f"[RECONNECT] session_id={session_id}, pending_request={pending_request is not None}"
        )
        if pending_request:
            session = self._input_registry.get_or_create(session_id)
            print("[RECONNECT] Got session, reconnecting...")
            session.reconnect()
            print(f"[RECONNECT] Sending input_request: {pending_request}")
            await websocket.send_json(pending_request)
        # 恢复待处理的确认请求
        pending_confirm = self._input_registry.get_confirm_request(session_id)
        print(
            f"[RECONNECT] session_id={session_id}, pending_confirm={pending_confirm is not None}"
        )
        if pending_confirm:
            confirm_session = self._input_registry.get_or_create_confirm_session(session_id)
            print("[RECONNECT] Got confirm session, reconnecting...")
            confirm_session.reconnect()
            print(f"[RECONNECT] Sending confirm_request: {pending_confirm}")
            await websocket.send_json(pending_confirm)
        try:
            while True:
                message = await websocket.receive_json()
                await self._handle_message(session_id, message)
        except WebSocketDisconnect:
            pass
        finally:
            self._router.unregister(connection_id, session_id=session_id)
            self._input_registry.unregister_provider(session_id)
            self._input_registry.disconnect_confirm_session(session_id)
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
            return
        if message_type == "confirm_result":
            confirmed = payload.get("confirmed", False)
            self._input_registry.submit_confirm(session_id, confirmed)
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
        if message_type == "manual_interrupt":
            set_interrupt(True)
            return


def create_app() -> FastAPI:
    """创建 FastAPI 应用。"""

    # 创建 AgentManager，并设置状态变更回调
    agent_manager = AgentManager(
        on_status_change=_on_agent_status_change
    )
    # 保存 agent_manager 到全局，以便回调访问
    global _global_agent_manager
    _global_agent_manager = agent_manager

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

    # 添加 CORS 中间件，允许前端跨域访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 生产环境应该指定具体域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def _startup() -> None:
        # 为运行中的 Agent 启动监控任务
        await agent_manager.start_monitoring_for_running_agents()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        # 清理所有 Agent
        await agent_manager.cleanup()
        set_current_gateway(None)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await manager.handle(websocket)

    # HTTP API：创建 Agent
    @app.post("/api/agents")
    async def create_agent(request: Dict[str, Any]) -> Dict[str, Any]:
        """创建 Agent。"""
        try:
            agent_type = request.get("agent_type")
            working_dir = request.get("working_dir")
            name = request.get("name")
            llm_group = request.get("llm_group", "default")
            tool_group = request.get("tool_group", "default")
            config_file = request.get("config_file")
            task = request.get("task")
            additional_args = request.get("additional_args")

            if not agent_type:
                return {"success": False, "error": {"code": "MISSING_AGENT_TYPE", "message": "agent_type is required"}}
            if not working_dir:
                return {"success": False, "error": {"code": "MISSING_WORKING_DIR", "message": "working_dir is required"}}

            agent_info = agent_manager.create_agent(
                agent_type=agent_type,
                working_dir=working_dir,
                name=name,
                llm_group=llm_group,
                tool_group=tool_group,
                config_file=config_file,
                task=task,
                additional_args=additional_args,
            )

            return {"success": True, "data": agent_info}
        except ValueError as e:
            return {"success": False, "error": {"code": "INVALID_ARGUMENT", "message": str(e)}}
        except RuntimeError as e:
            return {"success": False, "error": {"code": "START_FAILED", "message": str(e)}}
        except Exception as e:
            return {"success": False, "error": {"code": "INTERNAL_ERROR", "message": str(e)}}

    # HTTP API：获取 Agent 列表
    @app.get("/api/agents")
    async def get_agents() -> Dict[str, Any]:
        """获取 Agent 列表。"""
        try:
            agents = agent_manager.get_agent_list()
            return {"success": True, "data": agents}
        except Exception as e:
            return {"success": False, "error": {"code": "INTERNAL_ERROR", "message": str(e)}}

    # HTTP API：停止 Agent
    @app.delete("/api/agents/{agent_id}")
    async def stop_agent(agent_id: str) -> Dict[str, Any]:
        """停止 Agent。"""
        try:
            result = agent_manager.stop_agent(agent_id)
            return {"success": True, "data": result}
        except KeyError as e:
            return {"success": False, "error": {"code": "AGENT_NOT_FOUND", "message": str(e)}}
        except Exception as e:
            return {"success": False, "error": {"code": "INTERNAL_ERROR", "message": str(e)}}

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
