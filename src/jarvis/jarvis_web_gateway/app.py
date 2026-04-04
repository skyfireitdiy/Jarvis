# -*- coding: utf-8 -*-
"""Web Gateway FastAPI 应用。

独立服务：通过 WebSocket 对接 Gateway 输入/输出/执行事件。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import signal
import subprocess
import uuid
from datetime import datetime
from urllib.parse import parse_qsl
from urllib.parse import unquote
from typing import Any
from typing import Callable
from typing import Dict
from typing import Optional
from typing import Tuple

from fastapi import Depends, FastAPI, Request, Response, WebSocket
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
from jarvis.jarvis_web_gateway.agent_proxy_manager import (
    AgentProxyManager,
    AgentNotFoundError,
    AgentNotRunningError,
    ProxyConnectionError,
)
from jarvis.jarvis_web_gateway.token_manager import (
    generate_gateway_token,
)
from jarvis.jarvis_web_gateway.node_config import (
    NodeRuntimeConfig,
    build_node_runtime_config,
)
from jarvis.jarvis_web_gateway.node_manager import (
    ChildNodeClient,
    NodeConnectionManager,
)
from jarvis.jarvis_web_gateway.node_protocol import (
    AGENT_CREATE_REQUEST,
    AGENT_HTTP_REQUEST,
    AGENT_LIST_REQUEST,
    AGENT_STOP_REQUEST,
    AGENT_DELETE_REQUEST,
    NODE_HTTP_PROXY_REQUEST,
    AGENT_WS_REQUEST,
    DIRECTORY_LIST_REQUEST,
)
from jarvis.jarvis_web_gateway.node_runtime import AgentRouteInfo, NodeRuntime
from jarvis.jarvis_web_gateway.terminal_input_registry import TerminalInputRegistry
from jarvis.jarvis_web_gateway.terminal_session_manager import TerminalSessionManager
from jarvis.jarvis_web_gateway.timer_manager import TimerManager
from jarvis.jarvis_service.cli import get_single_instance_lock_path
from jarvis.jarvis_utils.globals import set_interrupt

logger = logging.getLogger(__name__)

# 导入 agent 状态管理器（用于处理 get_status 消息）
try:
    from jarvis.jarvis_agent.jarvis import get_agent_status_manager
except ImportError:
    # 如果 jarvis_agent 不可用，使用 None
    get_agent_status_manager = None  # type: ignore

# 导入配置相关函数
from jarvis.jarvis_utils.config import (
    GLOBAL_CONFIG_DATA,
    get_global_config_data,
    get_gateway_auth_config,
)


# 全局 AgentManager，用于状态变更回调
_global_agent_manager: Optional[AgentManager] = None

# 状态更新回调函数
_status_update_callback: Optional[Callable[[str], None]] = None

# 全局当前执行状态（用于 /status 接口）
_current_execution_status: str = "running"


def get_current_execution_status() -> str:
    """获取当前执行状态。

    Returns:
        str: 当前执行状态（running/waiting_multi/waiting_single）
    """
    global _current_execution_status
    return _current_execution_status


# 全局 SessionOutputRouter，用于推送状态更新
_router: Optional[SessionOutputRouter] = None

# 全局 TerminalSessionManager，用于独立终端会话管理
_terminal_session_manager: Optional[TerminalSessionManager] = None

MAX_FILE_SIZE_BYTES = 1024 * 1024
BINARY_FILE_SAMPLE_SIZE = 4096
GLOBAL_SEARCH_MAX_QUERY_LENGTH = 200
GLOBAL_SEARCH_DEFAULT_MAX_RESULTS = 100
GLOBAL_SEARCH_MAX_RESULTS_LIMIT = 500
GLOBAL_SEARCH_COMMAND_TIMEOUT_SECONDS = 30
GLOBAL_SEARCH_MAX_LINE_LENGTH = 2000
GLOBAL_SEARCH_MAX_GLOB_LENGTH = 500


def set_status_update_callback(callback: Optional[Callable[[str], None]]) -> None:
    """设置状态更新回调函数。

    Args:
        callback: 回调函数，接收状态字符串 ("running"/"waiting_multi"/"waiting_single")
    """
    global _status_update_callback
    _status_update_callback = callback


def _update_status(status: str) -> None:
    """更新状态。

    Args:
        status: 状态字符串
    """

    global _status_update_callback, _router, _current_execution_status  # 添加 _router 到全局
    _current_execution_status = status  # 更新全局状态

    # 1. 调用回调函数更新本地状态
    if _status_update_callback:
        try:
            _status_update_callback(status)
        except Exception:
            # 静默忽略状态更新失败，不影响主流程
            pass

    # 2. 通过 WebSocket 推送状态变化给前端
    if _router:
        try:
            # 单连接模式，固定使用 default session_id
            session_id = "default"
            # 推送状态变化消息
            message = {"type": "status_update", "payload": {"execution_status": status}}
            _router.publish(message, session_id=session_id)
        except Exception:
            pass


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

    def emit_output(self, event: GatewayOutputEvent) -> None:
        # 单连接模式，固定使用 default session_id
        session_id = "default"
        auth_payload = self._auth_store.get(session_id)
        authorized, _ = self._check_auth(auth_payload)
        if not authorized:
            return
        context = dict(event.context) if event.context else {}
        payload = {
            "text": event.text,
            "output_type": event.output_type,
            "timestamp": event.timestamp,
            "lang": event.lang,
            "traceback": event.traceback,
            "section": event.section,
            "context": context,
        }
        if context.get("agent_id"):
            payload["agent_id"] = context["agent_id"]
        message = {"type": "output", "payload": payload}
        self._router.publish(message, session_id=session_id)

    def request_input(self, request: GatewayInputRequest) -> GatewayInputResult:
        # 单连接模式，固定使用 default session_id
        session_id = "default"
        metadata = dict(request.metadata) if request.metadata else {}
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

        # 更新状态为等待输入
        if request.mode == "single":
            _update_status("waiting_single")
        else:
            _update_status("waiting_multi")

        session = self._input_registry.get_or_create(session_id)
        text = session.wait_for_input()

        # 输入完成，恢复为运行状态
        _update_status("running")

        return GatewayInputResult(text=text, metadata=metadata)

    def request_confirm(self, request: GatewayConfirmRequest) -> GatewayConfirmResult:
        # 单连接模式，固定使用 default session_id
        session_id = "default"
        metadata = dict(request.metadata) if request.metadata else {}
        metadata["session_id"] = session_id
        auth_payload = metadata.get("auth") or self._auth_store.get(session_id)
        authorized, reason = self._check_auth(auth_payload)
        if not authorized:
            return GatewayConfirmResult(
                confirmed=request.default if request.default is not None else False,
                metadata={"error": reason},
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

        # 更新状态为等待单行输入（确认）
        _update_status("waiting_single")

        session = self._input_registry.get_or_create_confirm_session(session_id)
        confirmed = session.wait_for_confirm()

        # 确认完成，恢复为运行状态
        _update_status("running")

        return GatewayConfirmResult(confirmed=confirmed, metadata=metadata)

    def publish_execution_event(
        self,
        event: GatewayExecutionEvent,
        session_id: Optional[str] = None,
    ) -> None:
        # 单连接模式，固定使用 default session_id
        session_id = "default"
        payload = dict(event.payload) if event.payload else {}
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
        self._connection_lock_enabled = (
            False  # 连接锁定模式：True=拒绝新连接，False=允许新连接替换旧连接
        )
        self._active_connections: Dict[str, tuple[str, WebSocket]] = {}
        self._connection_state_lock = asyncio.Lock()

    async def handle(self, websocket: WebSocket) -> None:
        await websocket.accept(subprotocol="jarvis-ws")
        session_id = "default"  # 固定使用 default session，简化重连逻辑
        connection_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()

        async with self._connection_state_lock:
            existing_connection = self._active_connections.get(session_id)
            if existing_connection:
                if self._connection_lock_enabled:
                    await _send_error(
                        websocket,
                        "CONNECTION_REJECTED",
                        "Already have an active connection (connection lock enabled)",
                    )
                    await websocket.close()
                    return
                old_connection_id, old_websocket = existing_connection
                print(
                    "[WS CONNECTION] New connection replacing old one (connection lock disabled)"
                )
                try:
                    await _send_error(
                        old_websocket,
                        "CONNECTION_REPLACED",
                        "Connection replaced by a new login",
                    )
                except Exception:
                    pass
                try:
                    await old_websocket.close()
                except Exception:
                    pass
                self._router.unregister(old_connection_id, session_id=session_id)
                self._active_connections.pop(session_id, None)
                self._auth_store.pop(session_id, None)

        auth_payload = _extract_auth_from_headers(websocket)
        authorized, reason = self._gateway._check_auth(auth_payload)
        if not authorized:
            await _send_error(websocket, "AUTH_FAILED", reason or "auth failed")
            await websocket.close()
            return

        self._auth_store[session_id] = auth_payload
        print(
            "[WS AUTH] authenticated "
            f"session_id={session_id} connection_id={connection_id} "
            f"has_token={bool((auth_payload or {}).get('token'))} "
            f"auth_store_keys={list(self._auth_store.keys())}"
        )
        self._router.register(
            connection_id,
            _build_sender(websocket, loop),
            session_id=session_id,
        )
        async with self._connection_state_lock:
            self._active_connections[session_id] = (connection_id, websocket)
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
            confirm_session = self._input_registry.get_or_create_confirm_session(
                session_id
            )
            print("[RECONNECT] Got confirm session, reconnecting...")
            confirm_session.reconnect()
            print(f"[RECONNECT] Sending confirm_request: {pending_confirm}")
            await websocket.send_json(pending_confirm)
        try:
            while True:
                message = await websocket.receive_json()
                await self._handle_message(session_id, message)
        except WebSocketDisconnect:
            print(
                "[WS DISCONNECT] "
                f"session_id={session_id} connection_id={connection_id} "
                f"active_auth={session_id in self._auth_store}"
            )
        finally:
            print(
                "[WS CLEANUP] begin "
                f"session_id={session_id} connection_id={connection_id} "
                f"active_auth_before={session_id in self._auth_store}"
            )
            self._router.unregister(connection_id, session_id=session_id)
            self._input_registry.unregister_provider(session_id)
            self._input_registry.disconnect_confirm_session(session_id)
            async with self._connection_state_lock:
                active_connection = self._active_connections.get(session_id)
                if active_connection and active_connection[0] == connection_id:
                    self._active_connections.pop(session_id, None)
                    self._auth_store.pop(session_id, None)
            print(
                "[WS CLEANUP] end "
                f"session_id={session_id} connection_id={connection_id} "
                f"active_auth_after={session_id in self._auth_store}"
            )

    async def _handle_message(self, session_id: str, message: Any) -> None:
        if not isinstance(message, dict):
            return
        message_type = message.get("type")
        payload = message.get("payload") or {}
        if message_type == "connection_lock":
            enabled = payload.get("enabled", False)
            self._connection_lock_enabled = enabled
            print(
                f"[WS CONNECTION LOCK] Connection lock {'enabled' if enabled else 'disabled'}"
            )
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
        if message_type == "get_status":
            # 处理前端主动请求状态的请求
            if get_agent_status_manager is not None:
                try:
                    status_manager = get_agent_status_manager()
                    current_status = status_manager.get_status()
                    # 返回 status_update 消息
                    status_message = {
                        "type": "status_update",
                        "payload": {"execution_status": current_status},
                    }
                    self._router.publish(status_message, session_id=session_id)
                    print(f"[GET_STATUS] Sent agent status: {current_status}")
                except Exception as e:
                    # 获取状态失败
                    print(f"[GET_STATUS] Failed to get status: {e}")
            return
        # 独立终端会话消息处理
        if message_type == "terminal_create":
            interpreter = payload.get("interpreter") or os.environ.get("SHELL", "bash")
            raw_working_dir = payload.get("working_dir")
            working_dir = str(raw_working_dir).strip() if raw_working_dir else ""
            if not working_dir:
                working_dir = str(pathlib.Path.home())
            if _terminal_session_manager:
                terminal_id, error = _terminal_session_manager.create_session(
                    interpreter=interpreter,
                    working_dir=working_dir,
                    stream_publisher=self._router,
                    session_id=session_id,
                )
                if terminal_id:
                    message = {
                        "type": "terminal_created",
                        "payload": {
                            "terminal_id": terminal_id,
                            "interpreter": interpreter,
                            "working_dir": working_dir,
                        },
                    }
                    self._router.publish(message, session_id=session_id)
            return
        if message_type == "terminal_close":
            terminal_id = payload.get("terminal_id")
            if terminal_id and _terminal_session_manager:
                _terminal_session_manager.close_session(terminal_id)
                message = {
                    "type": "terminal_closed",
                    "payload": {"terminal_id": terminal_id},
                }
                self._router.publish(message, session_id=session_id)
            return
        if message_type == "terminal_session_input":
            terminal_id = payload.get("terminal_id")
            data = payload.get("data", "")
            if terminal_id and _terminal_session_manager:
                _terminal_session_manager.write_input(terminal_id, data)
            return
        if message_type == "terminal_session_resize":
            terminal_id = payload.get("terminal_id")
            rows = payload.get("rows")
            cols = payload.get("cols")
            if terminal_id and _terminal_session_manager:
                try:
                    rows_int = int(rows)
                    cols_int = int(cols)
                except (TypeError, ValueError):
                    return
                _terminal_session_manager.resize(terminal_id, rows_int, cols_int)
            return


def create_app(
    custom_app: Optional[FastAPI] = None,
    node_config: Optional[NodeRuntimeConfig] = None,
) -> FastAPI:
    """创建 FastAPI 应用。

    Args:
        custom_app: 自定义 FastAPI app，用于添加额外的路由（如状态查询）

    Returns:
        FastAPI 应用实例
    """

    node_config = node_config or build_node_runtime_config()
    node_runtime = NodeRuntime(node_config)

    # 生成并设置 Gateway Token（启动时生成一次，永久使用）
    gateway_token = os.environ.get("JARVIS_AUTH_TOKEN", generate_gateway_token())
    # 统一设置到环境变量，供子进程（Agent）使用
    os.environ["JARVIS_AUTH_TOKEN"] = gateway_token
    print(f"[GATEWAY] Generated token: {gateway_token}")

    # 因为 uvicorn.run() 启动子进程会导致 GLOBAL_CONFIG_DATA 被重置，需要重新加载配置
    from jarvis.jarvis_utils.utils import init_env

    init_env(welcome_str="", config_file=None)

    # 创建 AgentManager，并设置状态变更回调
    agent_manager = AgentManager(on_status_change=_on_agent_status_change)
    # 保存 agent_manager 到全局，以便回调访问
    global _global_agent_manager
    _global_agent_manager = agent_manager

    # 创建 AgentProxyManager
    agent_proxy_manager = AgentProxyManager(agent_manager)
    node_connection_manager = NodeConnectionManager(
        node_runtime,
        agent_manager,
        agent_proxy_manager,
        node_http_dispatcher=None,
    )
    child_node_client = (
        ChildNodeClient(
            node_runtime,
            agent_manager,
            agent_proxy_manager,
            node_connection_manager,
        )
        if node_config.is_child
        else None
    )

    router = SessionOutputRouter()
    input_registry = InputSessionRegistry()
    terminal_input_registry = TerminalInputRegistry()
    terminal_session_manager = TerminalSessionManager(max_sessions=5)

    def _build_callback_from_metadata(metadata: Dict[str, Any]):
        action_metadata = metadata.get("action")
        if not isinstance(action_metadata, dict):
            raise ValueError("Persisted timer metadata.action must be an object")
        return _build_timer_action({"action": action_metadata})[0]

    timer_manager = TimerManager(task_factory=_build_callback_from_metadata)

    # 保存 router 到全局，用于状态更新时推送消息
    global _router, _terminal_session_manager
    _router = router
    _terminal_session_manager = terminal_session_manager
    auth_store: Dict[str, Optional[Dict[str, Any]]] = {}
    gateway = WebGateway(router, input_registry, auth_store, terminal_input_registry)
    manager = WebSocketConnectionManager(
        router, input_registry, terminal_input_registry, gateway, auth_store
    )

    set_current_gateway(gateway)

    # 使用自定义 app 或创建新 app
    app = custom_app if custom_app is not None else FastAPI()
    app.state.timer_manager = timer_manager
    app.state.node_config = node_config
    app.state.node_runtime = node_runtime
    app.state.agent_manager = agent_manager
    app.state.agent_proxy_manager = agent_proxy_manager
    app.state.node_connection_manager = node_connection_manager
    app.state.child_node_client = child_node_client

    # 添加 CORS 中间件，允许前端跨域访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 生产环境应该指定具体域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # HTTP 认证依赖
    def verify_token(request: Request) -> None:
        """验证 HTTP 请求的 Token。

        Args:
            request: FastAPI Request 对象

        Raises:
            HTTPException: Token 无效时抛出 401 错误
        """
        from jarvis.jarvis_web_gateway.token_manager import validate_gateway_token
        from fastapi import HTTPException

        # 从 Authorization Header 提取 Token
        authorization = request.headers.get("Authorization")
        if not authorization:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "MISSING_TOKEN",
                    "message": "Authorization header is required",
                },
            )

        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "INVALID_TOKEN_FORMAT",
                    "message": "Authorization header must be 'Bearer <token>'",
                },
            )

        token = parts[1]

        # 验证 Token
        if not validate_gateway_token(token):
            raise HTTPException(
                status_code=401,
                detail={"code": "INVALID_TOKEN", "message": "Invalid or expired token"},
            )

    def verify_agent_proxy_access(request: Request) -> None:
        """验证 Agent HTTP 代理访问权限。

        已登录会话或 Bearer Token 任一通过即可。
        """
        if manager._auth_store.get("default") is not None:
            return
        verify_token(request)

    @app.on_event("startup")
    async def _startup() -> None:
        # 初始化环境并加载配置文件（已在 run() 函数中调用，此处避免重复）
        # from jarvis.jarvis_utils.utils import init_env
        # init_env(welcome_str="", config_file=None)
        agent_manager.set_event_loop(asyncio.get_running_loop())
        # 为运行中的 Agent 启动监控任务
        await agent_manager.start_monitoring_for_running_agents()
        if node_config.is_master:
            node_runtime.mark_ready()
        else:
            node_runtime.mark_degraded()
            if child_node_client is not None:
                child_node_client.start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        # 清理所有 Agent
        await agent_manager.cleanup()
        # 清理代理管理器
        await agent_proxy_manager.cleanup()
        # 清理所有终端会话
        terminal_session_manager.cleanup()
        if child_node_client is not None:
            await child_node_client.stop()
        timer_manager.shutdown()
        set_current_gateway(None)

    # HTTP API：登录接口
    @app.post("/api/auth/login")
    async def login(request: Dict[str, Any]) -> Dict[str, Any]:
        """登录接口，验证密码并返回 Token。"""
        import logging

        logger = logging.getLogger(__name__)

        try:
            raw_password = request.get("password")
            password = str(raw_password).strip() if raw_password is not None else ""
            logger.info(f"[AUTH] Login attempt with password length: {len(password)}")

            # 验证密码（get_gateway_auth_config 已集成环境变量优先逻辑）
            config = get_gateway_auth_config()
            expected_password = config.get("password") if config else None

            # 判断密码来源：检查环境变量和配置文件
            password_source = (
                "环境变量"
                if os.environ.get("JARVIS_GATEWAY_PASSWORD")
                else "配置文件"
                if expected_password
                else "未设置"
            )
            logger.info(
                f"[AUTH] Password source: {password_source}, set: {'yes (length: ' + str(len(expected_password)) + ')' if expected_password else 'no'}"
            )

            # 未配置密码时，允许直接登录获取令牌
            if not expected_password:
                logger.info("[AUTH] Gateway password is not configured, login allowed")
            else:
                if not password:
                    logger.warning(f"[AUTH] Login failed: password is empty")
                    return {
                        "success": False,
                        "error": {
                            "code": "MISSING_PASSWORD",
                            "message": "password is required",
                        },
                    }

                # 如果设置了密码，进行验证
                if password != expected_password:
                    logger.warning(f"[AUTH] Login failed: password mismatch")
                    return {
                        "success": False,
                        "error": {
                            "code": "AUTH_FAILED",
                            "message": "Invalid password",
                        },
                    }

            has_authorized_connection = manager._auth_store.get("default") is not None
            if manager._connection_lock_enabled and has_authorized_connection:
                logger.warning(
                    "[AUTH] Login rejected: connection lock enabled and an authorized connection already exists"
                )
                return {
                    "success": False,
                    "error": {
                        "code": "CONNECTION_LOCKED",
                        "message": "An authenticated connection already exists",
                    },
                }

            logger.info(f"[AUTH] Password verification passed")
            # 如果没有配置密码或密码验证通过，返回预生成的 Token（从环境变量读取）
            token = os.environ.get("JARVIS_AUTH_TOKEN")

            if not token:
                logger.error(f"[AUTH] Login failed: Token not generated")
                return {
                    "success": False,
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "Token not generated",
                    },
                }
            logger.info(f"[AUTH] Login successful")
            return {
                "success": True,
                "data": {
                    "token": token,
                    "note": "Token is valid until Web Gateway restarts",
                },
            }
        except Exception as e:
            print(f"[AUTH DEBUG] 登录过程发生异常: {type(e).__name__}: {e}")
            logger.error(f"[AUTH] Login failed with exception: {type(e).__name__}: {e}")
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await manager.handle(websocket)

    @app.websocket("/ws/node")
    async def node_websocket_endpoint(websocket: WebSocket) -> None:
        if not node_config.is_master:
            await websocket.accept()
            await _send_error(
                websocket, "UNSUPPORTED", "child mode does not accept node connections"
            )
            await websocket.close(code=4404)
            return
        await node_connection_manager.handle_node_websocket(websocket)

    # WebSocket 代理：代理到 Agent WebSocket
    @app.websocket("/api/agent/{agent_id}/ws")
    async def agent_websocket_proxy(agent_id: str, websocket: WebSocket) -> None:
        """代理 WebSocket 连接到指定 Agent。

        Args:
            agent_id: Agent ID
            websocket: 客户端 WebSocket 连接
        """
        logger = logging.getLogger(__name__)
        logger.info(f"[WS PROXY] New WebSocket connection for agent {agent_id}")

        auth_payload = _extract_auth_from_headers(websocket)
        if auth_payload is not None:
            authorized, reason = gateway._check_auth(auth_payload)
        else:
            authorized = manager._auth_store.get("default") is not None
            reason = "Authentication required"
        if not authorized:
            await websocket.accept(subprotocol="jarvis-ws")
            await _send_error(websocket, "AUTH_FAILED", reason or "Invalid token")
            await websocket.close(code=4401, reason="Unauthorized")
            return

        await websocket.accept(subprotocol="jarvis-ws")

        requested_node_id = str(websocket.query_params.get("node_id") or "").strip()
        route = node_runtime.agent_route_registry.get(agent_id)
        target_node_id = requested_node_id
        if not target_node_id and route is not None:
            target_node_id = str(route.node_id or "").strip()

        if target_node_id and target_node_id not in (
            node_runtime.local_node_id,
            "master",
        ):
            remote_ws_session_id = str(uuid.uuid4())
            try:
                open_response = await node_connection_manager.send_request_to_node(
                    target_node_id,
                    AGENT_WS_OPEN_REQUEST,
                    {
                        "agent_id": agent_id,
                        "path": "ws",
                        "session_id": remote_ws_session_id,
                    },
                )
                open_payload = open_response.get("payload") or {}
                if not open_payload.get("success"):
                    await websocket.close(
                        code=4003,
                        reason=(open_payload.get("error") or {}).get(
                            "message", "Remote websocket open failed"
                        ),
                    )
                    return

                async def forward_client_to_remote() -> None:
                    while True:
                        data = await websocket.receive_text()
                        send_response = (
                            await node_connection_manager.send_request_to_node(
                                target_node_id,
                                AGENT_WS_SEND_REQUEST,
                                {
                                    "session_id": remote_ws_session_id,
                                    "messages": [data],
                                },
                            )
                        )
                        send_payload = send_response.get("payload") or {}
                        if not send_payload.get("success"):
                            raise RuntimeError(
                                (send_payload.get("error") or {}).get(
                                    "message", "Remote websocket send failed"
                                )
                            )

                async def forward_remote_to_client() -> None:
                    while True:
                        recv_response = (
                            await node_connection_manager.send_request_to_node(
                                target_node_id,
                                AGENT_WS_RECV_REQUEST,
                                {
                                    "session_id": remote_ws_session_id,
                                    "timeout": 1.0,
                                },
                                timeout=65.0,
                            )
                        )
                        recv_payload = recv_response.get("payload") or {}
                        if not recv_payload.get("success"):
                            raise RuntimeError(
                                (recv_payload.get("error") or {}).get(
                                    "message", "Remote websocket receive failed"
                                )
                            )
                        for item in recv_payload.get("messages") or []:
                            await websocket.send_text(str(item))

                client_to_remote_task = asyncio.create_task(forward_client_to_remote())
                remote_to_client_task = asyncio.create_task(forward_remote_to_client())
                done, pending = await asyncio.wait(
                    {client_to_remote_task, remote_to_client_task},
                    return_when=asyncio.FIRST_EXCEPTION,
                )
                for task in pending:
                    task.cancel()
                for task in done:
                    exc = task.exception()
                    if exc is not None:
                        raise exc
            except Exception as e:
                logger.error(f"[WS PROXY] Remote websocket proxy error: {e}")
                await websocket.close(code=4003, reason="Remote websocket proxy failed")
            finally:
                try:
                    await node_connection_manager.send_request_to_node(
                        target_node_id,
                        AGENT_WS_CLOSE_REQUEST,
                        {"session_id": remote_ws_session_id},
                    )
                except Exception as close_exc:
                    logger.warning(
                        f"[WS PROXY] Remote websocket close warning: {close_exc}"
                    )
            return

        try:
            await agent_proxy_manager.proxy_websocket(websocket, agent_id)
        except AgentNotFoundError:
            logger.error(f"[WS PROXY] Agent not found: {agent_id}")
            await websocket.close(code=4000, reason="Agent not found")
        except AgentNotRunningError as e:
            logger.error(f"[WS PROXY] Agent not running: {e}")
            await websocket.close(code=4001, reason="Agent not running")
        except ProxyConnectionError as e:
            logger.error(f"[WS PROXY] Proxy connection error: {e}")
            await websocket.close(code=4002, reason="Proxy connection failed")
        except Exception as e:
            logger.error(f"[WS PROXY] Unexpected error: {e}")
            await websocket.close(code=4999, reason="Internal error")
        finally:
            logger.info(f"[WS PROXY] WebSocket connection closed for agent {agent_id}")

    @app.api_route(
        "/api/node/{node_id}/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        dependencies=[Depends(verify_token)],
    )
    async def node_http_proxy(node_id: str, path: str, request: Request) -> Response:
        """统一节点 HTTP 代理。"""
        try:
            normalized_node_id = str(node_id or "").strip()
            if not normalized_node_id:
                return Response(
                    content='{"error": "node_id is required"}',
                    status_code=400,
                    media_type="application/json",
                )
            body = (await request.body()).decode("utf-8", errors="replace")
            if normalized_node_id in (node_runtime.local_node_id, "master"):
                result = await _dispatch_node_http_request(
                    method=request.method,
                    path=path,
                    query=str(request.query_params),
                    headers=dict(request.headers),
                    body=body,
                )
                return Response(
                    content=result.get("body", "{}"),
                    status_code=int(result.get("status_code", 200)),
                    media_type="application/json",
                )
            response = await node_connection_manager.send_request_to_node(
                normalized_node_id,
                NODE_HTTP_PROXY_REQUEST,
                {
                    "method": request.method,
                    "path": path,
                    "query": str(request.query_params),
                    "headers": dict(request.headers),
                    "body": body,
                },
            )
            payload = response.get("payload") or {}
            if not payload.get("success"):
                error = payload.get("error") or {}
                return Response(
                    content=f'{{"error": "{error.get("message", "Node HTTP proxy failed")}"}}',
                    status_code=502,
                    media_type="application/json",
                )
            return Response(
                content=payload.get("body", ""),
                status_code=int(payload.get("status_code", 200)),
                headers=payload.get("headers") or {},
                media_type=(payload.get("headers") or {}).get("content-type"),
            )
        except Exception as e:
            logger.error(f"[NODE HTTP PROXY] error node_id={node_id} path={path}: {e}")
            return Response(
                content='{"error": "Node HTTP proxy failed"}',
                status_code=502,
                media_type="application/json",
            )

    # HTTP 代理：代理到 Agent HTTP API
    @app.api_route(
        "/api/agent/{agent_id}/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        dependencies=[Depends(verify_agent_proxy_access)],
    )
    async def agent_http_proxy(agent_id: str, path: str, request: Request) -> Response:
        """代理 HTTP 请求到指定 Agent。

        Args:
            agent_id: Agent ID
            path: 目标路径
            request: FastAPI Request 对象

        Returns:
            代理的 HTTP 响应
        """
        logger = logging.getLogger(__name__)
        logger.info(f"[HTTP PROXY] {request.method} /api/agent/{agent_id}/{path}")

        route = node_runtime.agent_route_registry.get(agent_id)
        if route is not None and route.node_id not in (
            node_runtime.local_node_id,
            "master",
        ):
            try:
                body = (await request.body()).decode("utf-8", errors="replace")
                response = await node_connection_manager.send_request_to_node(
                    route.node_id,
                    AGENT_HTTP_REQUEST,
                    {
                        "agent_id": agent_id,
                        "method": request.method,
                        "path": path,
                        "query": str(request.query_params),
                        "headers": dict(request.headers),
                        "body": body,
                    },
                )
                payload = response.get("payload") or {}
                if not payload.get("success"):
                    error = payload.get("error") or {}
                    return Response(
                        content=f'{{"error": "{error.get("message", "Remote HTTP proxy failed")}"}}',
                        status_code=502,
                        media_type="application/json",
                    )
                return Response(
                    content=payload.get("body", ""),
                    status_code=int(payload.get("status_code", 200)),
                    headers=payload.get("headers") or {},
                    media_type=(payload.get("headers") or {}).get("content-type"),
                )
            except Exception as e:
                logger.error(f"[HTTP PROXY] Remote HTTP proxy error: {e}")
                return Response(
                    content='{"error": "Remote HTTP proxy failed"}',
                    status_code=502,
                    media_type="application/json",
                )

        try:
            return await agent_proxy_manager.proxy_http_request(request, agent_id, path)
        except AgentNotFoundError:
            logger.error(f"[HTTP PROXY] Agent not found: {agent_id}")
            return Response(
                content='{"error": "Agent not found"}',
                status_code=404,
                media_type="application/json",
            )
        except AgentNotRunningError as e:
            logger.error(f"[HTTP PROXY] Agent not running: {e}")
            return Response(
                content='{"error": "Agent not running"}',
                status_code=503,
                media_type="application/json",
            )
        except ProxyConnectionError as e:
            logger.error(f"[HTTP PROXY] Proxy connection error: {e}")
            return Response(
                content='{"error": "Proxy connection failed"}',
                status_code=502,
                media_type="application/json",
            )
        except Exception as e:
            logger.error(f"[HTTP PROXY] Unexpected error: {e}")
            return Response(
                content='{"error": "Internal error"}',
                status_code=500,
                media_type="application/json",
            )

    @app.get("/api/node/status", dependencies=[Depends(verify_token)])
    async def get_node_status() -> Dict[str, Any]:
        return {
            "success": True,
            "data": {
                "node": node_config.to_dict(),
                "runtime_status": node_runtime.status,
                "token_sync": {
                    "last_synced_at": node_runtime.token_sync_state.last_synced_at,
                    "sync_status": node_runtime.token_sync_state.sync_status,
                    "source_node_id": node_runtime.token_sync_state.source_node_id,
                    "error_message": node_runtime.token_sync_state.error_message,
                },
                "nodes": node_runtime.node_registry.list_all(),
                "agent_routes": node_runtime.agent_route_registry.list_all(),
            },
        }

    @app.post("/api/service/restart", dependencies=[Depends(verify_token)])
    async def restart_service() -> Dict[str, Any]:
        """请求 jarvis-service 通过 SIGUSR1 重启服务。"""
        try:
            lock_file_path = get_single_instance_lock_path()
            if not lock_file_path.exists():
                return {
                    "success": False,
                    "error": {
                        "code": "UNSUPPORTED",
                        "message": "当前环境不支持重启：未检测到 jarvis-service 锁文件",
                    },
                }

            service_pid_text = lock_file_path.read_text(encoding="utf-8").strip()
            if not service_pid_text:
                return {
                    "success": False,
                    "error": {
                        "code": "UNSUPPORTED",
                        "message": "当前环境不支持重启：未检测到 service PID",
                    },
                }

            service_pid = int(service_pid_text)
            os.kill(service_pid, signal.SIGUSR1)
            return {
                "success": True,
                "data": {
                    "pid": service_pid,
                    "message": "已请求 jarvis-service 重启服务",
                },
            }
        except (ValueError, ProcessLookupError):
            return {
                "success": False,
                "error": {
                    "code": "UNSUPPORTED",
                    "message": "当前环境不支持重启：未通过 jarvis-service 启动",
                },
            }
        except PermissionError:
            return {
                "success": False,
                "error": {
                    "code": "PERMISSION_DENIED",
                    "message": "无权限向 jarvis-service 发送重启信号",
                },
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：创建 Agent（需要认证）
    @app.post("/api/agents", dependencies=[Depends(verify_token)])
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
            worktree = bool(request.get("worktree", False))
            target_node_id = str(request.get("node_id") or "").strip()

            if not agent_type:
                return {
                    "success": False,
                    "error": {
                        "code": "MISSING_AGENT_TYPE",
                        "message": "agent_type is required",
                    },
                }
            if not working_dir:
                return {
                    "success": False,
                    "error": {
                        "code": "MISSING_WORKING_DIR",
                        "message": "working_dir is required",
                    },
                }

            resolved_target_node = target_node_id or node_runtime.local_node_id

            if resolved_target_node not in (node_runtime.local_node_id, "master"):
                node_info = node_runtime.node_registry.get(resolved_target_node)
                if node_info is None:
                    return {
                        "success": False,
                        "error": {
                            "code": "NODE_NOT_FOUND",
                            "message": f"Node not found: {resolved_target_node}",
                        },
                    }
                if node_info.status != "online":
                    return {
                        "success": False,
                        "error": {
                            "code": "NODE_OFFLINE",
                            "message": f"Node is offline: {resolved_target_node}",
                        },
                    }
                response = await node_connection_manager.send_request_to_node(
                    resolved_target_node,
                    AGENT_CREATE_REQUEST,
                    {
                        "agent_type": agent_type,
                        "working_dir": working_dir,
                        "name": name,
                        "llm_group": llm_group,
                        "tool_group": tool_group,
                        "config_file": config_file,
                        "task": task,
                        "additional_args": additional_args,
                        "worktree": worktree,
                    },
                )
                payload = response.get("payload") or {}
                if not payload.get("success"):
                    error = payload.get("error") or {}
                    return {
                        "success": False,
                        "error": {
                            "code": error.get("code", "AGENT_CREATE_FAILED"),
                            "message": error.get(
                                "message", "Remote agent creation failed"
                            ),
                        },
                    }
                agent_info = payload.get("agent_info") or {}
                node_runtime.agent_route_registry.register(
                    AgentRouteInfo(
                        agent_id=agent_info["agent_id"],
                        node_id=resolved_target_node,
                        status=agent_info.get("status", "running"),
                        working_dir=agent_info.get("working_dir"),
                        port=agent_info.get("port"),
                    )
                )
                return {"success": True, "data": agent_info}

            # 从环境变量获取当前 Token 并传递给 Agent
            auth_token = os.environ.get("JARVIS_AUTH_TOKEN")

            agent_info = agent_manager.create_agent(
                auth_token=auth_token,
                agent_type=agent_type,
                working_dir=working_dir,
                name=name,
                llm_group=llm_group,
                tool_group=tool_group,
                config_file=config_file,
                task=task,
                additional_args=additional_args,
                worktree=worktree,
                node_id=node_runtime.local_node_id,
            )
            node_runtime.agent_route_registry.register(
                AgentRouteInfo(
                    agent_id=agent_info["agent_id"],
                    node_id=agent_info.get("node_id", node_runtime.local_node_id),
                    status=agent_info.get("status", "running"),
                    working_dir=agent_info.get("working_dir"),
                    port=agent_info.get("port"),
                )
            )

            return {"success": True, "data": agent_info}
        except ValueError as e:
            return {
                "success": False,
                "error": {"code": "INVALID_ARGUMENT", "message": str(e)},
            }
        except RuntimeError as e:
            return {
                "success": False,
                "error": {"code": "START_FAILED", "message": str(e)},
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：获取 Agent 列表
    @app.get("/api/agents", dependencies=[Depends(verify_token)])
    async def get_agents() -> Dict[str, Any]:
        """获取 Agent 列表。"""
        try:
            agents = agent_manager.get_agent_list()
            known_agent_ids: set[str] = set()
            for agent in agents:
                agent_id = str(agent.get("agent_id") or "")
                if agent_id:
                    known_agent_ids.add(agent_id)
                route = node_runtime.agent_route_registry.get(agent.get("agent_id"))
                if route is not None:
                    agent.setdefault("node_id", route.node_id)
                else:
                    agent.setdefault("node_id", node_runtime.local_node_id)

            for node_info in node_runtime.node_registry.list_all():
                node_id = str((node_info or {}).get("node_id") or "")
                node_status = str((node_info or {}).get("status") or "")
                if node_id == node_runtime.local_node_id or node_status != "online":
                    continue
                try:
                    response = await node_connection_manager.send_request_to_node(
                        node_id,
                        AGENT_LIST_REQUEST,
                        {},
                        timeout=10.0,
                    )
                    payload = response.get("payload") or {}
                    if not payload.get("success"):
                        logger.warning(
                            "[AGENTS] remote list failed node_id=%s error=%s",
                            node_id,
                            (payload.get("error") or {}).get("message"),
                        )
                        continue
                    for agent in payload.get("agents") or []:
                        agent_id = str((agent or {}).get("agent_id") or "")
                        if not agent_id or agent_id in known_agent_ids:
                            continue
                        agents.append(agent)
                        known_agent_ids.add(agent_id)
                except Exception as exc:
                    logger.warning(
                        "[AGENTS] remote list request failed node_id=%s error=%s",
                        node_id,
                        exc,
                    )
            return {"success": True, "data": agents}
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：获取模型组列表
    @app.get("/api/model-groups", dependencies=[Depends(verify_token)])
    async def get_model_groups() -> Dict[str, Any]:
        """获取模型组列表。"""
        try:
            config = get_global_config_data()
            llm_groups = config.get("llm_groups", {})
            llms = config.get("llms", {})
            default_llm_group = config.get("llm_group", "")

            if not isinstance(llm_groups, dict) or not llm_groups:
                return {
                    "success": True,
                    "data": [],
                    "default_llm_group": default_llm_group,
                }

            # 转换格式: llm_groups 和 llms -> list of dict
            data = []
            for group_name, group_config in llm_groups.items():
                if not isinstance(group_config, dict):
                    continue

                # 获取各平台的模型配置
                smart_llm_ref = group_config.get("smart_llm", "")
                normal_llm_ref = group_config.get("normal_llm", "")
                cheap_llm_ref = group_config.get("cheap_llm", "")

                # 从 llms 中获取实际模型名称
                smart_model = "-"
                normal_model = "-"
                cheap_model = "-"

                if isinstance(llms, dict):
                    if smart_llm_ref and smart_llm_ref in llms:
                        smart_config = llms[smart_llm_ref]
                        if isinstance(smart_config, dict):
                            smart_model = smart_config.get("model", smart_llm_ref)

                    if normal_llm_ref and normal_llm_ref in llms:
                        normal_config = llms[normal_llm_ref]
                        if isinstance(normal_config, dict):
                            normal_model = normal_config.get("model", normal_llm_ref)

                    if cheap_llm_ref and cheap_llm_ref in llms:
                        cheap_config = llms[cheap_llm_ref]
                        if isinstance(cheap_config, dict):
                            cheap_model = cheap_config.get("model", cheap_llm_ref)

                data.append(
                    {
                        "name": group_name,
                        "smart_model": smart_model,
                        "normal_model": normal_model,
                        "cheap_model": cheap_model,
                    }
                )

            return {
                "success": True,
                "data": data,
                "default_llm_group": default_llm_group,
            }

            return {"success": True, "data": data}
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：停止 Agent
    @app.delete("/api/agents/{agent_id}/stop", dependencies=[Depends(verify_token)])
    async def stop_agent(agent_id: str) -> Dict[str, Any]:
        """停止 Agent。"""
        try:
            route = node_runtime.agent_route_registry.get(agent_id)
            if route is not None and route.node_id not in (
                node_runtime.local_node_id,
                "master",
            ):
                response = await node_connection_manager.send_request_to_node(
                    route.node_id,
                    AGENT_STOP_REQUEST,
                    {"agent_id": agent_id},
                )
                payload = response.get("payload") or {}
                if not payload.get("success"):
                    error = payload.get("error") or {}
                    return {
                        "success": False,
                        "error": {
                            "code": error.get("code", "AGENT_STOP_FAILED"),
                            "message": error.get("message", "Remote agent stop failed"),
                        },
                    }
                return {"success": True, "data": payload.get("result")}
            # Try local first
            try:
                result = agent_manager.stop_agent(agent_id)
                return {"success": True, "data": result}
            except (KeyError, Exception):
                pass
            # Not found locally and not in route registry — try all online child nodes
            for node_info in node_runtime.node_registry.list_all():
                nid = str((node_info or {}).get("node_id") or "")
                nst = str((node_info or {}).get("status") or "")
                if nid == node_runtime.local_node_id or nst != "online":
                    continue
                try:
                    response = await node_connection_manager.send_request_to_node(
                        nid, AGENT_STOP_REQUEST, {"agent_id": agent_id}, timeout=10.0,
                    )
                    payload = response.get("payload") or {}
                    if payload.get("success"):
                        return {"success": True, "data": payload.get("result")}
                except Exception:
                    pass
            return {
                "success": False,
                "error": {"code": "AGENT_NOT_FOUND", "message": f"Agent not found: {agent_id}"},
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：更新 Agent（重命名）
    @app.patch("/api/agents/{agent_id}", dependencies=[Depends(verify_token)])
    async def patch_agent(agent_id: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """更新 Agent 信息（目前只支持重命名）。"""
        try:
            name = request.get("name")
            target_node_id = str(request.get("node_id") or "").strip()

            if name is not None and not isinstance(name, str):
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_ARGUMENT",
                        "message": "name must be a string or null",
                    },
                }

            resolved_target_node = target_node_id
            if not resolved_target_node:
                route = node_runtime.agent_route_registry.get(agent_id)
                if route is not None:
                    resolved_target_node = str(route.node_id or "").strip()

            if resolved_target_node and resolved_target_node not in (
                node_runtime.local_node_id,
                "master",
            ):
                response = await node_connection_manager.send_request_to_node(
                    resolved_target_node,
                    NODE_HTTP_PROXY_REQUEST,
                    {
                        "method": "PATCH",
                        "path": f"agents/{agent_id}",
                        "query": "",
                        "headers": {"content-type": "application/json"},
                        "body": json.dumps({"name": name}),
                    },
                )
                payload = response.get("payload") or {}
                if not payload.get("success"):
                    error = payload.get("error") or {}
                    return {
                        "success": False,
                        "error": {
                            "code": error.get("code", "AGENT_UPDATE_FAILED"),
                            "message": error.get("message", "Remote agent update failed"),
                        },
                    }
                body = payload.get("body") or "{}"
                return json.loads(body)

            result = agent_manager.rename_agent(agent_id, name)
            return {"success": True, "data": result}
        except KeyError as e:
            return {
                "success": False,
                "error": {"code": "AGENT_NOT_FOUND", "message": str(e)},
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：删除 Agent
    @app.delete("/api/agents/{agent_id}", dependencies=[Depends(verify_token)])
    async def delete_agent(agent_id: str, node_id: str = "") -> Dict[str, Any]:
        """删除 Agent。"""
        try:
            resolved_target_node = str(node_id or "").strip()
            route = node_runtime.agent_route_registry.get(agent_id)
            if not resolved_target_node and route is not None:
                resolved_target_node = str(route.node_id or "").strip()
            if resolved_target_node and resolved_target_node not in (
                node_runtime.local_node_id,
                "master",
            ):
                response = await node_connection_manager.send_request_to_node(
                    resolved_target_node,
                    AGENT_DELETE_REQUEST,
                    {"agent_id": agent_id},
                )
                payload = response.get("payload") or {}
                if not payload.get("success"):
                    error = payload.get("error") or {}
                    return {
                        "success": False,
                        "error": {
                            "code": error.get("code", "AGENT_DELETE_FAILED"),
                            "message": error.get(
                                "message", "Remote agent delete failed"
                            ),
                        },
                    }
                node_runtime.agent_route_registry.unregister(agent_id)
                return {"success": True, "data": payload.get("result")}
            # Try local first
            try:
                result = agent_manager.delete_agent(agent_id)
                node_runtime.agent_route_registry.unregister(agent_id)
                return {"success": True, "data": result}
            except (KeyError, Exception):
                pass
            # Not found locally and not in route registry — try all online child nodes
            for node_info in node_runtime.node_registry.list_all():
                nid = str((node_info or {}).get("node_id") or "")
                nst = str((node_info or {}).get("status") or "")
                if nid == node_runtime.local_node_id or nst != "online":
                    continue
                try:
                    response = await node_connection_manager.send_request_to_node(
                        nid, AGENT_DELETE_REQUEST, {"agent_id": agent_id}, timeout=10.0,
                    )
                    payload = response.get("payload") or {}
                    if payload.get("success"):
                        node_runtime.agent_route_registry.unregister(agent_id)
                        return {"success": True, "data": payload.get("result")}
                except Exception:
                    pass
            return {
                "success": False,
                "error": {"code": "AGENT_NOT_FOUND", "message": f"Agent not found: {agent_id}"},
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：获取可恢复的 session 列表
    @app.get("/api/agents/{agent_id}/sessions", dependencies=[Depends(verify_token)])
    async def list_agent_sessions(agent_id: str, node_id: str = "") -> Dict[str, Any]:
        """获取可恢复的 session 列表。"""
        try:
            resolved_target_node = str(node_id or "").strip()
            if not resolved_target_node:
                route = node_runtime.agent_route_registry.get(agent_id)
                if route is not None:
                    resolved_target_node = str(route.node_id or "").strip()

            if resolved_target_node and resolved_target_node not in (
                node_runtime.local_node_id,
                "master",
            ):
                response = await node_connection_manager.send_request_to_node(
                    resolved_target_node,
                    NODE_HTTP_PROXY_REQUEST,
                    {
                        "method": "GET",
                        "path": f"agents/{agent_id}/sessions",
                        "query": "",
                        "headers": {},
                        "body": "",
                    },
                )
                payload = response.get("payload") or {}
                if not payload.get("success"):
                    error = payload.get("error") or {}
                    return {
                        "success": False,
                        "error": {
                            "code": error.get("code", "SESSION_LIST_FAILED"),
                            "message": error.get("message", "Remote session list failed"),
                        },
                    }
                body = payload.get("body") or "{}"
                return json.loads(body)

            agent_info = agent_manager.get_agent_info(agent_id)
            if agent_info is None:
                return {
                    "success": False,
                    "error": {"code": "AGENT_NOT_FOUND", "message": "Agent not found"},
                }

            # 代理到 Agent 进程的 /sessions 接口
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://127.0.0.1:{agent_info.port}/sessions"
                )
                return response.json()
        except KeyError as e:
            return {
                "success": False,
                "error": {"code": "AGENT_NOT_FOUND", "message": str(e)},
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：恢复指定的 session
    @app.post("/api/agents/{agent_id}/sessions", dependencies=[Depends(verify_token)])
    async def restore_agent_session(
        agent_id: str, request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """恢复指定的 session。"""
        try:
            resolved_target_node = str(request.get("node_id") or "").strip()
            if not resolved_target_node:
                route = node_runtime.agent_route_registry.get(agent_id)
                if route is not None:
                    resolved_target_node = str(route.node_id or "").strip()

            if resolved_target_node and resolved_target_node not in (
                node_runtime.local_node_id,
                "master",
            ):
                forward_body = dict(request)
                forward_body.pop("node_id", None)
                response = await node_connection_manager.send_request_to_node(
                    resolved_target_node,
                    NODE_HTTP_PROXY_REQUEST,
                    {
                        "method": "POST",
                        "path": f"agents/{agent_id}/sessions",
                        "query": "",
                        "headers": {"content-type": "application/json"},
                        "body": json.dumps(forward_body),
                    },
                )
                payload = response.get("payload") or {}
                if not payload.get("success"):
                    error = payload.get("error") or {}
                    return {
                        "success": False,
                        "error": {
                            "code": error.get("code", "SESSION_RESTORE_FAILED"),
                            "message": error.get("message", "Remote session restore failed"),
                        },
                    }
                body = payload.get("body") or "{}"
                return json.loads(body)

            agent_info = agent_manager.get_agent_info(agent_id)
            if agent_info is None:
                return {
                    "success": False,
                    "error": {"code": "AGENT_NOT_FOUND", "message": "Agent not found"},
                }

            # 代理到 Agent 进程的 /sessions 接口
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"http://127.0.0.1:{agent_info.port}/sessions", json=request
                )
                return response.json()
        except KeyError as e:
            return {
                "success": False,
                "error": {"code": "AGENT_NOT_FOUND", "message": str(e)},
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：获取补全列表
    @app.get("/api/completions/{agent_id}", dependencies=[Depends(verify_token)])
    async def get_completions(agent_id: str, node_id: str = "") -> Dict[str, Any]:
        """获取所有可用补全项（不包括文件）。"""
        try:
            resolved_target_node = str(node_id or "").strip()
            if not resolved_target_node:
                route = node_runtime.agent_route_registry.get(agent_id)
                if route is not None:
                    resolved_target_node = str(route.node_id or "").strip()

            if resolved_target_node and resolved_target_node not in (
                node_runtime.local_node_id,
                "master",
            ):
                response = await node_connection_manager.send_request_to_node(
                    resolved_target_node,
                    NODE_HTTP_PROXY_REQUEST,
                    {
                        "method": "GET",
                        "path": f"completions/{agent_id}",
                        "query": "",
                        "headers": {},
                        "body": "",
                    },
                )
                payload = response.get("payload") or {}
                if not payload.get("success"):
                    error = payload.get("error") or {}
                    return {
                        "success": False,
                        "error": {
                            "code": error.get("code", "COMPLETIONS_FAILED"),
                            "message": error.get("message", "Remote completions failed"),
                        },
                    }
                body = payload.get("body") or "{}"
                return json.loads(body)

            from jarvis.jarvis_utils.config import get_replace_map
            from jarvis.jarvis_utils.tag import ot
            from jarvis.jarvis_utils.input import BUILTIN_COMMANDS
            import os

            # 获取 Agent 的工作目录
            agent = agent_manager.get_agent(agent_id)
            if not agent:
                return {
                    "success": False,
                    "error": {"code": "AGENT_NOT_FOUND", "message": "Agent not found"},
                }
            working_dir = agent.working_dir
            os.chdir(working_dir)

            all_completions = []

            # 添加 replace_map
            try:
                replace_map = get_replace_map()
                for tag, info in replace_map.items():
                    desc = (
                        info.get("description", tag) + "(Append)"
                        if info.get("append")
                        else "(Replace)"
                    )
                    all_completions.append(
                        {
                            "type": "replace",
                            "value": ot(tag),
                            "display": tag,
                            "description": desc,
                        }
                    )
            except Exception as e:
                print(f"[COMPLETIONS] Failed to load replace_map: {e}")

            # 添加内置命令
            for cmd, desc in BUILTIN_COMMANDS:
                all_completions.append(
                    {
                        "type": "command",
                        "value": ot(cmd),
                        "display": cmd,
                        "description": desc,
                    }
                )

            # 添加规则
            try:
                from jarvis.jarvis_agent.rules_manager import RulesManager

                rules_manager = RulesManager(working_dir)
                available_rules = rules_manager.get_all_available_rule_names()

                # 内置规则
                if available_rules.get("builtin"):
                    for rule_name in available_rules["builtin"]:
                        all_completions.append(
                            {
                                "type": "rule",
                                "value": f"<rule:{rule_name}>",
                                "display": rule_name,
                                "description": "📚 内置规则",
                            }
                        )

                # 文件规则
                if available_rules.get("files"):
                    for rule_name in available_rules["files"]:
                        all_completions.append(
                            {
                                "type": "rule",
                                "value": f"<rule:{rule_name}>",
                                "display": rule_name,
                                "description": "📄 文件规则",
                            }
                        )

                # YAML 规则
                if available_rules.get("yaml"):
                    for rule_name in available_rules["yaml"]:
                        all_completions.append(
                            {
                                "type": "rule",
                                "value": f"<rule:{rule_name}>",
                                "display": rule_name,
                                "description": "📝 YAML 规则",
                            }
                        )
            except Exception as e:
                print(f"[COMPLETIONS] Failed to load rules: {e}")

            return {"success": True, "data": all_completions}
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    @app.get("/api/completions/{agent_id}/search", dependencies=[Depends(verify_token)])
    async def search_completions(agent_id: str, query: str = "", node_id: str = "") -> Dict[str, Any]:
        """搜索文件补全项。

        Args:
            agent_id: Agent ID
            query: 搜索关键词

        Returns:
            {
                "success": True,
                "data": [
                    {
                        "type": "file",
                        "value": "path/to/file",
                        "display": "path/to/file",
                        "description": "File"
                    },
                    ...
                ]
            }
        """
        try:
            resolved_target_node = str(node_id or "").strip()
            if not resolved_target_node:
                route = node_runtime.agent_route_registry.get(agent_id)
                if route is not None:
                    resolved_target_node = str(route.node_id or "").strip()

            if resolved_target_node and resolved_target_node not in (
                node_runtime.local_node_id,
                "master",
            ):
                forward_query = urlencode({"query": query})
                response = await node_connection_manager.send_request_to_node(
                    resolved_target_node,
                    NODE_HTTP_PROXY_REQUEST,
                    {
                        "method": "GET",
                        "path": f"completions/{agent_id}/search",
                        "query": forward_query,
                        "headers": {},
                        "body": "",
                    },
                )
                payload = response.get("payload") or {}
                if not payload.get("success"):
                    error = payload.get("error") or {}
                    return {
                        "success": False,
                        "error": {
                            "code": error.get("code", "COMPLETION_SEARCH_FAILED"),
                            "message": error.get("message", "Remote completion search failed"),
                        },
                    }
                body = payload.get("body") or "{}"
                return json.loads(body)

            import subprocess
            from fuzzywuzzy import process
            from jarvis.jarvis_utils.utils import decode_output
            import os

            # 获取 Agent 的工作目录
            agent = agent_manager.get_agent(agent_id)
            if not agent:
                return {
                    "success": False,
                    "error": {"code": "AGENT_NOT_FOUND", "message": "Agent not found"},
                }
            working_dir = agent.working_dir
            os.chdir(working_dir)

            # 获取 git 文件列表
            result = subprocess.run(
                ["git", "ls-files"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
            )
            files = []
            if result.returncode == 0:
                files = [
                    line
                    for line in decode_output(result.stdout).splitlines()
                    if line.strip()
                ]

            # 模糊搜索
            search_results = []
            if query and files:
                scored_items = process.extract(
                    query,
                    files,
                    limit=50,
                )
                scored_items = [
                    (item[0], item[1])
                    for item in scored_items
                    if item[1] > 10  # 最小分数阈值
                ]
                for path, score in scored_items:
                    search_results.append(
                        {
                            "type": "file",
                            "value": path,
                            "display": f"{path} ({score}%)" if score < 100 else path,
                            "description": "File",
                        }
                    )

            return {"success": True, "data": search_results}
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    @app.post("/api/global-search/{agent_id}", dependencies=[Depends(verify_token)])
    async def global_search(agent_id: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """在 Agent 工作目录内执行全局文件内容搜索。"""
        try:
            resolved_target_node = str(request.get("node_id") or "").strip()
            if not resolved_target_node:
                route = node_runtime.agent_route_registry.get(agent_id)
                if route is not None:
                    resolved_target_node = str(route.node_id or "").strip()

            if resolved_target_node and resolved_target_node not in (
                node_runtime.local_node_id,
                "master",
            ):
                forward_body = dict(request)
                forward_body.pop("node_id", None)
                response = await node_connection_manager.send_request_to_node(
                    resolved_target_node,
                    NODE_HTTP_PROXY_REQUEST,
                    {
                        "method": "POST",
                        "path": f"global-search/{agent_id}",
                        "query": "",
                        "headers": {"content-type": "application/json"},
                        "body": json.dumps(forward_body),
                    },
                )
                payload = response.get("payload") or {}
                if not payload.get("success"):
                    error = payload.get("error") or {}
                    return {
                        "success": False,
                        "error": {
                            "code": error.get("code", "GLOBAL_SEARCH_FAILED"),
                            "message": error.get("message", "Remote global search failed"),
                        },
                    }
                body = payload.get("body") or "{}"
                return json.loads(body)

            agent = agent_manager.get_agent(agent_id)
            if not agent:
                return {
                    "success": False,
                    "error": {"code": "AGENT_NOT_FOUND", "message": "Agent not found"},
                }

            raw_query = request.get("query", "")
            query = str(raw_query).strip() if raw_query is not None else ""
            if not query:
                return {
                    "success": False,
                    "error": {"code": "INVALID_QUERY", "message": "query is required"},
                }
            if len(query) > GLOBAL_SEARCH_MAX_QUERY_LENGTH:
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_QUERY",
                        "message": f"query length must be <= {GLOBAL_SEARCH_MAX_QUERY_LENGTH}",
                    },
                }

            case_sensitive = bool(request.get("case_sensitive", False))
            whole_word = bool(request.get("whole_word", False))
            raw_max_results = request.get(
                "max_results", GLOBAL_SEARCH_DEFAULT_MAX_RESULTS
            )
            try:
                max_results = int(raw_max_results)
            except (TypeError, ValueError):
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_QUERY",
                        "message": "max_results must be an integer",
                    },
                }
            if max_results < 1 or max_results > GLOBAL_SEARCH_MAX_RESULTS_LIMIT:
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_QUERY",
                        "message": f"max_results must be between 1 and {GLOBAL_SEARCH_MAX_RESULTS_LIMIT}",
                    },
                }

            raw_file_glob = request.get("file_glob", "")
            file_glob = str(raw_file_glob).strip() if raw_file_glob is not None else ""
            if len(file_glob) > GLOBAL_SEARCH_MAX_GLOB_LENGTH:
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_QUERY",
                        "message": f"file_glob length must be <= {GLOBAL_SEARCH_MAX_GLOB_LENGTH}",
                    },
                }
            file_glob_patterns = [
                item.strip()
                for item in file_glob.split(",")
                if isinstance(item, str) and item.strip()
            ]

            working_dir = pathlib.Path(agent.working_dir).resolve()
            if not working_dir.exists() or not working_dir.is_dir():
                return {
                    "success": False,
                    "error": {
                        "code": "WORKING_DIR_NOT_FOUND",
                        "message": f"Working directory not found: {working_dir}",
                    },
                }

            rg_command = [
                "rg",
                "--line-number",
                "--column",
                "--no-heading",
                "--color",
                "never",
                "--hidden",
                "--glob",
                "!.git",
                "--glob",
                "!node_modules",
                "--glob",
                "!__pycache__",
                "--glob",
                "!.venv",
                "--glob",
                "!venv",
                "--glob",
                "!dist",
                "--glob",
                "!build",
                "--max-count",
                str(max_results),
            ]
            if not case_sensitive:
                rg_command.append("--ignore-case")
            if whole_word:
                rg_command.append("--word-regexp")
            for glob_pattern in file_glob_patterns:
                rg_command.extend(["--glob", glob_pattern])
            rg_command.extend([query, str(working_dir)])

            try:
                result = subprocess.run(
                    rg_command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=GLOBAL_SEARCH_COMMAND_TIMEOUT_SECONDS,
                    cwd=str(working_dir),
                )
            except FileNotFoundError:
                return {
                    "success": False,
                    "error": {
                        "code": "SEARCH_FAILED",
                        "message": "ripgrep (rg) is not available",
                    },
                }
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "error": {
                        "code": "SEARCH_TIMEOUT",
                        "message": f"Search timed out after {GLOBAL_SEARCH_COMMAND_TIMEOUT_SECONDS} seconds",
                    },
                }

            if result.returncode not in (0, 1):
                return {
                    "success": False,
                    "error": {
                        "code": "SEARCH_FAILED",
                        "message": result.stderr.strip() or "Search command failed",
                    },
                }

            results_by_file: Dict[str, list[Dict[str, Any]]] = {}
            total_matches = 0
            for line in result.stdout.splitlines():
                if total_matches >= max_results:
                    break
                parts = line.split(":", 3)
                if len(parts) != 4:
                    continue
                file_path_str, line_number_str, column_str, line_content = parts
                try:
                    absolute_path = pathlib.Path(file_path_str).resolve()
                    relative_path = absolute_path.relative_to(working_dir)
                    line_number = int(line_number_str)
                    column = int(column_str)
                except (ValueError, OSError):
                    continue

                if len(line_content) > GLOBAL_SEARCH_MAX_LINE_LENGTH:
                    line_content = line_content[:GLOBAL_SEARCH_MAX_LINE_LENGTH] + "..."

                expected_match_start = max(column - 1, 0)
                search_line_content = (
                    line_content if case_sensitive else line_content.lower()
                )
                search_query = query if case_sensitive else query.lower()
                match_start = expected_match_start
                nearest_match_start = search_line_content.find(search_query)
                if nearest_match_start != -1:
                    search_from = 0
                    while True:
                        candidate_match_start = search_line_content.find(
                            search_query, search_from
                        )
                        if candidate_match_start == -1:
                            break
                        if abs(candidate_match_start - expected_match_start) < abs(
                            nearest_match_start - expected_match_start
                        ):
                            nearest_match_start = candidate_match_start
                        search_from = candidate_match_start + 1
                    match_start = nearest_match_start
                match_end = min(match_start + len(query), len(line_content))
                file_key = str(relative_path)
                results_by_file.setdefault(file_key, []).append(
                    {
                        "line_number": line_number,
                        "line_content": line_content,
                        "match_start": match_start,
                        "match_end": match_end,
                    }
                )
                total_matches += 1

            structured_results = [
                {
                    "file_path": file_path,
                    "matches": matches,
                }
                for file_path, matches in results_by_file.items()
            ]

            return {
                "success": True,
                "data": {
                    "query": query,
                    "file_glob": file_glob,
                    "total_files": len(structured_results),
                    "total_matches": total_matches,
                    "results": structured_results,
                },
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    def _validate_absolute_file_path(file_path: str) -> pathlib.Path:
        if not file_path:
            raise ValueError("Path is required")

        target_path = pathlib.Path(file_path)
        if not target_path.is_absolute():
            raise ValueError("Path must be absolute")

        target_path = target_path.resolve()
        if not target_path.exists():
            raise FileNotFoundError(f"Path does not exist: {file_path}")

        if not target_path.is_file():
            raise IsADirectoryError(f"Path is not a file: {file_path}")

        return target_path

    def _parse_timer_schedule(request: Dict[str, Any]) -> Dict[str, Any]:
        schedule = request.get("schedule")
        if not isinstance(schedule, dict):
            raise ValueError("schedule must be an object")

        run_at = schedule.get("run_at")
        delay_seconds = schedule.get("delay_seconds")
        interval_seconds = schedule.get("interval_seconds")
        provided_fields = [
            value is not None for value in [run_at, delay_seconds, interval_seconds]
        ]
        if sum(provided_fields) != 1:
            raise ValueError(
                "Exactly one of schedule.run_at, schedule.delay_seconds, schedule.interval_seconds is required"
            )

        if run_at is not None:
            if not isinstance(run_at, str) or not run_at.strip():
                raise ValueError(
                    "schedule.run_at must be a non-empty ISO datetime string"
                )
            parsed_run_at = datetime.fromisoformat(run_at)
            return {"schedule_type": "run_at", "run_at": parsed_run_at}

        if delay_seconds is not None:
            if not isinstance(delay_seconds, (int, float)):
                raise ValueError("schedule.delay_seconds must be a number")
            if delay_seconds < 0:
                raise ValueError("schedule.delay_seconds must be >= 0")
            return {"schedule_type": "delay", "delay_seconds": float(delay_seconds)}

        if not isinstance(interval_seconds, (int, float)):
            raise ValueError("schedule.interval_seconds must be a number")
        if interval_seconds <= 0:
            raise ValueError("schedule.interval_seconds must be > 0")
        return {
            "schedule_type": "interval",
            "interval_seconds": float(interval_seconds),
        }

    def _build_create_agent_callback(action_params: Dict[str, Any]):
        agent_type = action_params.get("agent_type")
        working_dir = action_params.get("working_dir")
        name = action_params.get("name")
        llm_group = action_params.get("llm_group", "default")
        tool_group = action_params.get("tool_group", "default")
        config_file = action_params.get("config_file")
        task = action_params.get("task")
        additional_args = action_params.get("additional_args")
        worktree = bool(action_params.get("worktree", False))

        if not agent_type:
            raise ValueError("action.params.agent_type is required")
        if not working_dir:
            raise ValueError("action.params.working_dir is required")

        metadata = {
            "type": "create_agent",
            "params": {
                "agent_type": agent_type,
                "working_dir": working_dir,
                "name": name,
                "llm_group": llm_group,
                "tool_group": tool_group,
                "config_file": config_file,
                "task": task,
                "additional_args": additional_args,
                "worktree": worktree,
            },
        }

        def _create_agent_callback() -> None:
            auth_token = os.environ.get("JARVIS_AUTH_TOKEN")
            agent_manager.create_agent_threadsafe(
                auth_token=auth_token,
                agent_type=agent_type,
                working_dir=working_dir,
                name=name,
                llm_group=llm_group,
                tool_group=tool_group,
                config_file=config_file,
                task=task,
                additional_args=additional_args,
                worktree=worktree,
            )

        return _create_agent_callback, metadata

    def _build_shell_command_callback(action_params: Dict[str, Any]):
        command = action_params.get("command")
        working_dir = action_params.get("working_dir")
        interpreter = action_params.get("interpreter") or os.environ.get(
            "SHELL", "bash"
        )

        if not isinstance(command, str) or not command.strip():
            raise ValueError("action.params.command must be a non-empty string")
        if not isinstance(working_dir, str) or not working_dir.strip():
            raise ValueError("action.params.working_dir must be a non-empty string")

        working_path = pathlib.Path(working_dir).expanduser().resolve()
        if not working_path.exists():
            raise ValueError(f"Working directory not found: {working_dir}")
        if not working_path.is_dir():
            raise ValueError(f"Working directory is not a directory: {working_dir}")
        if not isinstance(interpreter, str) or not interpreter.strip():
            raise ValueError("action.params.interpreter must be a non-empty string")

        metadata = {
            "type": "run_shell_command",
            "params": {
                "command": command,
                "working_dir": str(working_path),
                "interpreter": interpreter,
            },
        }

        def _run_shell_command_callback() -> None:
            subprocess.run(
                [interpreter, "-lc", command],
                cwd=str(working_path),
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )

        return _run_shell_command_callback, metadata

    def _build_timer_action(request: Dict[str, Any]):
        action = request.get("action")
        if not isinstance(action, dict):
            raise ValueError("action must be an object")

        action_type = action.get("type")
        action_params = action.get("params")
        if not isinstance(action_type, str) or not action_type.strip():
            raise ValueError("action.type is required")
        if not isinstance(action_params, dict):
            raise ValueError("action.params must be an object")

        if action_type == "create_agent":
            return _build_create_agent_callback(action_params)
        if action_type == "run_shell_command":
            return _build_shell_command_callback(action_params)
        raise ValueError("action.type must be one of create_agent or run_shell_command")

    timer_manager.load_persisted_tasks()

    def _schedule_timer_task(request: Dict[str, Any]) -> Dict[str, Any]:
        schedule_info = _parse_timer_schedule(request)
        callback, action_metadata = _build_timer_action(request)
        timer_metadata = {
            "action": action_metadata,
            "schedule": {
                "type": schedule_info["schedule_type"],
            },
        }

        if schedule_info["schedule_type"] == "run_at":
            run_at = schedule_info["run_at"]
            timer_metadata["schedule"]["run_at"] = run_at.isoformat()
            timer_id = timer_manager.schedule_at(
                run_at=run_at,
                callback=callback,
                metadata=timer_metadata,
            )
        elif schedule_info["schedule_type"] == "delay":
            delay_seconds = schedule_info["delay_seconds"]
            timer_metadata["schedule"]["delay_seconds"] = delay_seconds
            timer_id = timer_manager.schedule_after(
                delay_seconds=delay_seconds,
                callback=callback,
                metadata=timer_metadata,
            )
        else:
            interval_seconds = schedule_info["interval_seconds"]
            timer_metadata["schedule"]["interval_seconds"] = interval_seconds
            timer_id = timer_manager.schedule_every(
                interval_seconds=interval_seconds,
                callback=callback,
                metadata=timer_metadata,
            )

        timer_info = timer_manager.get_task(timer_id)
        if timer_info is None:
            raise RuntimeError("Failed to load timer after scheduling")
        return timer_info

    @app.post("/api/timers", dependencies=[Depends(verify_token)])
    async def create_timer(request: Dict[str, Any]) -> Dict[str, Any]:
        """创建定时器。"""
        try:
            timer_info = _schedule_timer_task(request)
            return {"success": True, "data": timer_info}
        except ValueError as e:
            return {
                "success": False,
                "error": {"code": "INVALID_ARGUMENT", "message": str(e)},
            }
        except RuntimeError as e:
            return {
                "success": False,
                "error": {"code": "CREATE_FAILED", "message": str(e)},
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    @app.get("/api/timers", dependencies=[Depends(verify_token)])
    async def list_timers() -> Dict[str, Any]:
        """查询所有定时器。"""
        try:
            return {"success": True, "data": timer_manager.list_tasks()}
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    @app.get("/api/timers/{timer_id}", dependencies=[Depends(verify_token)])
    async def get_timer(timer_id: str) -> Dict[str, Any]:
        """查询单个定时器。"""
        try:
            timer_info = timer_manager.get_task(timer_id)
            if timer_info is None:
                return {
                    "success": False,
                    "error": {"code": "NOT_FOUND", "message": "Timer not found"},
                }
            return {"success": True, "data": timer_info}
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    @app.delete("/api/timers/{timer_id}", dependencies=[Depends(verify_token)])
    async def delete_timer(timer_id: str) -> Dict[str, Any]:
        """删除指定定时器。"""
        try:
            success = timer_manager.cancel(timer_id)
            if not success:
                return {
                    "success": False,
                    "error": {"code": "NOT_FOUND", "message": "Timer not found"},
                }
            return {"success": True}
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    async def _handle_file_content_request(payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            file_path = str(payload.get("path", "")).strip()
            try:
                target_path = _validate_absolute_file_path(file_path)
            except ValueError as exc:
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_PATH",
                        "message": str(exc),
                    },
                }
            except FileNotFoundError as exc:
                return {
                    "success": False,
                    "error": {
                        "code": "NOT_FOUND",
                        "message": str(exc),
                    },
                }
            except IsADirectoryError as exc:
                return {
                    "success": False,
                    "error": {
                        "code": "NOT_A_FILE",
                        "message": str(exc),
                    },
                }

            if target_path.stat().st_size > MAX_FILE_SIZE_BYTES:
                return {
                    "success": False,
                    "error": {
                        "code": "FILE_TOO_LARGE",
                        "message": "File size exceeds 1MB limit",
                    },
                }

            with open(target_path, "rb") as binary_file:
                file_header = binary_file.read(BINARY_FILE_SAMPLE_SIZE)

            if b"\x00" in file_header:
                return {
                    "success": False,
                    "error": {
                        "code": "BINARY_FILE_NOT_SUPPORTED",
                        "message": "Binary file is not supported",
                    },
                }

            try:
                with open(target_path, "r", encoding="utf-8") as file:
                    file_content = file.read()
            except UnicodeDecodeError:
                return {
                    "success": False,
                    "error": {
                        "code": "BINARY_FILE_NOT_SUPPORTED",
                        "message": "Binary file is not supported",
                    },
                }

            return {
                "success": True,
                "data": {
                    "path": str(target_path),
                    "content": file_content,
                },
            }
        except PermissionError:
            return {
                "success": False,
                "error": {
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied",
                },
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    async def _handle_file_stat_request(payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            file_path = str(payload.get("path", "")).strip()
            try:
                target_path = _validate_absolute_file_path(file_path)
            except ValueError as exc:
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_PATH",
                        "message": str(exc),
                    },
                }
            except FileNotFoundError as exc:
                return {
                    "success": False,
                    "error": {
                        "code": "NOT_FOUND",
                        "message": str(exc),
                    },
                }
            except IsADirectoryError as exc:
                return {
                    "success": False,
                    "error": {
                        "code": "NOT_A_FILE",
                        "message": str(exc),
                    },
                }

            file_stat = target_path.stat()
            return {
                "success": True,
                "data": {
                    "path": str(target_path),
                    "mtime_ns": file_stat.st_mtime_ns,
                    "size": file_stat.st_size,
                },
            }
        except PermissionError:
            return {
                "success": False,
                "error": {
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied",
                },
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    async def _handle_file_write_request(payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            file_path = str(payload.get("path", "")).strip()
            if not file_path:
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_PATH",
                        "message": "Path is required",
                    },
                }

            target_path = pathlib.Path(file_path)
            if not target_path.is_absolute():
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_PATH",
                        "message": "Path must be absolute",
                    },
                }

            file_content = payload.get("content")
            if not isinstance(file_content, str):
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_CONTENT",
                        "message": "Content must be a string",
                    },
                }

            encoded_content = file_content.encode("utf-8")
            if len(encoded_content) > MAX_FILE_SIZE_BYTES:
                return {
                    "success": False,
                    "error": {
                        "code": "FILE_TOO_LARGE",
                        "message": "File size exceeds 1MB limit",
                    },
                }

            target_path = target_path.resolve(strict=False)
            parent_directory = target_path.parent

            if not parent_directory.exists():
                return {
                    "success": False,
                    "error": {
                        "code": "PARENT_DIRECTORY_NOT_FOUND",
                        "message": f"Parent directory does not exist: {parent_directory}",
                    },
                }

            if not parent_directory.is_dir():
                return {
                    "success": False,
                    "error": {
                        "code": "PARENT_NOT_A_DIRECTORY",
                        "message": f"Parent path is not a directory: {parent_directory}",
                    },
                }

            with open(target_path, "w", encoding="utf-8") as file:
                file.write(file_content)

            return {
                "success": True,
                "data": {
                    "path": str(target_path),
                    "bytes_written": len(encoded_content),
                },
            }
        except PermissionError:
            return {
                "success": False,
                "error": {
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied",
                },
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    async def _handle_directories_request(payload: Dict[str, Any]) -> Dict[str, Any]:
        import pathlib

        try:
            path = str(payload.get("path", ""))
            if not path or path == "~":
                target_path = pathlib.Path.home()
            else:
                target_path = pathlib.Path(path).expanduser()

            target_path = target_path.resolve()

            if not target_path.exists():
                return {
                    "success": False,
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"Path does not exist: {path}",
                    },
                }

            if not target_path.is_dir():
                return {
                    "success": False,
                    "error": {
                        "code": "NOT_A_DIRECTORY",
                        "message": f"Path is not a directory: {path}",
                    },
                }

            parent_path = None
            if target_path.parent != target_path:
                parent_path = str(target_path.parent)

            items = []
            try:
                for entry in target_path.iterdir():
                    if not entry.name.startswith("."):
                        entry_type = "directory" if entry.is_dir() else "file"
                        items.append(
                            {
                                "name": entry.name,
                                "path": str(entry),
                                "type": entry_type,
                            }
                        )
                items.sort(key=lambda x: (x["type"] != "directory", x["name"]))
            except PermissionError:
                pass

            return {
                "success": True,
                "data": {
                    "current_path": str(target_path),
                    "parent_path": parent_path,
                    "items": items,
                },
            }
        except PermissionError:
            return {
                "success": False,
                "error": {"code": "PERMISSION_DENIED", "message": "Permission denied"},
            }
        except Exception as e:
            logger.exception("[DIRECTORIES] list_directories failed: %r", e)
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": repr(e)},
            }

    async def _dispatch_node_http_request(
        method: str,
        path: str,
        query: str,
        headers: Dict[str, Any],
        body: str,
    ) -> Dict[str, Any]:
        normalized_method = str(method or "GET").upper()
        normalized_path = "/" + str(path or "").lstrip("/")
        if normalized_path.startswith("/api/"):
            normalized_path = "/" + normalized_path[len("/api/") :].lstrip("/")

        payload: Dict[str, Any] = {}
        if normalized_method == "GET":
            params = dict(parse_qsl(query, keep_blank_values=True))
            payload.update(params)
        elif body:
            try:
                parsed_body = json.loads(body)
                if isinstance(parsed_body, dict):
                    payload = parsed_body
                else:
                    return {
                        "success": False,
                        "status_code": 400,
                        "headers": {"content-type": "application/json"},
                        "body": json.dumps(
                            {"error": "request body must be a JSON object"}
                        ),
                    }
            except json.JSONDecodeError:
                return {
                    "success": False,
                    "status_code": 400,
                    "headers": {"content-type": "application/json"},
                    "body": json.dumps({"error": "invalid JSON body"}),
                }

        if normalized_method == "GET" and normalized_path == "/directories":
            result = await _handle_directories_request(payload)
        elif normalized_method == "POST" and normalized_path == "/file-content":
            result = await _handle_file_content_request(payload)
        elif normalized_method == "POST" and normalized_path == "/file-stat":
            result = await _handle_file_stat_request(payload)
        elif normalized_method == "POST" and normalized_path == "/file-write":
            result = await _handle_file_write_request(payload)
        else:
            return {
                "success": False,
                "status_code": 404,
                "headers": {"content-type": "application/json"},
                "body": json.dumps(
                    {"error": f"unsupported node api path: {normalized_path}"}
                ),
            }

        return {
            "success": result.get("success", False),
            "status_code": 200 if result.get("success") else 400,
            "headers": {"content-type": "application/json"},
            "body": json.dumps(result),
        }

    @app.post("/api/file-content", dependencies=[Depends(verify_token)])
    async def get_file_content(request: Dict[str, Any]) -> Dict[str, Any]:
        """读取指定绝对路径文件的内容。"""
        return await _handle_file_content_request(request)

    @app.post("/api/file-stat", dependencies=[Depends(verify_token)])
    async def get_file_stat(request: Dict[str, Any]) -> Dict[str, Any]:
        """读取指定绝对路径文件的元信息。"""
        return await _handle_file_stat_request(request)

    @app.post("/api/file-write", dependencies=[Depends(verify_token)])
    async def write_file_content(request: Dict[str, Any]) -> Dict[str, Any]:
        """写入指定绝对路径文本文件的内容。"""
        return await _handle_file_write_request(request)

    @app.get("/api/directories", dependencies=[Depends(verify_token)])
    async def list_directories(path: str = "", node_id: str = "") -> Dict[str, Any]:
        """获取指定路径下的目录列表。"""
        try:
            resolved_node_id = str(node_id or "").strip()
            target_node_id = resolved_node_id or node_runtime.local_node_id

            if target_node_id not in (node_runtime.local_node_id, "master"):
                logger.info(
                    "[DIRECTORIES] remote list request path=%s target_node_id=%s local_node_id=%s",
                    path,
                    target_node_id,
                    node_runtime.local_node_id,
                )
                node_info = node_runtime.node_registry.get(target_node_id)
                if node_info is None:
                    logger.warning(
                        "[DIRECTORIES] target node not found: %s", target_node_id
                    )
                    return {
                        "success": False,
                        "error": {
                            "code": "NODE_NOT_FOUND",
                            "message": f"Node not found: {target_node_id}",
                        },
                    }
                logger.info(
                    "[DIRECTORIES] target node status=%s connection_id=%s",
                    node_info.status,
                    node_info.connection_id,
                )
                if node_info.status != "online":
                    return {
                        "success": False,
                        "error": {
                            "code": "NODE_OFFLINE",
                            "message": f"Node is offline: {target_node_id}",
                        },
                    }
                response = await node_connection_manager.send_request_to_node(
                    target_node_id,
                    DIRECTORY_LIST_REQUEST,
                    {
                        "path": path,
                    },
                )
                logger.info(
                    "[DIRECTORIES] remote node response type=%s", response.get("type")
                )
                payload = response.get("payload") or {}
                if payload.get("success"):
                    logger.info(
                        "[DIRECTORIES] remote list success current_path=%s item_count=%s",
                        (payload.get("data") or {}).get("current_path"),
                        len((payload.get("data") or {}).get("items") or []),
                    )
                    return {"success": True, "data": payload.get("data") or {}}
                error = payload.get("error") or {}
                logger.warning(
                    "[DIRECTORIES] remote list failed code=%s message=%s",
                    error.get("code"),
                    error.get("message"),
                )
                return {
                    "success": False,
                    "error": {
                        "code": error.get("code", "DIRECTORY_LIST_FAILED"),
                        "message": error.get(
                            "message", "Remote directory listing failed"
                        ),
                    },
                }

            return await _handle_directories_request({"path": path})
        except Exception as e:
            logger.exception("[DIRECTORIES] list_directories failed: %r", e)
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": repr(e)},
            }

    # HTTP API：创建终端会话
    @app.post("/api/terminals", dependencies=[Depends(verify_token)])
    async def create_terminal(request: Dict[str, Any]) -> Dict[str, Any]:
        """创建新的终端会话。

        Args:
            request: {
                "interpreter": "bash",  # 可选，默认bash
                "working_dir": "."     # 可选，默认当前目录
            }

        Returns:
            {"success": True, "data": {"terminal_id": "xxx"}}
        """
        try:
            interpreter = request.get("interpreter") or os.environ.get("SHELL", "bash")
            raw_working_dir = request.get("working_dir")
            working_dir = str(raw_working_dir).strip() if raw_working_dir else ""
            if not working_dir:
                working_dir = str(pathlib.Path.home())

            terminal_id, error = terminal_session_manager.create_session(
                interpreter=interpreter,
                working_dir=working_dir,
                stream_publisher=router,
                session_id="default",
            )

            if terminal_id is None:
                return {
                    "success": False,
                    "error": {
                        "code": "CREATE_FAILED",
                        "message": error or "创建终端失败",
                    },
                }

            return {"success": True, "data": {"terminal_id": terminal_id}}
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：列出所有终端会话
    @app.get("/api/terminals", dependencies=[Depends(verify_token)])
    async def list_terminals() -> Dict[str, Any]:
        """列出所有活跃的终端会话。

        Returns:
            {"success": True, "data": [{"terminal_id": "xxx", ...}]}
        """
        try:
            sessions = terminal_session_manager.list_sessions()
            return {"success": True, "data": sessions}
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：关闭终端会话
    @app.delete("/api/terminals/{terminal_id}", dependencies=[Depends(verify_token)])
    async def close_terminal(terminal_id: str) -> Dict[str, Any]:
        """关闭指定的终端会话。

        Args:
            terminal_id: 终端ID

        Returns:
            {"success": True}
        """
        try:
            success = terminal_session_manager.close_session(terminal_id)
            if not success:
                return {
                    "success": False,
                    "error": {"code": "NOT_FOUND", "message": "终端不存在"},
                }
            return {"success": True}
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # Inject local HTTP dispatcher into node_connection_manager
    node_connection_manager._node_http_dispatcher = _dispatch_node_http_request

    return app


def run(
    host: str = "127.0.0.1",
    port: int = 8000,
    password: Optional[str] = None,
    node_config: Optional[NodeRuntimeConfig] = None,
) -> None:
    """本地启动入口。"""

    import uvicorn

    from jarvis.jarvis_utils.utils import init_env

    # 初始化环境并加载配置文件
    init_env(welcome_str="", config_file=None)

    # 如果提供了密码参数，更新 gateway_auth 配置
    if password:
        if "gateway_auth" not in GLOBAL_CONFIG_DATA:
            GLOBAL_CONFIG_DATA["gateway_auth"] = {}
        GLOBAL_CONFIG_DATA["gateway_auth"]["password"] = password
        GLOBAL_CONFIG_DATA["gateway_auth"]["enable"] = True
        GLOBAL_CONFIG_DATA["gateway_auth"]["allow_unset"] = False

    uvicorn.run(create_app(node_config=node_config), host=host, port=port)


def _normalize_auth_payload(payload: Any) -> Optional[Dict[str, Any]]:
    """规范化 WebSocket 认证消息的负载。

    Args:
        payload: 认证消息的 payload

    Returns:
        规范化后的认证负载，包含 token
    """
    if not isinstance(payload, dict):
        return None
    return {
        "token": payload.get("token"),
    }


def _extract_auth_from_headers(websocket: WebSocket) -> Optional[Dict[str, Any]]:
    """从 WebSocket 握手 Header 提取认证信息。"""
    protocol_header = websocket.headers.get("sec-websocket-protocol", "")
    for item in protocol_header.split(","):
        protocol = item.strip()
        if protocol.startswith("jarvis-token."):
            encoded_token = protocol[len("jarvis-token.") :]
            token = unquote(encoded_token)
            if token:
                return {"token": token}
    return None


def _build_sender(websocket: WebSocket, loop: asyncio.AbstractEventLoop):
    def _sender(message: Dict[str, Any]) -> None:
        async def _send():
            try:
                print(
                    f"[WebSocket Sender] Sending message: type={message.get('type')}, exec_id={message.get('payload', {}).get('execution_id')}"
                )
                await websocket.send_json(message)
                print("[WebSocket Sender] Message sent successfully")
            except Exception as e:
                print(f"[WebSocket Sender] Error sending message: {e}")

        try:
            asyncio.run_coroutine_threadsafe(_send(), loop)
        except Exception as e:
            print(f"[WebSocket Sender] Error scheduling send: {e}")

    return _sender


async def _send_error(websocket: WebSocket, code: str, message: str) -> None:
    error_msg = {"type": "error", "payload": {"code": code, "message": message}}
    await websocket.send_json(error_msg)
