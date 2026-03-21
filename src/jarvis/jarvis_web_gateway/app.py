# -*- coding: utf-8 -*-
"""Web Gateway FastAPI 应用。

独立服务：通过 WebSocket 对接 Gateway 输入/输出/执行事件。
"""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib
import uuid
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
from jarvis.jarvis_web_gateway.terminal_input_registry import TerminalInputRegistry
from jarvis.jarvis_web_gateway.terminal_session_manager import TerminalSessionManager
from jarvis.jarvis_utils.globals import set_interrupt

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

        # 检查是否已有活跃连接
        if self._router.has_active_subscribers():
            if self._connection_lock_enabled:
                # 锁定模式：拒绝新连接
                await _send_error(
                    websocket,
                    "CONNECTION_REJECTED",
                    "Already have an active connection (connection lock enabled)",
                )
                await websocket.close()
                return
            else:
                # 非锁定模式：断开旧连接，允许新连接
                print(
                    f"[WS CONNECTION] New connection replacing old one (connection lock disabled)"
                )
                self._router.unregister_all_session(session_id=session_id)

        self._auth_store[session_id] = auth_payload
        self._router.register(
            connection_id,
            _build_sender(websocket, loop),
            session_id=session_id,
        )
        self._input_registry.register_provider(session_id)
        await websocket.send_json(
            {"type": "ready", "payload": {"session_id": session_id}}
        )
        # 发送缓存的消息
        cached_messages = self._router.get_and_clear_cache()
        if cached_messages:
            print(f"[CACHE] Sending {len(cached_messages)} cached messages to client")
            for msg in cached_messages:
                try:
                    await websocket.send_json(msg)
                except Exception as e:
                    print(f"[CACHE] Failed to send cached message: {e}")
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
            working_dir = payload.get("working_dir", ".")
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


def create_app(custom_app: Optional[FastAPI] = None) -> FastAPI:
    """创建 FastAPI 应用。

    Args:
        custom_app: 自定义 FastAPI app，用于添加额外的路由（如状态查询）

    Returns:
        FastAPI 应用实例
    """

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

    router = SessionOutputRouter()
    input_registry = InputSessionRegistry()
    terminal_input_registry = TerminalInputRegistry()
    terminal_session_manager = TerminalSessionManager(max_sessions=5)

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

    @app.on_event("startup")
    async def _startup() -> None:
        # 初始化环境并加载配置文件（已在 run() 函数中调用，此处避免重复）
        # from jarvis.jarvis_utils.utils import init_env
        # init_env(welcome_str="", config_file=None)
        # 为运行中的 Agent 启动监控任务
        await agent_manager.start_monitoring_for_running_agents()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        # 清理所有 Agent
        await agent_manager.cleanup()
        # 清理代理管理器
        await agent_proxy_manager.cleanup()
        # 清理所有终端会话
        terminal_session_manager.cleanup()
        set_current_gateway(None)

    # HTTP API：登录接口
    @app.post("/api/auth/login")
    async def login(request: Dict[str, Any]) -> Dict[str, Any]:
        """登录接口，验证密码并返回 Token。"""
        import logging

        logger = logging.getLogger(__name__)

        try:
            password = request.get("password")
            logger.info(
                f"[AUTH] Login attempt with password length: {len(password) if password else 0}"
            )

            if not password:
                logger.warning(f"[AUTH] Login failed: password is empty")
                return {
                    "success": False,
                    "error": {
                        "code": "MISSING_PASSWORD",
                        "message": "password is required",
                    },
                }

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

            # 如果设置了密码，进行验证
            if expected_password and password != expected_password:
                logger.warning(f"[AUTH] Login failed: password mismatch")
                return {
                    "success": False,
                    "error": {
                        "code": "AUTH_FAILED",
                        "message": "Invalid password",
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

    # WebSocket 代理：代理到 Agent WebSocket
    @app.websocket("/api/agent/{agent_id}/ws")
    async def agent_websocket_proxy(agent_id: str, websocket: WebSocket) -> None:
        """代理 WebSocket 连接到指定 Agent。

        Args:
            agent_id: Agent ID
            websocket: 客户端 WebSocket 连接
        """
        await websocket.accept()
        logger = logging.getLogger(__name__)
        logger.info(f"[WS PROXY] New WebSocket connection for agent {agent_id}")

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

    # HTTP 代理：代理到 Agent HTTP API
    @app.api_route(
        "/api/agent/{agent_id}/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
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
            result = agent_manager.stop_agent(agent_id)
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

    # HTTP API：更新 Agent（重命名）
    @app.patch("/api/agents/{agent_id}", dependencies=[Depends(verify_token)])
    async def patch_agent(agent_id: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """更新 Agent 信息（目前只支持重命名）。"""
        try:
            name = request.get("name")

            if name is not None and not isinstance(name, str):
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_ARGUMENT",
                        "message": "name must be a string or null",
                    },
                }

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
    async def delete_agent(agent_id: str) -> Dict[str, Any]:
        """删除 Agent。"""
        try:
            result = agent_manager.delete_agent(agent_id)
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

    # HTTP API：获取可恢复的 session 列表
    @app.get("/api/agents/{agent_id}/sessions", dependencies=[Depends(verify_token)])
    async def list_agent_sessions(agent_id: str) -> Dict[str, Any]:
        """获取可恢复的 session 列表。"""
        try:
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
    async def get_completions(agent_id: str) -> Dict[str, Any]:
        """获取所有可用补全项（不包括文件）。"""
        try:
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
    async def search_completions(agent_id: str, query: str = "") -> Dict[str, Any]:
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
                    limit=30,
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

    @app.post("/api/file-content", dependencies=[Depends(verify_token)])
    async def get_file_content(request: Dict[str, Any]) -> Dict[str, Any]:
        """读取指定绝对路径文件的内容。"""
        try:
            file_path = str(request.get("path", "")).strip()
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

    @app.post("/api/file-stat", dependencies=[Depends(verify_token)])
    async def get_file_stat(request: Dict[str, Any]) -> Dict[str, Any]:
        """读取指定绝对路径文件的元信息。"""
        try:
            file_path = str(request.get("path", "")).strip()
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

    @app.post("/api/file-write", dependencies=[Depends(verify_token)])
    async def write_file_content(request: Dict[str, Any]) -> Dict[str, Any]:
        """写入指定绝对路径文本文件的内容。"""
        try:
            file_path = str(request.get("path", "")).strip()
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

            file_content = request.get("content")
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

    @app.get("/api/directories", dependencies=[Depends(verify_token)])
    async def list_directories(path: str = "") -> Dict[str, Any]:
        """获取指定路径下的目录列表。

        Args:
            path: 目录路径，默认为用户主目录

        Returns:
            {
                "success": True,
                "data": {
                    "current_path": "/path/to/dir",
                    "parent_path": "/path/to",  # 如果存在
                    "directories": [
                        {"name": "dir1", "path": "/path/to/dir/dir1"},
                        ...
                    ]
                }
            }
        """
        import pathlib

        try:
            # 解析路径，如果为空则使用用户主目录
            if not path or path == "~":
                target_path = pathlib.Path.home()
            else:
                target_path = pathlib.Path(path).expanduser()

            # 规范化为绝对路径
            target_path = target_path.resolve()

            # 检查路径是否存在且是目录
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

            # 获取父目录路径（如果存在）
            parent_path = None
            if target_path.parent != target_path:  # 不是根目录
                parent_path = str(target_path.parent)

            # 获取子目录和文件列表
            items = []
            try:
                for entry in target_path.iterdir():
                    # 过滤隐藏文件（以 . 开头）
                    if not entry.name.startswith("."):
                        # 判断是目录还是文件
                        entry_type = "directory" if entry.is_dir() else "file"
                        items.append(
                            {
                                "name": entry.name,
                                "path": str(entry),
                                "type": entry_type,
                            }
                        )
                # 按名称排序，目录在前，文件在后
                items.sort(key=lambda x: (x["type"] != "directory", x["name"]))
            except PermissionError:
                # 忽略权限错误，返回空列表
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
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
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
            working_dir = request.get("working_dir", ".")

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

    return app


def run(
    host: str = "127.0.0.1", port: int = 8000, password: Optional[str] = None
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

    uvicorn.run(create_app(), host=host, port=port)


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
    """从 WebSocket HTTP Header 提取认证信息。

    Args:
        websocket: WebSocket 连接对象

    Returns:
        认证负载，包含 token（如果存在）
    """
    # 支持两种方式：
    # 1. x-jarvis-token Header（旧格式，保持兼容）
    token = websocket.headers.get("x-jarvis-token")
    if token:
        return {"token": token}

    # 2. Authorization: Bearer <token> Header（新格式）
    authorization = websocket.headers.get("Authorization")
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return {"token": parts[1]}

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


async def _await_auth_message(
    websocket: WebSocket, gateway: WebGateway
) -> Tuple[Optional[Dict[str, Any]], bool, Optional[str]]:
    """等待 WebSocket 的第一条认证消息。

    Args:
        websocket: WebSocket 连接对象
        gateway: WebGateway 实例

    Returns:
        (认证负载, 是否认证成功, 错误原因)
    """
    try:
        message = await asyncio.wait_for(websocket.receive_json(), timeout=10)
    except Exception:
        return (
            None,
            False,
            "Authentication required. First message must be an auth message with type 'auth' and payload containing 'token'.",
        )

    if not isinstance(message, dict) or message.get("type") != "auth":
        return (
            None,
            False,
            "Authentication required. First message must be an auth message with type 'auth' and payload containing 'token'.",
        )

    payload = _normalize_auth_payload(message.get("payload") or {})
    authorized, reason = gateway._check_auth(payload)

    if not authorized:
        return payload, False, reason or "Invalid token"

    return payload, True, "Authorized"


async def _send_error(websocket: WebSocket, code: str, message: str) -> None:
    error_msg = {"type": "error", "payload": {"code": code, "message": message}}
    await websocket.send_json(error_msg)
