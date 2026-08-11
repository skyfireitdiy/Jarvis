# -*- coding: utf-8 -*-
"""Web Gateway FastAPI 应用。

独立服务：通过 WebSocket 对接 Gateway 输入/输出/执行事件。
"""

from __future__ import annotations

import asyncio
from collections import deque
from contextlib import asynccontextmanager
import json
import logging
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time
import uuid

import yaml  # type: ignore[import-untyped]
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple, cast
from urllib.parse import parse_qsl
from urllib.parse import unquote
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Request, Response, WebSocket
from fastapi import WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import httpx

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
from jarvis.jarvis_web_gateway.chat_manager import ChatManager
from jarvis.jarvis_web_gateway.agent_proxy_manager import (
    AgentProxyManager,
    AgentNotFoundError,
    AgentNotRunningError,
    ProxyConnectionError,
)
from jarvis.jarvis_web_gateway.token_manager import (
    generate_gateway_token,
    validate_gateway_token,
    extract_token_from_authorization_header,
)
from jarvis.jarvis_web_gateway.user_manager import UserManager
from jarvis.jarvis_web_gateway.permission_manager import PermissionManager
from jarvis.jarvis_web_gateway.jwt_utils import (
    generate_jwt_token,
    revoke_token,
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
    AGENT_WS_OPEN_REQUEST,
    AGENT_WS_SEND_REQUEST,
    AGENT_WS_RECV_REQUEST,
    AGENT_WS_CLOSE_REQUEST,
    DIRECTORY_LIST_REQUEST,
    NODE_TERMINAL_REQUEST,
    SERVICE_RESTART_REQUEST,
    CONFIG_GET_REQUEST,
    CONFIG_SET_REQUEST,
    CODE_UPDATE_TO_MAIN_REQUEST,
)
from jarvis.jarvis_web_gateway.node_runtime import AgentRouteInfo, NodeRuntime
from jarvis.jarvis_web_gateway.terminal_input_registry import TerminalInputRegistry
from jarvis.jarvis_web_gateway.terminal_session_manager import TerminalSessionManager
from jarvis.jarvis_web_gateway.timer_manager import TimerManager
from jarvis.jarvis_service.cli import get_single_instance_lock_path
from jarvis.jarvis_utils.globals import set_interrupt, get_script_pid
import jarvis.jarvis_utils.globals as jglobals
from jarvis.jarvis_utils.utils import _find_all_config_files, _merge_configs
from jarvis.jarvis_utils.config import (
    GLOBAL_CONFIG_DATA,
    save_exception,
)

logger = logging.getLogger(__name__)

# 群组存储（内存存储，服务重启后丢失）
# Key: group_id, Value: {"name": str, "members": set()}
groups: Dict[str, Dict[str, Any]] = {}

# 导入 agent 状态管理器（用于处理 get_status 消息）
try:
    from jarvis.jarvis_agent.jarvis import get_agent_status_manager
except ImportError:
    # 如果 jarvis_agent 不可用，使用 None
    get_agent_status_manager = None  # type: ignore


# 全局 AgentManager，用于状态变更回调
_global_agent_manager: Optional[AgentManager] = None

# Node Secret 服务器（用于提供 node_secret 给子节点）
# Linux: Unix Domain Socket, Windows: TCP Socket
_node_secret_socket_server: Optional[asyncio.Server] = None
_NODE_SECRET_SOCKET_PATH = os.path.expanduser("~/.jarvis/gateway/node_secret.sock")
_NODE_SECRET_TCP_PORT = 18765  # Windows 使用 TCP 端口
_RESTART_COMMAND_TCP_PORT = 18766  # Windows 重启命令 TCP 端口

# 状态更新回调函数
_status_update_callback: Optional[Callable[[str], None]] = None


async def _handle_node_secret_client(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    """处理 Unix Domain Socket 客户端请求，返回 node_secret。

    协议格式：
    - 客户端发送："GET_NODE_SECRET\n"
    - 服务器返回："{\"node_secret\": \"<secret>\"}\n" 或 "{\"error\": \"<message>\"}\n"
    """
    try:
        # 读取请求
        data = await reader.readline()
        request = data.decode("utf-8").strip()

        if request != "GET_NODE_SECRET":
            response = json.dumps({"error": "Invalid request. Use: GET_NODE_SECRET"})
        else:
            # 从环境变量获取 node_secret
            node_secret = os.environ.get("JARVIS_NODE_SECRET")
            if not node_secret:
                response = json.dumps({"error": "Node secret not configured"})
            else:
                response = json.dumps({"node_secret": node_secret})

        writer.write(response.encode("utf-8") + b"\n")
        await writer.drain()
    except Exception as e:
        logger.error(f"Error handling node secret client: {e}")
        try:
            error_response = json.dumps({"error": str(e)})
            writer.write(error_response.encode("utf-8") + b"\n")
            await writer.drain()
        except Exception as e:
            save_exception(e, module="jarvis_web_gateway.app", function="")
            pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception as e:
            save_exception(e, module="jarvis_web_gateway.app", function="")
            pass


async def _start_node_secret_socket_server(node_config: NodeRuntimeConfig) -> None:
    """启动 Node Secret 服务器（仅在 master 模式下）。

    Linux: Unix Domain Socket
    Windows: TCP Socket (localhost only)

    Args:
        node_config: Node 运行时配置
    """
    global _node_secret_socket_server

    # 仅在 master 模式下启动
    if not node_config.is_master:
        return

    if sys.platform == "win32":
        # Windows: 使用 TCP Socket
        try:
            _node_secret_socket_server = await asyncio.start_server(
                _handle_node_secret_client,
                host="127.0.0.1",
                port=_NODE_SECRET_TCP_PORT,
            )
            logger.info(
                f"Node secret TCP server started at 127.0.0.1:{_NODE_SECRET_TCP_PORT}"
            )
        except Exception as e:
            logger.error(f"Failed to start node secret TCP server: {e}")
            raise
    else:
        # Linux: 使用 Unix Domain Socket
        # 确保目录存在
        socket_dir = os.path.dirname(_NODE_SECRET_SOCKET_PATH)
        os.makedirs(socket_dir, exist_ok=True)

        # 删除旧的 socket 文件（如果存在）
        if os.path.exists(_NODE_SECRET_SOCKET_PATH):
            try:
                os.unlink(_NODE_SECRET_SOCKET_PATH)
                logger.info(f"Removed old socket file: {_NODE_SECRET_SOCKET_PATH}")
            except Exception as e:
                logger.warning(f"Failed to remove old socket file: {e}")

        # 启动 Unix Domain Socket 服务器
        try:
            _node_secret_socket_server = await asyncio.start_unix_server(
                _handle_node_secret_client, path=_NODE_SECRET_SOCKET_PATH
            )

            # 设置严格的文件权限（仅当前用户可读写）
            os.chmod(_NODE_SECRET_SOCKET_PATH, 0o600)

            logger.info(
                f"Node secret socket server started at {_NODE_SECRET_SOCKET_PATH} (mode: 0600)"
            )
        except Exception as e:
            logger.error(f"Failed to start node secret socket server: {e}")
            raise


async def _stop_node_secret_socket_server() -> None:
    """停止 Node Secret 服务器并清理资源。

    Linux: 清理 Unix Domain Socket 文件
    Windows: 无需清理文件
    """
    global _node_secret_socket_server

    if _node_secret_socket_server is not None:
        _node_secret_socket_server.close()
        await _node_secret_socket_server.wait_closed()
        _node_secret_socket_server = None
        logger.info("Node secret server stopped")

    # Linux: 清理 socket 文件
    if sys.platform != "win32":
        if os.path.exists(_NODE_SECRET_SOCKET_PATH):
            try:
                os.unlink(_NODE_SECRET_SOCKET_PATH)
                logger.info(f"Removed socket file: {_NODE_SECRET_SOCKET_PATH}")
            except Exception as e:
                logger.warning(f"Failed to remove socket file: {e}")


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
_node_connection_manager: Optional["NodeConnectionManager"] = None
_node_runtime: Optional["NodeRuntime"] = None

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
        except Exception as e:
            save_exception(
                e, module="jarvis_web_gateway.app", function="_update_status"
            )
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

        # 消息缓存：持续缓存所有消息（输出+输入，上限1亿条），用于重连后恢复完整对话
        self._message_cache: deque = deque(maxlen=100_000_000)

        # 消息序号：按 agent_id 维护独立序号序列
        self._agent_message_sequences: Dict[str, int] = {}  # agent_id -> next_seq
        self._global_message_sequence: int = 0  # 全局消息（无agent_id）的序号

        # 输入缓存：区分已发送/未发送
        self._pending_inputs: List[Dict[str, Any]] = []  # 未发送的输入请求
        self._sent_inputs: Dict[
            str, Dict[str, Any]
        ] = {}  # 已发送但未收到回复：{session_id: message}

    def emit_output(self, event: GatewayOutputEvent) -> None:
        # 单连接模式，固定使用 default session_id
        session_id = "default"
        auth_payload = self._auth_store.get(session_id)
        authorized, _ = self._check_auth(auth_payload)

        context = dict(event.context) if event.context else {}

        # Agent 进程自动补充 agent_id
        if os.environ.get("IS_AGENT_PROCESS") == "1":
            if not context.get("agent_id"):
                from jarvis.jarvis_utils import globals as jglobals

                if jglobals.agent_id:
                    context["agent_id"] = jglobals.agent_id

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

        # 为消息分配序号（按 agent_id 或 global）
        agent_id = context.get("agent_id")
        if agent_id:
            seq = self._agent_message_sequences.get(agent_id, 0)
            self._agent_message_sequences[agent_id] = seq + 1
        else:
            seq = self._global_message_sequence
            self._global_message_sequence += 1

        message = {"type": "output", "payload": payload, "seq": seq}

        # 持续缓存所有消息（无论是否已授权）
        self._message_cache.append(message)

        # 如果已授权，实时发送
        if authorized:
            self._router.publish(message, session_id=session_id)

    def request_input(self, request: GatewayInputRequest) -> GatewayInputResult:
        # 单连接模式，固定使用 default session_id
        session_id = "default"
        metadata = dict(request.metadata) if request.metadata else {}
        metadata["session_id"] = session_id

        # 等待WebSocket连接建立（通过检查_auth_store中是否有认证信息）
        import time

        wait_interval = 0.5  # 秒
        waited = 0

        while True:
            auth_payload = metadata.get("auth") or self._auth_store.get(session_id)
            authorized, reason = self._check_auth(auth_payload)
            if authorized:
                break

            time.sleep(wait_interval)
            waited += wait_interval

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
        # 追踪已发送的输入请求
        self._sent_inputs[session_id] = message

        # 更新状态为等待输入
        if request.mode == "single":
            _update_status("waiting_single")
        else:
            _update_status("waiting_multi")

        session = self._input_registry.get_or_create(session_id)

        # 设置输入注入回调，允许 /message 接口直接注入消息到输入流
        jglobals.input_inject_callback = session.submit_input

        try:
            # 单行输入不使用全局缓冲区，只有多行输入才使用
            text = session.wait_for_input(use_global_buffer=(request.mode != "single"))
        finally:
            # 清除回调，避免后续误用
            jglobals.input_inject_callback = None

        # 输入完成，恢复为运行状态
        _update_status("running")

        # 清除已完成的输入请求
        self._sent_inputs.pop(session_id, None)

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
        # 追踪已发送的确认请求（使用特殊key区分input和confirm）
        confirm_key = f"{session_id}_confirm"
        self._sent_inputs[confirm_key] = message

        # 更新状态为等待确认
        _update_status("waiting_confirm")

        session = self._input_registry.get_or_create_confirm_session(session_id)
        confirmed = session.wait_for_confirm()

        # 确认完成，恢复为运行状态
        _update_status("running")

        # 清除已完成的确认请求
        self._sent_inputs.pop(confirm_key, None)

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
    ) -> Optional[Callable[[float], Optional[str]]]:
        return self._terminal_input_registry.get_input_callback(execution_id)  # type: ignore[return-value]

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
        user_manager: Optional[Any] = None,
        permission_manager: Optional[Any] = None,
    ) -> None:
        self._router = router
        self._input_registry = input_registry
        self._terminal_input_registry = terminal_input_registry
        self._gateway = gateway
        self._auth_store = auth_store
        self._user_manager = user_manager
        self._permission_manager = permission_manager

        self._active_connections: Dict[str, Dict[str, tuple[str, WebSocket]]] = {}
        self._connection_state_lock = asyncio.Lock()

        # 聊天室管理
        self._chat_manager = ChatManager()

    async def handle(self, websocket: WebSocket) -> None:
        await websocket.accept(subprotocol="jarvis-ws")
        session_id = "default"  # 固定使用 default session，简化重连逻辑
        connection_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()

        # 先进行认证检查，只有认证通过才允许替换旧连接
        auth_payload = _extract_auth_from_headers(websocket)
        authorized, reason = self._gateway._check_auth(auth_payload)
        if not authorized:
            await _send_error(websocket, "AUTH_FAILED", reason or "auth failed")
            await websocket.close()
            return

        async with self._connection_state_lock:
            existing_connections = self._active_connections.get(session_id)
            if existing_connections:
                print(
                    f"[WS CONNECTION] New connection added (existing={len(existing_connections)})"
                )

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
            connections = self._active_connections.setdefault(session_id, {})
            connections[connection_id] = (connection_id, websocket)
        self._input_registry.register_provider(session_id)
        await websocket.send_json(
            {"type": "ready", "payload": {"session_id": session_id}}
        )
        # 消息历史通过前端发送 sync_request 按需增量同步，不在连接建立时主动推送
        # 恢复待处理的输入请求
        pending_request = self._input_registry.get_input_request(session_id)
        if pending_request:
            session = self._input_registry.get_or_create(session_id)
            session.reconnect()
            await websocket.send_json(pending_request)
        # 恢复待处理的确认请求
        pending_confirm = self._input_registry.get_confirm_request(session_id)
        if pending_confirm:
            confirm_session = self._input_registry.get_or_create_confirm_session(
                session_id
            )
            confirm_session.reconnect()
            await websocket.send_json(pending_confirm)
        try:
            while True:
                message = await websocket.receive_json()
                await self._handle_message(session_id, message, websocket)
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
            # 注销聊天客户端
            for cid, client in list(self._chat_manager._chat_clients.items()):
                if client.get("connection_id") == connection_id:
                    await self._chat_manager.unregister_client(cid)
            async with self._connection_state_lock:
                connections = self._active_connections.get(session_id)
                if connections:
                    connections.pop(connection_id, None)
                    if not connections:
                        self._active_connections.pop(session_id, None)
                        self._auth_store.pop(session_id, None)
            print(
                "[WS CLEANUP] end "
                f"session_id={session_id} connection_id={connection_id} "
                f"active_auth_after={session_id in self._auth_store}"
            )

    async def _handle_sync_request(
        self, session_id: str, agent_seqs: Dict[str, int], websocket: WebSocket
    ) -> None:
        """处理同步请求，一次性返回消息缓存中该 agent 的所有历史消息"""
        print(
            f"[SYNC_REQUEST] received session_id={session_id} "
            f"agent_seqs={agent_seqs} "
            f"cache_size={len(self._gateway._message_cache)}"
        )

        # 获取前端请求的 agent_id 列表
        requested_agent_ids = set(agent_seqs.keys())
        # 排除 __global__，单独处理
        requested_agent_ids.discard("__global__")
        has_global = "__global__" in agent_seqs

        # 收集所有匹配的历史消息（增量：只返回 seq > lastSeq 的消息）
        matched_messages = []
        for cached_message in self._gateway._message_cache:
            if not isinstance(cached_message, dict):
                continue

            # 获取消息的 agent_id
            msg_type = cached_message.get("type")
            if msg_type == "output":
                msg_payload = cached_message.get("payload", {})
                msg_agent_id = (
                    msg_payload.get("agent_id")
                    if isinstance(msg_payload, dict)
                    else None
                )
            elif msg_type == "input_result":
                msg_payload = cached_message.get("payload", {})
                msg_agent_id = (
                    msg_payload.get("agent_id")
                    if isinstance(msg_payload, dict)
                    else None
                )
            else:
                msg_agent_id = None

            # 检查是否匹配请求的 agent_id
            if msg_agent_id and msg_agent_id in requested_agent_ids:
                # 增量过滤：只返回序号大于客户端已有最新序号的消息
                last_seq = agent_seqs.get(msg_agent_id, -1)
                msg_seq = cached_message.get("seq", -1)
                if isinstance(msg_seq, (int, float)) and msg_seq > last_seq:
                    matched_messages.append(cached_message)
            elif msg_agent_id is None and has_global:
                # 全局消息的增量过滤
                last_seq = agent_seqs.get("__global__", -1)
                msg_seq = cached_message.get("seq", -1)
                if isinstance(msg_seq, (int, float)) and msg_seq > last_seq:
                    matched_messages.append(cached_message)

        # 限制最多返回最近30条消息，避免数据量过大
        MAX_SYNC_MESSAGES = 30
        if len(matched_messages) > MAX_SYNC_MESSAGES:
            matched_messages = matched_messages[-MAX_SYNC_MESSAGES:]

        # 合并为一条 sync_response 消息一次性发送
        print(
            f"[SYNC_REQUEST] sending sync_response with "
            f"{len(matched_messages)} messages"
        )
        await websocket.send_json(
            {
                "type": "sync_response",
                "payload": {"messages": matched_messages},
            }
        )
        print("[SYNC_REQUEST] sync_response sent successfully")

    async def _handle_message(
        self, session_id: str, message: Any, websocket: WebSocket
    ) -> None:
        if not isinstance(message, dict):
            return
        message_type = message.get("type")
        payload = message.get("payload") or {}

        if message_type == "sync_request":
            # 处理增量同步请求（仅 Agent 进程处理）
            if os.environ.get("IS_AGENT_PROCESS") == "1":
                agent_seqs = payload.get("agent_seqs", {})
                print(
                    f"[SYNC_REQUEST] dispatching to _handle_sync_request "
                    f"session_id={session_id} agent_seqs={agent_seqs}"
                )
                await self._handle_sync_request(session_id, agent_seqs, websocket)
            else:
                print(
                    f"[SYNC_REQUEST] IGNORED (not agent process) "
                    f"IS_AGENT_PROCESS={os.environ.get('IS_AGENT_PROCESS')}"
                )
            return
        if message_type == "input_result":
            text = payload.get("text", "")
            # 为用户输入消息分配序号
            agent_id = payload.get("agent_id")
            if agent_id:
                seq = self._gateway._agent_message_sequences.get(agent_id, 0)
                self._gateway._agent_message_sequences[agent_id] = seq + 1
            else:
                seq = self._gateway._global_message_sequence
                self._gateway._global_message_sequence += 1
            message_with_seq = dict(message)
            message_with_seq["seq"] = seq

            # ➕ 新增：将用户输入作为 output 消息广播至所有前端，确保所有前端收到带 seq 的用户输入
            user_input_msg = {
                "type": "output",
                "payload": {
                    "output_type": "user_input",
                    "agent_name": "user",
                    "text": text,
                    "lang": "text",
                    "agent_id": agent_id,
                },
                "seq": seq,
            }
            self._router.publish(user_input_msg, session_id=session_id)

            # 缓存用户输入消息，用于重连后恢复对话完整性
            self._gateway._message_cache.append(message_with_seq)
            # 将带 seq 的用户输入消息发回前端，让前端添加到历史记录
            self._router.publish(message_with_seq, session_id=session_id)
            # 检查当前是否正在等待输入
            session = self._input_registry.get_or_create(session_id)
            if session.is_waiting_for_input():
                # 正在等待输入，直接提交
                self._input_registry.submit_input(session_id, text)
            else:
                # 不在等待输入状态，存入全局缓冲区
                from jarvis.jarvis_utils.globals import add_input_buffer

                add_input_buffer(text)
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
            if rows is None or cols is None:
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
            # 先检查是否有正在运行的脚本进程，如果有则发送 SIGINT 信号
            script_pid = get_script_pid()
            if script_pid is not None:
                try:
                    os.kill(script_pid, signal.SIGINT)
                except OSError:
                    pass  # 进程可能已经结束
            set_interrupt(True)
            return
        if message_type == "get_status":
            # 处理前端主动请求状态的请求
            logger.info("[WS MESSAGE] Received get_status request")
            if get_agent_status_manager is not None:
                try:
                    status_manager = get_agent_status_manager()
                    current_status = status_manager.get_status()
                    logger.info(f"[WS MESSAGE] Current agent status: {current_status}")
                    # 返回 status_update 消息
                    status_message = {
                        "type": "status_update",
                        "payload": {"execution_status": current_status},
                    }
                    self._router.publish(status_message, session_id=session_id)
                    logger.info(
                        f"[WS MESSAGE] Published status_update to session {session_id}"
                    )
                except Exception as e:
                    logger.error(
                        f"[WS MESSAGE] Error handling get_status: {e}", exc_info=True
                    )
            else:
                logger.warning("[WS MESSAGE] get_agent_status_manager is not available")  # type: ignore[unreachable]
            return
        # 独立终端会话消息处理
        # 检查是否需要转发到远端节点
        if message_type in (
            "terminal_create",
            "terminal_close",
            "terminal_session_input",
            "terminal_session_resize",
        ):
            terminal_node_id = str(payload.get("node_id") or "").strip()
            if terminal_node_id and terminal_node_id not in (
                _node_runtime.local_node_id if _node_runtime else "master",
                "master",
                "",
            ):
                # 转发到远端节点
                if _node_connection_manager is None:
                    logger.error(
                        "[WS MESSAGE] Node connection manager is not available"
                    )
                    return
                try:
                    response = await _node_connection_manager.send_request_to_node(
                        terminal_node_id,
                        NODE_TERMINAL_REQUEST,
                        {
                            "action": message_type,
                            "payload": payload,
                            "session_id": session_id,
                        },
                    )
                    resp_payload = response.get("payload") or {}
                    # 对于 terminal_create，将响应转发给前端
                    if message_type == "terminal_create" and resp_payload.get(
                        "success"
                    ):
                        result_data = resp_payload.get("data") or {}
                        # 添加 node_id 以便前端知道终端在哪个节点上
                        result_data["node_id"] = terminal_node_id
                        result_msg = {
                            "type": "terminal_created",
                            "payload": result_data,
                        }
                        self._router.publish(result_msg, session_id=session_id)
                    elif message_type == "terminal_close" and resp_payload.get(
                        "success"
                    ):
                        result_msg = {
                            "type": "terminal_closed",
                            "payload": {"terminal_id": payload.get("terminal_id")},
                        }
                        self._router.publish(result_msg, session_id=session_id)
                except Exception as e:
                    save_exception(
                        e, module="jarvis_web_gateway.app", function="__init__"
                    )
                    pass
                return

        if message_type == "terminal_create":
            # 权限校验：terminal:create
            auth_payload = self._auth_store.get("default")
            user_id = None
            if auth_payload and isinstance(auth_payload, dict):
                user_info = auth_payload.get("user_info")
                if user_info and isinstance(user_info, dict):
                    user_id = user_info.get("user_id")
            if user_id and user_id != "system" and self._permission_manager:
                if not self._permission_manager.check_permission(
                    user_id, "terminal:create"
                ):
                    error_msg = {
                        "type": "terminal_error",
                        "payload": {"error": "Permission denied: terminal:create"},
                    }
                    self._router.publish(error_msg, session_id=session_id)
                    return
                # 节点访问校验
                check_node_id = terminal_node_id if terminal_node_id else "master"
                if not self._permission_manager.check_node_access(
                    user_id, check_node_id
                ):
                    error_msg = {
                        "type": "terminal_error",
                        "payload": {
                            "error": f"Permission denied: no access to node {check_node_id}"
                        },
                    }
                    self._router.publish(error_msg, session_id=session_id)
                    return
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
                            "node_id": str(
                                _node_runtime.local_node_id
                                if _node_runtime
                                else "master"
                            ),
                        },
                    }
                    self._router.publish(message, session_id=session_id)
            return
        if message_type == "terminal_close":
            # 权限校验：terminal:create（终端操作统一权限）
            auth_payload = self._auth_store.get("default")
            user_id = None
            if auth_payload and isinstance(auth_payload, dict):
                user_info = auth_payload.get("user_info")
                if user_info and isinstance(user_info, dict):
                    user_id = user_info.get("user_id")
            if user_id and user_id != "system" and self._permission_manager:
                if not self._permission_manager.check_permission(
                    user_id, "terminal:create"
                ):
                    error_msg = {
                        "type": "terminal_error",
                        "payload": {"error": "Permission denied: terminal:create"},
                    }
                    self._router.publish(error_msg, session_id=session_id)
                    return
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
            # 权限校验：terminal:create（终端操作统一权限）
            auth_payload = self._auth_store.get("default")
            user_id = None
            if auth_payload and isinstance(auth_payload, dict):
                user_info = auth_payload.get("user_info")
                if user_info and isinstance(user_info, dict):
                    user_id = user_info.get("user_id")
            if user_id and user_id != "system" and self._permission_manager:
                if not self._permission_manager.check_permission(
                    user_id, "terminal:create"
                ):
                    error_msg = {
                        "type": "terminal_error",
                        "payload": {"error": "Permission denied: terminal:create"},
                    }
                    self._router.publish(error_msg, session_id=session_id)
                    return
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
                if rows is None or cols is None:
                    return
                try:
                    rows_int = int(rows)
                    cols_int = int(cols)
                except (TypeError, ValueError):
                    return
                _terminal_session_manager.resize(terminal_id, rows_int, cols_int)
            return
        if message_type == "file_upload":
            # 权限校验：file:upload
            auth_payload = self._auth_store.get("default")
            user_id = None
            if auth_payload and isinstance(auth_payload, dict):
                user_info = auth_payload.get("user_info")
                if user_info and isinstance(user_info, dict):
                    user_id = user_info.get("user_id")
            if user_id and user_id != "system" and self._permission_manager:
                if not self._permission_manager.check_permission(
                    user_id, "file:upload"
                ):
                    error_msg = {
                        "type": "file_upload_response",
                        "message_id": message.get("message_id"),
                        "payload": {
                            "success": False,
                            "error": "Permission denied: file:upload",
                        },
                    }
                    self._router.publish(error_msg, session_id=session_id)
                    return
            # 处理文件上传请求
            message_id = message.get("message_id")
            file_name = payload.get("file_name")
            file_data = payload.get("file_data")

            if not all([message_id, file_name, file_data]):
                error_msg = {
                    "type": "file_upload_response",
                    "message_id": message_id,
                    "payload": {"success": False, "error": "Missing required fields"},
                }
                self._router.publish(error_msg, session_id=session_id)
                return

            # 检查是否需要转发到远程节点
            node_id = str(payload.get("node_id") or "").strip()
            if node_id and node_id not in (
                _node_runtime.local_node_id if _node_runtime else "master",
                "master",
                "",
            ):
                # 转发到远端节点
                if _node_connection_manager is None:
                    logger.error(
                        "[WS MESSAGE] Node connection manager is not available"
                    )
                    return
                try:
                    response = await _node_connection_manager.send_request_to_node(
                        node_id,
                        NODE_TERMINAL_REQUEST,
                        {
                            "action": "file_upload",
                            "payload": payload,
                            "session_id": session_id,
                        },
                    )
                    # 转发远端节点的响应给前端
                    self._router.publish(response, session_id=session_id)
                except Exception as e:
                    logger.error(
                        f"[WS MESSAGE] Failed to forward file upload to node {node_id}: {e}"
                    )
                    error_msg = {
                        "type": "file_upload_response",
                        "message_id": message_id,
                        "payload": {
                            "success": False,
                            "error": f"Failed to forward to node: {str(e)}",
                        },
                    }
                    self._router.publish(error_msg, session_id=session_id)
                return

            # 本地处理文件上传
            try:
                result = await _handle_file_upload(payload)
                response_msg = {
                    "type": "file_upload_response",
                    "message_id": message_id,
                    "payload": result,
                }
                self._router.publish(response_msg, session_id=session_id)
            except Exception as e:
                logger.error(
                    f"[WS MESSAGE] Error handling file upload: {e}", exc_info=True
                )
                error_msg = {
                    "type": "file_upload_response",
                    "message_id": message_id,
                    "payload": {"success": False, "error": str(e)},
                }
                self._router.publish(error_msg, session_id=session_id)
            return

        # ============================================================
        # 聊天室消息处理
        # ============================================================
        if message_type.startswith("chat_"):
            await self._handle_chat_message(message_type, payload, websocket)
            return

    async def _handle_chat_message(
        self, message_type: str, payload: Dict[str, Any], websocket: WebSocket
    ) -> None:
        """处理聊天室相关消息。"""
        try:
            if message_type == "chat_register":
                await self._handle_chat_register(payload, websocket)
            elif message_type == "chat_get_rooms":
                await self._handle_chat_get_rooms(websocket)
            elif message_type == "chat_create_room":
                await self._handle_chat_create_room(payload, websocket)
            elif message_type == "chat_join_room":
                await self._handle_chat_join_room(payload, websocket)
            elif message_type == "chat_leave_room":
                await self._handle_chat_leave_room(payload, websocket)
            elif message_type == "chat_delete_room":
                await self._handle_chat_delete_room(payload, websocket)
            elif message_type == "chat_send_message":
                await self._handle_chat_send_message(payload, websocket)
            elif message_type == "chat_get_clients":
                await self._handle_chat_get_clients(websocket)
            elif message_type == "chat_get_room_members":
                await self._handle_chat_get_room_members(payload, websocket)
            elif message_type == "chat_send_private":
                await self._handle_chat_send_private(payload, websocket)
            elif message_type == "chat_get_private_history":
                await self._handle_chat_get_private_history(payload, websocket)
            else:
                await websocket.send_json(
                    {
                        "type": "chat_error",
                        "payload": {"error": f"未知消息类型: {message_type}"},
                    }
                )
        except Exception as e:
            logger.error(f"[CHAT] Error handling {message_type}: {e}", exc_info=True)
            try:
                await websocket.send_json(
                    {"type": "chat_error", "payload": {"error": str(e)}}
                )
            except Exception:
                pass

    async def _handle_chat_register(
        self, payload: Dict[str, Any], websocket: WebSocket
    ) -> None:
        """注册聊天客户端。"""
        client_id = payload.get("client_id", "")
        name = payload.get("name", "匿名用户")
        if not client_id:
            await websocket.send_json(
                {
                    "type": "chat_register_response",
                    "payload": {"success": False, "error": "client_id 不能为空"},
                }
            )
            return
        connection_id = str(uuid.uuid4())
        # 从认证信息获取user_id
        auth_payload = self._auth_store.get("default")
        user_id = None
        if auth_payload and isinstance(auth_payload, dict):
            user_info = auth_payload.get("user_info")
            if user_info and isinstance(user_info, dict):
                user_id = user_info.get("user_id")
        # 从user_manager获取display_name
        display_name = None
        if user_id and self._user_manager:
            user_data = self._user_manager.get_user(user_id)
            if user_data:
                display_name = user_data.get("display_name")
        result = await self._chat_manager.register_client(
            client_id,
            name,
            connection_id,
            websocket,
            user_id=user_id,
            display_name=display_name,
        )
        await websocket.send_json({"type": "chat_register_response", "payload": result})

    async def _handle_chat_get_rooms(self, websocket: WebSocket) -> None:
        """获取聊天室列表。"""
        rooms = self._chat_manager.get_rooms()
        await websocket.send_json(
            {
                "type": "chat_get_rooms_response",
                "payload": {"success": True, "rooms": rooms},
            }
        )

    async def _handle_chat_create_room(
        self, payload: Dict[str, Any], websocket: WebSocket
    ) -> None:
        """创建聊天室。"""
        name = payload.get("name", "")
        creator_id = payload.get("client_id", "")
        if not name:
            await websocket.send_json(
                {
                    "type": "chat_create_room_response",
                    "payload": {"success": False, "error": "聊天室名称不能为空"},
                }
            )
            return
        result = await self._chat_manager.create_room(name, creator_id)
        await websocket.send_json(
            {"type": "chat_create_room_response", "payload": result}
        )
        # 广播新房间通知给所有其他在线用户
        if result.get("success"):
            await self._chat_manager.broadcast_to_all(
                {
                    "type": "chat_room_created",
                    "payload": {
                        "room_id": result["room_id"],
                        "name": result["name"],
                        "member_count": 1,
                        "created_by": creator_id,
                    },
                },
                exclude_client_id=creator_id,
            )

    async def _handle_chat_join_room(
        self, payload: Dict[str, Any], websocket: WebSocket
    ) -> None:
        """加入聊天室。"""
        room_id = payload.get("room_id", "")
        client_id = payload.get("client_id", "")
        result = await self._chat_manager.join_room(room_id, client_id)
        await websocket.send_json(
            {"type": "chat_join_room_response", "payload": result}
        )

    async def _handle_chat_leave_room(
        self, payload: Dict[str, Any], websocket: WebSocket
    ) -> None:
        """离开聊天室。"""
        room_id = payload.get("room_id", "")
        client_id = payload.get("client_id", "")
        result = await self._chat_manager.leave_room(room_id, client_id)
        await websocket.send_json(
            {"type": "chat_leave_room_response", "payload": result}
        )

    async def _handle_chat_delete_room(
        self, payload: Dict[str, Any], websocket: WebSocket
    ) -> None:
        """删除聊天室（仅创建者可删除）。"""
        room_id = payload.get("room_id", "")
        client_id = payload.get("client_id", "")
        result = await self._chat_manager.delete_room(room_id, client_id)
        if result.get("success"):
            # 通知被删除房间的所有成员
            room_name = result.get("name", "")
            members = result.get("members", [])
            for mid in members:
                if mid == client_id:
                    continue
                client = self._chat_manager.get_client(mid)
                if client and client.get("websocket"):
                    try:
                        await client["websocket"].send_json(
                            {
                                "type": "chat_room_deleted",
                                "payload": {"room_id": room_id, "name": room_name},
                            }
                        )
                    except Exception:
                        pass
        await websocket.send_json(
            {"type": "chat_delete_room_response", "payload": result}
        )

    async def _handle_chat_send_message(
        self, payload: Dict[str, Any], websocket: WebSocket
    ) -> None:
        """发送聊天室消息。"""
        room_id = payload.get("room_id", "")
        client_id = payload.get("client_id", "")
        content = payload.get("content", "")
        client = self._chat_manager.get_client(client_id)
        if not client:
            await websocket.send_json(
                {
                    "type": "chat_send_message_response",
                    "payload": {"success": False, "error": "客户端未注册"},
                }
            )
            return
        msg = {
            "type": "chat_message",
            "payload": {
                "room_id": room_id,
                "client_id": client_id,
                "sender_name": client["name"],
                "sender_display_name": client.get("display_name", client["name"]),
                "content": content,
                "timestamp": time.time(),
            },
        }
        await self._chat_manager.broadcast_to_room(
            room_id, msg, exclude_client_id=client_id
        )
        await websocket.send_json(
            {"type": "chat_send_message_response", "payload": {"success": True}}
        )

    async def _handle_chat_get_clients(self, websocket: WebSocket) -> None:
        """获取在线客户端列表。"""
        clients = self._chat_manager.get_clients()
        await websocket.send_json(
            {
                "type": "chat_get_clients_response",
                "payload": {"success": True, "clients": clients},
            }
        )

    async def _handle_chat_get_room_members(
        self, payload: Dict[str, Any], websocket: WebSocket
    ) -> None:
        """获取聊天室成员列表。"""
        room_id = payload.get("room_id", "")
        members = self._chat_manager.get_room_members(room_id)
        await websocket.send_json(
            {
                "type": "chat_get_room_members_response",
                "payload": {"success": True, "room_id": room_id, "members": members},
            }
        )

    async def _handle_chat_send_private(
        self, payload: Dict[str, Any], websocket: WebSocket
    ) -> None:
        """发送私聊消息。"""
        sender_id = payload.get("sender_id", "")
        receiver_id = payload.get("receiver_id", "")
        content = payload.get("content", "")
        result = await self._chat_manager.send_private(sender_id, receiver_id, content)
        await websocket.send_json(
            {"type": "chat_send_private_response", "payload": result}
        )

    async def _handle_chat_get_private_history(
        self, payload: Dict[str, Any], websocket: WebSocket
    ) -> None:
        """获取私聊历史消息。"""
        client_id = payload.get("client_id", "")
        other_id = payload.get("other_id", "")
        result = self._chat_manager.get_private_history(client_id, other_id)
        await websocket.send_json(
            {"type": "chat_get_private_history_response", "payload": result}
        )


def create_app(
    custom_app: Optional[FastAPI] = None,
    node_config: Optional[NodeRuntimeConfig] = None,
    port: int = 8000,
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

    # 初始化用户管理和权限管理
    from jarvis.jarvis_utils.utils import get_data_dir

    _data_dir = get_data_dir()
    user_manager = UserManager(_data_dir)
    permission_manager = PermissionManager(_data_dir)

    # 确保admin用户在sys-admin组中
    admin_user = user_manager.get_user_by_username("admin")
    if admin_user:
        admin_groups = permission_manager.get_user_groups(admin_user["user_id"])
        admin_group_names = (
            [g["name"] for g in admin_groups]
            if admin_groups and isinstance(admin_groups[0], dict)
            else (admin_groups or [])
        )
        if "sys-admin" not in admin_group_names:
            permission_manager.set_user_groups(admin_user["user_id"], ["sys-admin"])

    # 设置 node_secret 到环境变量（供 Unix Domain Socket 服务使用）
    if node_config.node_secret:
        os.environ["JARVIS_NODE_SECRET"] = node_config.node_secret

    # 根据节点模式设置 master_url 全局变量（仅在未设置时才设置，避免覆盖 Agent 已有的值）
    if jglobals.master_url is None:
        if node_config.is_child:
            # Child 节点：将传入的 master_url 转为 HTTP 协议
            if node_config.master_url:
                jglobals.master_url = node_config.master_url.replace(
                    "ws://", "http://"
                ).replace("wss://", "https://")
        elif node_config.is_master:
            # Master 节点：拼接本地 gateway URL
            jglobals.master_url = f"http://127.0.0.1:{port}"

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
    terminal_session_manager = TerminalSessionManager(max_sessions=None)

    def _build_callback_from_metadata(metadata: Dict[str, Any]):
        action_metadata = metadata.get("action")
        if not isinstance(action_metadata, dict):
            raise ValueError("Persisted timer metadata.action must be an object")
        return _build_timer_action({"action": action_metadata})[0]

    timer_manager = TimerManager(task_factory=_build_callback_from_metadata)

    # 保存 router 到全局，用于状态更新时推送消息
    global _router, _terminal_session_manager, _node_connection_manager, _node_runtime
    _router = router
    _terminal_session_manager = terminal_session_manager
    _node_connection_manager = node_connection_manager
    _node_runtime = node_runtime
    # 将 router 和 terminal_session_manager 也注入到 node_connection_manager，用于终端转发
    node_connection_manager._router = router
    node_connection_manager._terminal_session_manager = terminal_session_manager
    auth_store: Dict[str, Optional[Dict[str, Any]]] = {}
    gateway = WebGateway(router, input_registry, auth_store, terminal_input_registry)
    manager = WebSocketConnectionManager(
        router,
        input_registry,
        terminal_input_registry,
        gateway,
        auth_store,
        user_manager,
        permission_manager,
    )

    set_current_gateway(gateway)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Lifespan context manager for startup and shutdown events."""
        # Startup
        agent_manager.set_event_loop(asyncio.get_running_loop())
        await agent_manager.start_monitoring_for_running_agents()
        # 同步新Token到所有running状态的Agent
        gateway_token = os.environ.get("JARVIS_AUTH_TOKEN", "")
        if gateway_token:
            async with httpx.AsyncClient() as client:
                for agent in agent_manager.get_agent_list():
                    if agent.get("status") == "running":
                        port = agent.get("port")
                        if port:
                            try:
                                await client.post(
                                    f"http://127.0.0.1:{port}/update_token",
                                    json={"token": gateway_token},
                                    headers={"X-Internal-Sync": "true"},
                                    timeout=5.0,
                                )
                            except Exception as e:
                                save_exception(
                                    e,
                                    module="jarvis_web_gateway.app",
                                    function="_build_callback_from_metadata",
                                )
                                pass
        if node_config.is_master:
            node_runtime.mark_ready()
            # 启动 Unix Domain Socket 服务器（提供 node_secret 给子节点）
            await _start_node_secret_socket_server(node_config)
        else:
            node_runtime.mark_degraded()
            if child_node_client is not None:
                child_node_client.start()
        yield
        # Shutdown
        agent_manager._save_agents()
        await agent_proxy_manager.cleanup()
        terminal_session_manager.cleanup()
        if child_node_client is not None:
            await child_node_client.stop()
        timer_manager.shutdown()
        set_current_gateway(None)
        # 停止 Unix Domain Socket 服务器
        await _stop_node_secret_socket_server()

    # 使用自定义 app 或创建新 app
    if custom_app is not None:
        app = custom_app
    else:
        app = FastAPI(lifespan=lifespan)
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
    def verify_token(request: Request) -> Dict[str, Any]:
        """验证 HTTP 请求的 Token，返回用户信息。

        支持两种认证方式（任一通过即可）：
        1. Authorization: Bearer <token> - 兼容现有服务
        2. X-Jarvis-Token: <token> - 用于 LLM 代理场景，避免与 LLM API Key 冲突

        Args:
            request: FastAPI Request 对象

        Returns:
            用户信息字典

        Raises:
            HTTPException: Token 无效时抛出 401 错误
        """
        from fastapi import HTTPException

        # 尝试从 X-Jarvis-Token 头提取 Token（优先）
        jarvis_token = request.headers.get("X-Jarvis-Token")
        if jarvis_token:
            user_info = validate_gateway_token(jarvis_token)
            if user_info is None:
                raise HTTPException(
                    status_code=401,
                    detail={
                        "code": "INVALID_TOKEN",
                        "message": "Invalid or expired X-Jarvis-Token",
                    },
                )
            request.state.user_info = user_info
            return user_info

        # 尝试从 Authorization Header 提取 Token（兼容模式）
        authorization = request.headers.get("Authorization")
        if not authorization:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "MISSING_TOKEN",
                    "message": "Authorization or X-Jarvis-Token header is required",
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
        user_info = validate_gateway_token(token)
        if user_info is None:
            raise HTTPException(
                status_code=401,
                detail={"code": "INVALID_TOKEN", "message": "Invalid or expired token"},
            )
        request.state.user_info = user_info
        return user_info

    def verify_agent_proxy_access(request: Request) -> None:
        """验证 Agent HTTP 代理访问权限。

        已登录会话或 Bearer Token 任一通过即可。
        """
        if manager._auth_store.get("default") is not None:
            return
        verify_token(request)

    # HTTP API：登录接口
    @app.post("/api/auth/login")
    async def login(request: Request) -> Dict[str, Any]:
        """登录接口，验证用户名密码并返回 JWT Token。"""
        try:
            body = await request.json()
            username = str(body.get("username", "")).strip()
            password = str(body.get("password", "")).strip()

            if not username or not password:
                return {
                    "success": False,
                    "error": {
                        "code": "MISSING_CREDENTIALS",
                        "message": "username and password are required",
                    },
                }

            # 尝试用户认证
            user = user_manager.authenticate(username, password)
            if user:
                # JWT认证成功
                token = generate_jwt_token(
                    user_id=user["user_id"],
                    username=user["username"],
                    is_admin=user.get("is_admin", False),
                )
                logger.info(f"[AUTH] User '{username}' login successful (JWT)")
                return {
                    "success": True,
                    "data": {
                        "token": token,
                        "user": {
                            "user_id": user["user_id"],
                            "username": user["username"],
                            "display_name": user.get("display_name", ""),
                            "is_admin": user.get("is_admin", False),
                        },
                    },
                }

            logger.warning(f"[AUTH] Login failed for user '{username}'")
            return {
                "success": False,
                "error": {
                    "code": "AUTH_FAILED",
                    "message": "Invalid username or password",
                },
            }
        except Exception as e:
            logger.error(f"[AUTH] Login failed with exception: {type(e).__name__}: {e}")
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：登出接口
    @app.post("/api/auth/logout")
    async def logout(request: Request) -> Dict[str, Any]:
        """登出接口，将当前JWT加入黑名单。"""
        authorization = request.headers.get("Authorization")
        if authorization:
            token = extract_token_from_authorization_header(authorization)
            if token:
                revoke_token(token)
        jarvis_token = request.headers.get("X-Jarvis-Token")
        if jarvis_token:
            revoke_token(jarvis_token)
        return {"success": True, "data": {"message": "Logged out successfully"}}

    # HTTP API：获取当前用户信息
    @app.get("/api/auth/me")
    async def get_current_user(request: Request) -> Dict[str, Any]:
        """获取当前登录用户信息。"""
        user_info = verify_token(request)
        if user_info.get("user_id") != "system":
            full_user = user_manager.get_user(user_info["user_id"])
            if full_user:
                return {"success": True, "data": {"user": full_user}}
        return {"success": True, "data": {"user": user_info}}

    # 权限检查依赖
    def require_permission(resource: str, action: str):
        """创建需要特定权限的FastAPI依赖。"""
        from fastapi import HTTPException

        def check_perm(request: Request) -> Dict[str, Any]:
            user_info = verify_token(request)
            user_id = user_info.get("user_id", "")
            if user_id == "system":
                return user_info
            has_perm = permission_manager.check_permission(
                user_id, f"{resource}:{action}"
            )
            if not has_perm:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "PERMISSION_DENIED",
                        "message": f"Permission denied: {resource}:{action}",
                    },
                )
            return user_info

        return Depends(check_perm)

    @app.get("/api/users/brief", dependencies=[Depends(verify_token)])
    async def api_list_users_brief(
        request: Request, search: str = ""
    ) -> Dict[str, Any]:
        """列出用户简要信息（仅需登录，用于ACL选择等场景）。"""
        users = user_manager.list_users(search=search or None, limit=100)
        brief = [
            {
                "user_id": u.get("user_id"),
                "display_name": u.get("display_name", u.get("username")),
            }
            for u in users
        ]
        return {"success": True, "data": {"users": brief}}

    async def api_list_users(
        request: Request, search: str = "", offset: int = 0, limit: int = 50
    ) -> Dict[str, Any]:
        """列出用户（需要admin:users权限）。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        if user_info.get(
            "user_id"
        ) != "system" and not permission_manager.check_permission(
            user_info["user_id"], "admin:users"
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:users",
                },
            )
        users = user_manager.list_users(
            search=search or None, offset=offset, limit=limit
        )
        return {"success": True, "data": {"users": users}}

    @app.post("/api/users", dependencies=[Depends(verify_token)])
    async def api_create_user(request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
        """创建用户（需要admin:users权限）。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        if user_info.get(
            "user_id"
        ) != "system" and not permission_manager.check_permission(
            user_info["user_id"], "admin:users"
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:users",
                },
            )
        username = str(body.get("username", "")).strip()
        password = str(body.get("password", "")).strip()
        display_name = str(body.get("display_name", "")).strip() or None
        is_admin = bool(body.get("is_admin", False))
        if not username or not password:
            return {
                "success": False,
                "error": {
                    "code": "INVALID_INPUT",
                    "message": "username and password are required",
                },
            }
        try:
            user = user_manager.create_user(
                username, password, display_name=display_name, is_admin=is_admin
            )
            permission_manager.invalidate_cache(user["user_id"])
            return {"success": True, "data": {"user": user}}
        except ValueError as e:
            return {
                "success": False,
                "error": {"code": "VALIDATION_ERROR", "message": str(e)},
            }

    @app.get("/api/users/{user_id}", dependencies=[Depends(verify_token)])
    async def api_get_user(request: Request, user_id: str) -> Dict[str, Any]:
        """获取用户详情（只能查看自己，或admin:users权限）。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        is_self = user_info.get("user_id") == user_id
        if (
            not is_self
            and user_info.get("user_id") != "system"
            and not permission_manager.check_permission(
                user_info["user_id"], "admin:users"
            )
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:users",
                },
            )
        user = user_manager.get_user(user_id)
        if not user:
            return {
                "success": False,
                "error": {"code": "NOT_FOUND", "message": "User not found"},
            }
        return {"success": True, "data": {"user": user}}

    @app.put("/api/users/{user_id}", dependencies=[Depends(verify_token)])
    async def api_update_user(
        request: Request, user_id: str, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """更新用户信息（需要admin:users权限，或更新自己）。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        is_self = user_info.get("user_id") == user_id
        if (
            not is_self
            and user_info.get("user_id") != "system"
            and not permission_manager.check_permission(
                user_info["user_id"], "admin:users"
            )
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:users",
                },
            )
        try:
            user = user_manager.update_user(user_id, **body)
            if user:
                permission_manager.invalidate_cache(user_id)
                return {"success": True, "data": {"user": user}}
            return {
                "success": False,
                "error": {"code": "NOT_FOUND", "message": "User not found"},
            }
        except ValueError as e:
            return {
                "success": False,
                "error": {"code": "VALIDATION_ERROR", "message": str(e)},
            }

    @app.delete("/api/users/{user_id}", dependencies=[Depends(verify_token)])
    async def api_delete_user(request: Request, user_id: str) -> Dict[str, Any]:
        """删除用户（需要admin:users权限）。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        if user_info.get(
            "user_id"
        ) != "system" and not permission_manager.check_permission(
            user_info["user_id"], "admin:users"
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:users",
                },
            )
        success = user_manager.delete_user(user_id)
        if success:
            permission_manager.invalidate_cache(user_id)
            return {"success": True, "data": {"message": "User deleted"}}
        return {
            "success": False,
            "error": {
                "code": "NOT_FOUND",
                "message": "User not found or cannot be deleted",
            },
        }

    @app.post(
        "/api/users/{user_id}/reset-password", dependencies=[Depends(verify_token)]
    )
    async def api_reset_password(
        request: Request, user_id: str, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """重置用户密码（需要admin:users权限）。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        if user_info.get(
            "user_id"
        ) != "system" and not permission_manager.check_permission(
            user_info["user_id"], "admin:users"
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:users",
                },
            )
        new_password = str(body.get("new_password", "")).strip()
        if not new_password:
            return {
                "success": False,
                "error": {
                    "code": "INVALID_INPUT",
                    "message": "new_password is required",
                },
            }
        success = user_manager.reset_password(user_id, new_password)
        if success:
            return {"success": True, "data": {"message": "Password reset successfully"}}
        return {
            "success": False,
            "error": {"code": "NOT_FOUND", "message": "User not found"},
        }

    @app.post(
        "/api/users/{user_id}/change-password", dependencies=[Depends(verify_token)]
    )
    async def api_change_password(
        request: Request, user_id: str, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """修改密码（只能修改自己）。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        if user_info.get("user_id") != user_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Can only change own password",
                },
            )
        old_password = str(body.get("old_password", "")).strip()
        new_password = str(body.get("new_password", "")).strip()
        if not old_password or not new_password:
            return {
                "success": False,
                "error": {
                    "code": "INVALID_INPUT",
                    "message": "old_password and new_password are required",
                },
            }
        success = user_manager.change_password(user_id, old_password, new_password)
        if success:
            return {
                "success": True,
                "data": {"message": "Password changed successfully"},
            }
        return {
            "success": False,
            "error": {"code": "AUTH_FAILED", "message": "Old password is incorrect"},
        }

    # ==================== 权限管理 API ====================

    @app.get("/api/permissions/user/{user_id}", dependencies=[Depends(verify_token)])
    async def api_get_user_permissions(
        request: Request, user_id: str
    ) -> Dict[str, Any]:
        """获取用户权限。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        if (
            user_info.get("user_id") != "system"
            and user_info.get("user_id") != user_id
            and not permission_manager.check_permission(
                user_info["user_id"], "admin:permissions"
            )
        ):
            raise HTTPException(
                status_code=403,
                detail={"code": "PERMISSION_DENIED", "message": "Permission denied"},
            )
        perms = permission_manager.get_user_permissions(user_id)
        return {"success": True, "data": {"permissions": perms}}

    @app.get(
        "/api/permissions/user/{user_id}/groups", dependencies=[Depends(verify_token)]
    )
    async def api_get_user_groups(request: Request, user_id: str) -> Dict[str, Any]:
        """获取用户所属组。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        if (
            user_info.get("user_id") != "system"
            and user_info.get("user_id") != user_id
            and not permission_manager.check_permission(
                user_info["user_id"], "admin:permissions"
            )
        ):
            raise HTTPException(
                status_code=403,
                detail={"code": "PERMISSION_DENIED", "message": "Permission denied"},
            )
        groups = permission_manager.get_user_groups(user_id)
        return {"success": True, "data": {"groups": groups}}

    @app.put(
        "/api/permissions/user/{user_id}/groups", dependencies=[Depends(verify_token)]
    )
    async def api_set_user_groups(
        request: Request, user_id: str, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """设置用户所属组（需要admin:permissions权限）。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        if user_info.get(
            "user_id"
        ) != "system" and not permission_manager.check_permission(
            user_info["user_id"], "admin:permissions"
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:permissions",
                },
            )
        group_ids = body.get("group_ids", [])
        permission_manager.set_user_groups(user_id, group_ids)
        permission_manager.invalidate_cache(user_id)
        return {"success": True, "data": {"message": "User groups updated"}}

    @app.get(
        "/api/permissions/user/{user_id}/accessible-nodes",
        dependencies=[Depends(verify_token)],
    )
    async def api_get_user_accessible_nodes(
        request: Request, user_id: str
    ) -> Dict[str, Any]:
        """获取用户可访问的节点列表。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        if (
            user_info.get("user_id") != "system"
            and user_info.get("user_id") != user_id
            and not permission_manager.check_permission(
                user_info["user_id"], "admin:permissions"
            )
        ):
            raise HTTPException(
                status_code=403,
                detail={"code": "PERMISSION_DENIED", "message": "Permission denied"},
            )
        nodes = permission_manager.get_user_accessible_nodes(user_id)
        return {"success": True, "data": {"accessible_nodes": nodes}}

    @app.get(
        "/api/permissions/user/{user_id}/overrides",
        dependencies=[Depends(verify_token)],
    )
    async def api_get_user_overrides(request: Request, user_id: str) -> Dict[str, Any]:
        """获取用户权限覆盖。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        if (
            user_info.get("user_id") != "system"
            and user_info.get("user_id") != user_id
            and not permission_manager.check_permission(
                user_info["user_id"], "admin:permissions"
            )
        ):
            raise HTTPException(
                status_code=403,
                detail={"code": "PERMISSION_DENIED", "message": "Permission denied"},
            )
        overrides = permission_manager.get_user_overrides(user_id)
        return {"success": True, "data": {"overrides": overrides}}

    @app.put(
        "/api/permissions/user/{user_id}/overrides",
        dependencies=[Depends(verify_token)],
    )
    async def api_set_user_overrides(
        request: Request, user_id: str, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """设置用户权限覆盖（需要admin:permissions权限）。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        if user_info.get(
            "user_id"
        ) != "system" and not permission_manager.check_permission(
            user_info["user_id"], "admin:permissions"
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:permissions",
                },
            )
        overrides = body.get("overrides", {})
        permission_manager.set_user_overrides(user_id, overrides)
        permission_manager.invalidate_cache(user_id)
        return {"success": True, "data": {"message": "User overrides updated"}}

    # ==================== 组管理 API ====================

    @app.get("/api/permissions/groups", dependencies=[Depends(verify_token)])
    async def api_list_groups(request: Request) -> Dict[str, Any]:
        """列出所有权限组。"""
        groups = permission_manager.list_groups()
        return {"success": True, "data": {"groups": groups}}

    @app.get("/api/permissions/groups/{group_id}", dependencies=[Depends(verify_token)])
    async def api_get_group(request: Request, group_id: str) -> Dict[str, Any]:
        """获取权限组详情。"""
        group = permission_manager.get_group(group_id)
        if not group:
            return {
                "success": False,
                "error": {"code": "NOT_FOUND", "message": "Group not found"},
            }
        return {"success": True, "data": {"group": group}}

    @app.post("/api/permissions/groups", dependencies=[Depends(verify_token)])
    async def api_create_group(
        request: Request, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """创建权限组（需要admin:permissions权限）。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        if user_info.get(
            "user_id"
        ) != "system" and not permission_manager.check_permission(
            user_info["user_id"], "admin:permissions"
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:permissions",
                },
            )
        name = str(body.get("name", "")).strip()
        description = str(body.get("description", "")).strip() or None
        if not name:
            return {
                "success": False,
                "error": {"code": "INVALID_INPUT", "message": "name is required"},
            }
        try:
            group = permission_manager.create_group(
                name, display_name=name, description=description or ""
            )
            return {"success": True, "data": {"group": group}}
        except ValueError as e:
            return {
                "success": False,
                "error": {"code": "VALIDATION_ERROR", "message": str(e)},
            }

    @app.put("/api/permissions/groups/{group_id}", dependencies=[Depends(verify_token)])
    async def api_update_group(
        request: Request, group_id: str, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """更新权限组（需要admin:permissions权限）。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        if user_info.get(
            "user_id"
        ) != "system" and not permission_manager.check_permission(
            user_info["user_id"], "admin:permissions"
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:permissions",
                },
            )
        try:
            group = permission_manager.update_group(group_id, **body)
            if group:
                return {"success": True, "data": {"group": group}}
            return {
                "success": False,
                "error": {"code": "NOT_FOUND", "message": "Group not found"},
            }
        except ValueError as e:
            return {
                "success": False,
                "error": {"code": "VALIDATION_ERROR", "message": str(e)},
            }

    @app.delete(
        "/api/permissions/groups/{group_id}", dependencies=[Depends(verify_token)]
    )
    async def api_delete_group(request: Request, group_id: str) -> Dict[str, Any]:
        """删除权限组（需要admin:permissions权限）。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        if user_info.get(
            "user_id"
        ) != "system" and not permission_manager.check_permission(
            user_info["user_id"], "admin:permissions"
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:permissions",
                },
            )
        success = permission_manager.delete_group(group_id)
        if success:
            return {"success": True, "data": {"message": "Group deleted"}}
        return {
            "success": False,
            "error": {
                "code": "NOT_FOUND",
                "message": "Group not found or cannot be deleted",
            },
        }

    @app.get(
        "/api/permissions/groups/{group_id}/permissions",
        dependencies=[Depends(verify_token)],
    )
    async def api_get_group_permissions(
        request: Request, group_id: str
    ) -> Dict[str, Any]:
        """获取组权限（需要admin:permissions权限）。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        if user_info.get(
            "user_id"
        ) != "system" and not permission_manager.check_permission(
            user_info["user_id"], "admin:permissions"
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:permissions",
                },
            )
        perms = permission_manager.get_group_permissions(group_id)
        return {"success": True, "data": {"permissions": perms}}

    @app.put(
        "/api/permissions/groups/{group_id}/permissions",
        dependencies=[Depends(verify_token)],
    )
    async def api_set_group_permissions(
        request: Request, group_id: str, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """设置组权限（需要admin:permissions权限）。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        if user_info.get(
            "user_id"
        ) != "system" and not permission_manager.check_permission(
            user_info["user_id"], "admin:permissions"
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:permissions",
                },
            )
        permissions = body.get("permissions", {})
        permission_manager.set_group_permissions(group_id, permissions)
        permission_manager.invalidate_cache()
        return {"success": True, "data": {"message": "Group permissions updated"}}

    # ==================== 资源ACL API ====================

    @app.put(
        "/api/permissions/resources/{resource_type}/{resource_id}/acl",
        dependencies=[Depends(verify_token)],
    )
    async def api_set_resource_acl(
        request: Request, resource_type: str, resource_id: str, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """设置资源ACL（需要admin:permissions权限）。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        if user_info.get(
            "user_id"
        ) != "system" and not permission_manager.check_permission(
            user_info["user_id"], "admin:permissions"
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:permissions",
                },
            )

        acl = body.get("acl", {})
        permission_manager.set_resource_acl(resource_type, resource_id, acl)
        permission_manager.invalidate_cache()
        return {"success": True, "data": {"message": "Resource ACL updated"}}

    @app.get(
        "/api/permissions/resources/{resource_type}/{resource_id}/acl",
        dependencies=[Depends(verify_token)],
    )
    async def api_get_resource_acl(
        request: Request, resource_type: str, resource_id: str
    ) -> Dict[str, Any]:
        """获取资源ACL（需要admin:permissions权限）。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        if user_info.get(
            "user_id"
        ) != "system" and not permission_manager.check_permission(
            user_info["user_id"], "admin:permissions"
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:permissions",
                },
            )
        acl = permission_manager.get_resource_acl(resource_type, resource_id)
        return {"success": True, "data": {"acl": acl}}

    @app.delete(
        "/api/permissions/resources/{resource_type}/{resource_id}/acl",
        dependencies=[Depends(verify_token)],
    )
    async def api_delete_resource_acl(
        request: Request, resource_type: str, resource_id: str
    ) -> Dict[str, Any]:
        """删除资源ACL（需要admin:permissions权限）。"""
        from fastapi import HTTPException

        user_info = request.state.user_info
        if user_info.get(
            "user_id"
        ) != "system" and not permission_manager.check_permission(
            user_info["user_id"], "admin:permissions"
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:permissions",
                },
            )
        permission_manager.delete_resource_acl(resource_type, resource_id)
        permission_manager.invalidate_cache()
        return {"success": True, "data": {"message": "Resource ACL deleted"}}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await manager.handle(websocket)

    @app.websocket("/api/node/master/ws")
    async def master_websocket_endpoint(websocket: WebSocket) -> None:
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

        # 检查read权限：非owner需在access_acl.read中或有agent:delete权限
        user_id = None
        if auth_payload is not None:
            user_id = auth_payload.get("user_id")
        if user_id and user_id != "system":
            agent_info = agent_manager.get_agent(agent_id)
            if agent_info and agent_info.owner_id and agent_info.owner_id != user_id:
                access_acl = agent_info.access_acl or {}
                has_read = user_id in (access_acl.get("read") or [])
                has_delete = permission_manager.check_permission(
                    user_id, "agent:delete"
                )
                if not has_read and not has_delete:
                    await websocket.accept(subprotocol="jarvis-ws")
                    await _send_error(
                        websocket, "FORBIDDEN", "No read access to this agent"
                    )
                    await websocket.close(code=4403, reason="Forbidden")
                    return

        await websocket.accept(subprotocol="jarvis-ws")

        requested_node_id = str(websocket.query_params.get("node_id") or "").strip()
        route = node_runtime.agent_route_registry.get(agent_id)
        target_node_id = requested_node_id
        if not target_node_id and route is not None:
            target_node_id = str(route.node_id or "").strip()
        logger.info(
            "[WS PROXY] agent_id=%s requested_node_id=%s route_node_id=%s resolved_target_node_id=%s local_node_id=%s",
            agent_id,
            requested_node_id,
            str(route.node_id or "").strip() if route is not None else "",
            target_node_id,
            node_runtime.local_node_id,
        )

        if target_node_id and target_node_id not in (
            node_runtime.local_node_id,
            "master",
        ):
            remote_ws_session_id = str(uuid.uuid4())
            logger.info(
                "[WS PROXY] opening remote agent ws agent_id=%s target_node_id=%s session_id=%s",
                agent_id,
                target_node_id,
                remote_ws_session_id,
            )
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
                logger.info(
                    "[WS PROXY] remote open response agent_id=%s target_node_id=%s session_id=%s payload=%s",
                    agent_id,
                    target_node_id,
                    remote_ws_session_id,
                    open_payload,
                )
                if not open_payload.get("success"):
                    close_reason = (open_payload.get("error") or {}).get(
                        "message", "Remote websocket open failed"
                    )
                    logger.warning(
                        "[WS PROXY] remote open failed agent_id=%s target_node_id=%s session_id=%s reason=%s",
                        agent_id,
                        target_node_id,
                        remote_ws_session_id,
                        close_reason,
                    )
                    await websocket.close(
                        code=4003,
                        reason=close_reason,
                    )
                    return

                async def forward_client_to_remote() -> None:
                    while True:
                        data = await websocket.receive_text()
                        # 检查interact权限：拦截input_result/confirm_result/manual_interrupt
                        if user_id and user_id != "system":
                            try:
                                msg = json.loads(data)
                                msg_type = msg.get("type", "")
                                if msg_type in (
                                    "input_result",
                                    "confirm_result",
                                    "manual_interrupt",
                                ):
                                    agent_info = agent_manager.get_agent(agent_id)
                                    if (
                                        agent_info
                                        and agent_info.owner_id
                                        and agent_info.owner_id != user_id
                                    ):
                                        access_acl = agent_info.access_acl or {}
                                        has_interact = user_id in (
                                            access_acl.get("interact") or []
                                        )
                                        has_delete = (
                                            permission_manager.check_permission(
                                                user_id, "agent:delete"
                                            )
                                        )
                                        if not has_interact and not has_delete:
                                            await websocket.send_json(
                                                {
                                                    "type": "error",
                                                    "payload": {
                                                        "code": "FORBIDDEN",
                                                        "message": "No interact access to this agent",
                                                    },
                                                }
                                            )
                                            continue
                            except (json.JSONDecodeError, AttributeError):
                                pass
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
                logger.error(
                    "[WS PROXY] Remote websocket proxy error agent_id=%s target_node_id=%s session_id=%s error=%s",
                    agent_id,
                    target_node_id,
                    remote_ws_session_id,
                    e,
                )
                await websocket.close(code=4003, reason="Remote websocket proxy failed")
            finally:
                try:
                    logger.info(
                        "[WS PROXY] closing remote agent ws agent_id=%s target_node_id=%s session_id=%s",
                        agent_id,
                        target_node_id,
                        remote_ws_session_id,
                    )
                    await node_connection_manager.send_request_to_node(
                        target_node_id,
                        AGENT_WS_CLOSE_REQUEST,
                        {"session_id": remote_ws_session_id},
                    )
                except Exception as close_exc:
                    logger.warning(
                        "[WS PROXY] Remote websocket close warning agent_id=%s target_node_id=%s session_id=%s error=%s",
                        agent_id,
                        target_node_id,
                        remote_ws_session_id,
                        close_exc,
                    )
            return

        # 本地代理路径：包装websocket拦截interact消息
        if user_id and user_id != "system":
            _original_receive_text = websocket.receive_text
            _interact_types = {"input_result", "confirm_result", "manual_interrupt"}

            async def _checked_receive_text() -> str:
                data = await _original_receive_text()
                try:
                    msg = json.loads(data)
                    if msg.get("type", "") in _interact_types:
                        agent_info = agent_manager.get_agent(agent_id)
                        if (
                            agent_info
                            and agent_info.owner_id
                            and agent_info.owner_id != user_id
                        ):
                            access_acl = agent_info.access_acl or {}
                            has_interact = user_id in (access_acl.get("interact") or [])
                            has_delete = permission_manager.check_permission(
                                user_id, "agent:delete"
                            )
                            if not has_interact and not has_delete:
                                await websocket.send_json(
                                    {
                                        "type": "error",
                                        "payload": {
                                            "code": "FORBIDDEN",
                                            "message": "No interact access to this agent",
                                        },
                                    }
                                )
                                return await _checked_receive_text()
                except (json.JSONDecodeError, AttributeError):
                    pass
                return data

            websocket.receive_text = _checked_receive_text  # type: ignore[assignment]

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

    @app.websocket("/api/node/{node_id}/agent/{agent_id}/ws")
    async def node_agent_websocket_proxy(
        node_id: str, agent_id: str, websocket: WebSocket
    ) -> None:
        logger = logging.getLogger(__name__)
        normalized_node_id = str(node_id or "").strip()

        # 本地节点：委托给 agent_websocket_proxy
        if not normalized_node_id or normalized_node_id in (
            node_runtime.local_node_id,
            "master",
        ):
            await agent_websocket_proxy(agent_id, websocket)
            return

        # --- 远端节点：通过隧道转发 ---
        logger.info(
            "[NODE AGENT WS] remote agent ws node_id=%s agent_id=%s",
            normalized_node_id,
            agent_id,
        )

        # 认证
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

        remote_ws_session_id = str(uuid.uuid4())
        logger.info(
            "[NODE AGENT WS] opening remote agent ws node_id=%s agent_id=%s session_id=%s",
            normalized_node_id,
            agent_id,
            remote_ws_session_id,
        )
        try:
            open_response = await node_connection_manager.send_request_to_node(
                normalized_node_id,
                AGENT_WS_OPEN_REQUEST,
                {
                    "agent_id": agent_id,
                    "path": "ws",
                    "session_id": remote_ws_session_id,
                },
            )
            open_payload = open_response.get("payload") or {}
            logger.info(
                "[NODE AGENT WS] remote open response node_id=%s agent_id=%s session_id=%s payload=%s",
                normalized_node_id,
                agent_id,
                remote_ws_session_id,
                open_payload,
            )
            if not open_payload.get("success"):
                close_reason = (open_payload.get("error") or {}).get(
                    "message", "Remote websocket open failed"
                )
                logger.warning(
                    "[NODE AGENT WS] remote open failed node_id=%s agent_id=%s session_id=%s reason=%s",
                    normalized_node_id,
                    agent_id,
                    remote_ws_session_id,
                    close_reason,
                )
                await websocket.close(code=4003, reason=close_reason)
                return

            async def forward_client_to_remote() -> None:
                while True:
                    data = await websocket.receive_text()
                    send_response = await node_connection_manager.send_request_to_node(
                        normalized_node_id,
                        AGENT_WS_SEND_REQUEST,
                        {
                            "session_id": remote_ws_session_id,
                            "messages": [data],
                        },
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
                    recv_response = await node_connection_manager.send_request_to_node(
                        normalized_node_id,
                        AGENT_WS_RECV_REQUEST,
                        {
                            "session_id": remote_ws_session_id,
                            "timeout": 1.0,
                        },
                        timeout=65.0,
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
            logger.error(
                "[NODE AGENT WS] remote ws proxy error node_id=%s agent_id=%s session_id=%s error=%s",
                normalized_node_id,
                agent_id,
                remote_ws_session_id,
                e,
            )
            try:
                await websocket.close(code=4003, reason="Remote websocket proxy failed")
            except Exception as e:
                save_exception(
                    e,
                    module="jarvis_web_gateway.app",
                    function="verify_agent_proxy_access",
                )
                pass
        finally:
            try:
                logger.info(
                    "[NODE AGENT WS] closing remote agent ws node_id=%s agent_id=%s session_id=%s",
                    normalized_node_id,
                    agent_id,
                    remote_ws_session_id,
                )
                await node_connection_manager.send_request_to_node(
                    normalized_node_id,
                    AGENT_WS_CLOSE_REQUEST,
                    {"session_id": remote_ws_session_id},
                )
            except Exception as close_exc:
                logger.warning(
                    "[NODE AGENT WS] remote ws close warning node_id=%s agent_id=%s session_id=%s error=%s",
                    normalized_node_id,
                    agent_id,
                    remote_ws_session_id,
                    close_exc,
                )

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

            # --- agent HTTP 代理：path 以 agent/ 开头 ---
            normalized_path = str(path or "").strip("/")
            if normalized_path.startswith("agent/"):
                # 解析 agent/{agent_id}/{sub_path}
                agent_parts = normalized_path[len("agent/") :].split("/", 1)
                agent_id = agent_parts[0]
                agent_sub_path = agent_parts[1] if len(agent_parts) > 1 else ""
                if normalized_node_id in (node_runtime.local_node_id, "master"):
                    # 本地 agent HTTP 代理
                    try:
                        return await agent_proxy_manager.proxy_http_request(
                            request, agent_id, agent_sub_path
                        )
                    except AgentNotFoundError:
                        return Response(
                            content='{"error": "Agent not found"}',
                            status_code=404,
                            media_type="application/json",
                        )
                    except AgentNotRunningError:
                        return Response(
                            content='{"error": "Agent not running"}',
                            status_code=503,
                            media_type="application/json",
                        )
                    except ProxyConnectionError:
                        return Response(
                            content='{"error": "Proxy connection failed"}',
                            status_code=502,
                            media_type="application/json",
                        )
                else:
                    # 远端 agent HTTP 代理
                    response = await node_connection_manager.send_request_to_node(
                        normalized_node_id,
                        AGENT_HTTP_REQUEST,
                        {
                            "agent_id": agent_id,
                            "method": request.method,
                            "path": agent_sub_path,
                            "query": str(request.query_params),
                            "headers": dict(request.headers),
                            "body": body,
                        },
                    )
                    payload = response.get("payload") or {}
                    if not payload.get("success"):
                        error = payload.get("error") or {}
                        return Response(
                            content=f'{{"error": "{error.get("message", "Remote agent HTTP proxy failed")}"}}',
                            status_code=502,
                            media_type="application/json",
                        )
                    return Response(
                        content=payload.get("body", ""),
                        status_code=int(payload.get("status_code", 200)),
                        headers=payload.get("headers") or {},
                        media_type=(payload.get("headers") or {}).get("content-type"),
                    )

            # --- HTTP 代理：透传到外部 URL ---
            if normalized_path.startswith("http_proxy/"):
                target_url = normalized_path[len("http_proxy/") :]
                logger.info(
                    f"[HTTP PROXY] 收到代理请求：node_id={normalized_node_id}, target_url={target_url}"
                )

                # 调试：记录请求头和请求体
                debug_headers = dict(request.headers)
                logger.info(
                    f"[HTTP PROXY DEBUG] Headers: Accept={debug_headers.get('accept', 'N/A')}, Content-Type={debug_headers.get('content-type', 'N/A')}"
                )

                if normalized_node_id in (node_runtime.local_node_id, "master"):
                    # 本地 HTTP 代理

                    # 构建目标 URL
                    full_url = target_url
                    if request.query_params:
                        full_url = f"{full_url}?{request.query_params}"
                    logger.debug(f"[HTTP PROXY] 完整目标 URL: {full_url}")

                    # 验证 URL
                    if not full_url.startswith(("http://", "https://")):
                        return Response(
                            content='{"error": "URL must start with http:// or https://"}',
                            status_code=400,
                            media_type="application/json",
                        )

                    # 准备请求头
                    headers = dict(request.headers)
                    headers.pop("host", None)

                    # 读取请求体
                    body = await request.body()

                    # 判断是否需要流式响应：检查 Accept 头或请求体中的 stream 参数
                    accept_header = headers.get("accept", "")
                    want_stream = "text/event-stream" in accept_header

                    # 如果 Accept 头未指定，检查请求体中的 stream 字段（OpenAI SDK 格式）
                    if not want_stream and body:
                        try:
                            body_json = json.loads(body)
                            # 检查stream字段的各种真值形式
                            stream_value = body_json.get("stream")
                            if (
                                stream_value is True
                                or stream_value == 1
                                or stream_value == "true"
                            ):
                                want_stream = True
                                logger.info(
                                    "[HTTP PROXY] 从请求体检测到 stream=true，启用流式模式"
                                )
                        except (json.JSONDecodeError, ValueError):
                            # 如果JSON解析失败，检查原始body中是否包含stream关键字
                            body_str = (
                                body.decode("utf-8", errors="replace")
                                if isinstance(body, bytes)
                                else str(body)
                            )
                            if (
                                '"stream": true' in body_str
                                or '"stream":true' in body_str
                            ):
                                want_stream = True
                                logger.info(
                                    "[HTTP PROXY] 从请求体原始内容检测到 stream=true，启用流式模式"
                                )

                    logger.info(
                        f"[HTTP PROXY] 流式检测：Accept={accept_header}, want_stream={want_stream}, body_length={len(body) if body else 0}"
                    )

                    try:
                        if want_stream:

                            async def stream_response() -> AsyncGenerator[bytes, None]:
                                async with httpx.AsyncClient(
                                    timeout=httpx.Timeout(60.0)
                                ).stream(
                                    method=request.method,
                                    url=full_url,
                                    headers=headers,
                                    content=body,
                                ) as response:
                                    logger.debug(
                                        f"[NODE HTTP PROXY] Streaming response: {response.status_code}"
                                    )
                                    async for chunk in response.aiter_bytes():
                                        if chunk:
                                            yield chunk

                            return StreamingResponse(
                                stream_response(),
                                media_type="text/event-stream",
                                headers={
                                    "Cache-Control": "no-cache",
                                    "Connection": "keep-alive",
                                    "X-Accel-Buffering": "no",
                                },
                            )
                        else:
                            response = await httpx.AsyncClient(
                                timeout=httpx.Timeout(60.0)
                            ).request(
                                method=request.method,
                                url=full_url,
                                headers=headers,
                                content=body,
                            )

                            excluded_headers = {
                                "content-encoding",
                                "content-length",
                                "transfer-encoding",
                                "connection",
                            }
                            response_headers = {
                                k: v
                                for k, v in response.headers.items()
                                if k.lower() not in excluded_headers
                            }

                            return Response(
                                content=response.content,
                                status_code=response.status_code,
                                headers=response_headers,
                                media_type=response.headers.get("content-type"),
                            )
                    except httpx.TimeoutException:
                        return Response(
                            content='{"error": "Request timeout"}',
                            status_code=504,
                            media_type="application/json",
                        )
                    except httpx.RequestError as e:
                        logger.error(f"[NODE HTTP PROXY] Request error: {e}")
                        return Response(
                            content=f'{{"error": "Request failed: {str(e)}"}}',
                            status_code=502,
                            media_type="application/json",
                        )
                else:
                    # 远端 HTTP 代理
                    accept_header = dict(request.headers).get("accept", "")
                    want_stream = "text/event-stream" in accept_header

                    # 如果 Accept 头未指定，检查请求体中的 stream 字段（OpenAI SDK 格式）
                    if not want_stream and body:
                        try:
                            body_json = json.loads(body)
                            # 检查stream字段的各种真值形式
                            stream_value = body_json.get("stream")
                            if (
                                stream_value is True
                                or stream_value == 1
                                or stream_value == "true"
                            ):
                                want_stream = True
                                logger.info(
                                    "[HTTP PROXY] 远端代理从请求体检测到 stream=true，启用流式模式"
                                )
                        except (json.JSONDecodeError, ValueError):
                            # 如果JSON解析失败，检查原始body中是否包含stream关键字
                            body_str = (
                                body.decode("utf-8", errors="replace")
                                if isinstance(body, bytes)
                                else str(body)
                            )
                            if (
                                '"stream": true' in body_str
                                or '"stream":true' in body_str
                            ):
                                want_stream = True
                                logger.info(
                                    "[HTTP PROXY] 远端代理从请求体原始内容检测到 stream=true，启用流式模式"
                                )

                    logger.info(
                        f"[HTTP PROXY] 远端代理流式检测：Accept={accept_header}, want_stream={want_stream}, body_length={len(body) if body else 0}"
                    )

                    if want_stream:
                        # 流式模式：使用 streaming 方法
                        async def stream_from_node() -> AsyncGenerator[bytes, None]:
                            async for (
                                msg
                            ) in node_connection_manager.send_request_to_node_streaming(
                                normalized_node_id,
                                NODE_HTTP_PROXY_REQUEST,
                                {
                                    "method": request.method,
                                    "path": f"http_proxy/{target_url}",
                                    "query": str(request.query_params),
                                    "headers": dict(request.headers),
                                    "body": body,
                                    "streaming": True,
                                },
                            ):
                                chunk = msg.get("payload", {}).get("chunk", b"")
                                if isinstance(chunk, str):
                                    chunk = chunk.encode()
                                if chunk:
                                    yield chunk

                        return StreamingResponse(
                            stream_from_node(),
                            media_type="text/event-stream",
                            headers={
                                "Cache-Control": "no-cache",
                                "Connection": "keep-alive",
                                "X-Accel-Buffering": "no",
                            },
                        )
                    else:
                        response = await node_connection_manager.send_request_to_node(
                            normalized_node_id,
                            NODE_HTTP_PROXY_REQUEST,
                            {
                                "method": request.method,
                                "path": f"http_proxy/{target_url}",
                                "query": str(request.query_params),
                                "headers": dict(request.headers),
                                "body": body,
                            },
                        )
                    payload = response.get("payload") or {}
                    if "body" in payload:
                        return Response(
                            content=payload.get("body", ""),
                            status_code=int(payload.get("status_code", 200)),
                            headers=payload.get("headers") or {},
                            media_type=(payload.get("headers") or {}).get(
                                "content-type"
                            ),
                        )
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

            # --- 节点级 API ---
            logger.info(
                f"[NODE HTTP PROXY] 开始处理请求: node_id={normalized_node_id}, method={request.method}, path={path}"
            )
            if normalized_node_id in (node_runtime.local_node_id, "master"):
                result = await _dispatch_node_http_request(
                    method=request.method,
                    path=path,
                    query=str(request.query_params),
                    headers=dict(request.headers),
                    body=body,
                    user_info=getattr(request.state, "user_info", None),
                )
                return Response(
                    content=result.get("body", "{}"),
                    status_code=int(result.get("status_code", 200)),
                    media_type="application/json",
                )
            # 检查节点是否在线
            node_info = node_runtime.node_registry.get(normalized_node_id)
            if node_info is None:
                logger.error(
                    f"[NODE HTTP PROXY] 节点不存在: node_id={normalized_node_id}"
                )
                return Response(
                    content=f'{{"error": "Node {normalized_node_id} not found"}}',
                    status_code=502,
                    media_type="application/json",
                )
            if node_info.status != "online":
                logger.error(
                    f"[NODE HTTP PROXY] 节点不在线: node_id={normalized_node_id}, status={node_info.status}"
                )
                return Response(
                    content=f'{{"error": "Node {normalized_node_id} is not online (status: {node_info.status})"}}',
                    status_code=502,
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
            # 如果 payload 中有 body，说明 child 端已正确处理请求，
            # 直接返回其 status_code 和 body（即使业务级 success=False）。
            # 只有当 payload 中没有 body（真正的代理失败）时才返回 502。
            if "body" in payload:
                logger.info(
                    f"[NODE HTTP PROXY] 请求成功: node_id={normalized_node_id}, path={path}, status_code={payload.get('status_code', 200)}"
                )
                return Response(
                    content=payload.get("body", ""),
                    status_code=int(payload.get("status_code", 200)),
                    headers=payload.get("headers") or {},
                    media_type=(payload.get("headers") or {}).get("content-type"),
                )
            if not payload.get("success"):
                error = payload.get("error") or {}
                error_message = error.get("message", "Node HTTP proxy failed")
                error_code = error.get("code", "unknown")
                logger.error(
                    f"[NODE HTTP PROXY] 请求失败: node_id={normalized_node_id}, path={path}, error_code={error_code}, error_message={error_message}"
                )
                return Response(
                    content=f'{{"error": "{error_message}", "code": "{error_code}"}}',
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
            response = await agent_proxy_manager.proxy_http_request(
                request, agent_id, path
            )
            # 如果是 /status 请求且状态为 waiting_confirm，添加 pending_confirm 信息
            if path == "status" and request.method == "GET":
                try:
                    import json as json_module

                    body_bytes = bytes(response.body)
                    body = json_module.loads(body_bytes.decode("utf-8"))
                    if body.get("execution_status") == "waiting_confirm":
                        session_id = "default"
                        pending_confirm = input_registry.get_confirm_request(session_id)
                        if pending_confirm:
                            body["pending_confirm"] = pending_confirm
                            from starlette.responses import JSONResponse

                            return JSONResponse(
                                content=body,
                                status_code=response.status_code,
                                headers=dict(response.headers),
                            )
                except Exception as e:
                    logger.warning(
                        f"[HTTP PROXY] Failed to add pending_confirm to status: {e}"
                    )
            return response
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

    @app.get("/api/node/secret", dependencies=[Depends(verify_token)])
    async def get_node_secret(request: Request) -> Dict[str, Any]:
        """获取节点连接私钥（仅 master 模式，需要admin:config权限）。"""
        from fastapi import HTTPException

        user_info = getattr(request.state, "user_info", None)
        if (
            user_info
            and user_info.get("user_id") != "system"
            and not permission_manager.check_permission(
                user_info["user_id"], "admin:config"
            )
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:config",
                },
            )
        if not node_config.is_master:
            return {
                "success": False,
                "error": {
                    "code": "NOT_MASTER_MODE",
                    "message": "Node secret is only available in master mode",
                },
            }

        node_secret = os.environ.get("JARVIS_NODE_SECRET")
        if not node_secret:
            return {
                "success": False,
                "error": {
                    "code": "SECRET_NOT_CONFIGURED",
                    "message": "Node secret is not configured",
                },
            }

        return {
            "success": True,
            "data": {
                "node_secret": node_secret,
            },
        }

    @app.get("/api/nodes/{node_id}/config", dependencies=[Depends(verify_token)])
    async def get_node_config(node_id: str, request: Request) -> Dict[str, Any]:
        """获取指定节点的配置（需要admin:config权限）。"""
        from fastapi import HTTPException

        user_info = getattr(request.state, "user_info", None)
        if (
            user_info
            and user_info.get("user_id") != "system"
            and not permission_manager.check_permission(
                user_info["user_id"], "admin:config"
            )
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:config",
                },
            )
        try:
            # 检查是否是本地节点
            if node_id in (node_runtime.local_node_id, "master"):
                # 读取本地配置
                config_file = pathlib.Path.home() / ".jarvis" / "config.yaml"
                if not config_file.exists():
                    return {
                        "success": False,
                        "error": {
                            "code": "CONFIG_NOT_FOUND",
                            "message": "Config file not found",
                        },
                    }

                with open(config_file, "r", encoding="utf-8") as f:
                    config_data = yaml.safe_load(f) or {}

                return {
                    "success": True,
                    "data": {
                        "node_id": node_id,
                        "config": config_data,
                    },
                }

            # 检查远程节点状态
            node_info = node_runtime.node_registry.get(node_id)
            if node_info is None:
                return {
                    "success": False,
                    "error": {
                        "code": "NODE_NOT_FOUND",
                        "message": f"Node not found: {node_id}",
                    },
                }

            if node_info.status != "online":
                return {
                    "success": False,
                    "error": {
                        "code": "NODE_OFFLINE",
                        "message": f"Node is offline: {node_id}",
                    },
                }

            # 从远程节点获取配置
            response = await node_connection_manager.send_request_to_node(
                node_id,
                CONFIG_GET_REQUEST,
                {},
                timeout=30.0,
            )

            payload = response.get("payload") or {}
            if payload.get("success"):
                return {
                    "success": True,
                    "data": {
                        "node_id": node_id,
                        "config": payload.get("data", {}).get("config_data", {}),
                    },
                }
            else:
                error = payload.get("error") or {}
                return {
                    "success": False,
                    "error": error,
                }
        except Exception as e:
            error_message = str(e).strip()
            if not error_message:
                if isinstance(e, TimeoutError):
                    error_message = f"Get config timed out for node: {node_id}"
                else:
                    error_message = f"Get config failed for node: {node_id}"
            logger.error(
                "[CONFIG GET] failed node_id=%s error=%s",
                node_id,
                error_message,
                exc_info=True,
            )
            return {
                "success": False,
                "error": {
                    "code": "GET_CONFIG_FAILED",
                    "message": error_message,
                },
            }

    @app.post("/api/nodes/{node_id}/config", dependencies=[Depends(verify_token)])
    async def set_node_config(
        node_id: str, request_body: Dict[str, Any], request: Request
    ) -> Dict[str, Any]:
        """设置指定节点的配置（需要admin:config权限）。"""
        from fastapi import HTTPException

        user_info = getattr(request.state, "user_info", None)
        if (
            user_info
            and user_info.get("user_id") != "system"
            and not permission_manager.check_permission(
                user_info["user_id"], "admin:config"
            )
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:config",
                },
            )
        try:
            config_sections = request_body.get("config_sections", [])
            config_data = request_body.get("config_data", {})

            if not config_sections:
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "config_sections is required",
                    },
                }

            if not config_data:
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "config_data is required",
                    },
                }

            # 检查是否是本地节点
            if node_id in (node_runtime.local_node_id, "master"):
                # 本地节点直接应用配置
                try:
                    config_file = pathlib.Path.home() / ".jarvis" / "config.yaml"

                    # 备份原配置文件
                    backup_file = config_file.with_suffix(".yaml.bak")
                    if config_file.exists():
                        shutil.copy2(config_file, backup_file)

                    # 读取现有配置
                    existing_config: Dict[str, Any] = {}
                    if config_file.exists():
                        with open(config_file, "r", encoding="utf-8") as f:
                            existing_config = yaml.safe_load(f) or {}

                    # 更新配置
                    updated_config = existing_config.copy()
                    for section in config_sections:
                        if section in config_data:
                            updated_config[section] = config_data[section]

                    # 保存配置
                    config_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(config_file, "w", encoding="utf-8") as f:
                        yaml.safe_dump(
                            updated_config,
                            f,
                            allow_unicode=True,
                            default_flow_style=False,
                        )

                    return {
                        "success": True,
                        "data": {
                            "node_id": node_id,
                            "message": "配置设置成功",
                            "backup_file": str(backup_file),
                        },
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "error": {
                            "code": "CONFIG_SET_ERROR",
                            "message": str(e),
                        },
                    }

            # 检查远程节点状态
            node_info = node_runtime.node_registry.get(node_id)
            if node_info is None:
                return {
                    "success": False,
                    "error": {
                        "code": "NODE_NOT_FOUND",
                        "message": f"Node not found: {node_id}",
                    },
                }

            if node_info.status != "online":
                return {
                    "success": False,
                    "error": {
                        "code": "NODE_OFFLINE",
                        "message": f"Node is offline: {node_id}",
                    },
                }

            # 发送配置设置请求到远程节点
            response = await node_connection_manager.send_request_to_node(
                node_id,
                CONFIG_SET_REQUEST,
                {
                    "config_sections": config_sections,
                    "config_data": config_data,
                },
                timeout=30.0,
            )

            payload = response.get("payload") or {}
            if payload.get("success"):
                return {
                    "success": True,
                    "data": {
                        "node_id": node_id,
                        "message": "配置设置成功",
                        "data": payload.get("data", {}),
                    },
                }
            else:
                error = payload.get("error") or {}
                return {
                    "success": False,
                    "error": error,
                }
        except Exception as e:
            error_message = str(e).strip()
            if not error_message:
                if isinstance(e, TimeoutError):
                    error_message = f"Set config timed out for node: {node_id}"
                else:
                    error_message = f"Set config failed for node: {node_id}"
            logger.error(
                "[CONFIG SET] failed node_id=%s error=%s",
                node_id,
                error_message,
                exc_info=True,
            )
            return {
                "success": False,
                "error": {
                    "code": "SET_CONFIG_FAILED",
                    "message": error_message,
                },
            }

    @app.post("/api/service/restart", dependencies=[Depends(verify_token)])
    async def restart_service(
        request_body: Dict[str, Any], request: Request
    ) -> Dict[str, Any]:
        """请求 jarvis-service 重启服务（需要admin:config权限）。"""
        from fastapi import HTTPException

        user_info = getattr(request.state, "user_info", None)
        if (
            user_info
            and user_info.get("user_id") != "system"
            and not permission_manager.check_permission(
                user_info["user_id"], "admin:config"
            )
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:config",
                },
            )
        try:
            target_node_id = str(request_body.get("node_id") or "").strip()
            restart_frontend = bool(request_body.get("restart_frontend", True))

            # 如果指定了远端节点，转发重启请求
            if target_node_id and target_node_id not in (
                node_runtime.local_node_id,
                "master",
            ):
                node_info = node_runtime.node_registry.get(target_node_id)
                if node_info is None:
                    return {
                        "success": False,
                        "error": {
                            "code": "NODE_NOT_FOUND",
                            "message": f"Node not found: {target_node_id}",
                        },
                    }
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
                    SERVICE_RESTART_REQUEST,
                    {"restart_frontend": restart_frontend},
                    timeout=30.0,
                )
                payload = response.get("payload") or {}
                if not payload.get("success"):
                    error = payload.get("error") or {}
                    return {
                        "success": False,
                        "error": {
                            "code": error.get("code", "RESTART_FAILED"),
                            "message": error.get("message", "Remote restart failed"),
                        },
                    }
                return {
                    "success": True,
                    "data": {
                        "node_id": target_node_id,
                        "message": f"已请求节点 {target_node_id} 重启服务",
                    },
                }

            # 本地重启
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
            # 根据 restart_frontend 参数选择信号
            # Linux: SIGUSR1/SIGUSR2
            # Windows: 通过 TCP 命令通道发送重启命令
            if sys.platform != "win32":
                # SIGUSR1: 重启所有服务（包括前端）
                # SIGUSR2: 只重启网关服务
                signal_to_send = signal.SIGUSR1 if restart_frontend else signal.SIGUSR2
                signal_name = "SIGUSR1" if restart_frontend else "SIGUSR2"
                os.kill(service_pid, signal_to_send)
            else:
                # Windows: 通过 TCP 命令通道发送重启命令
                import socket as socket_module

                command = "RESTART_ALL" if restart_frontend else "RESTART_GATEWAY_ONLY"
                try:
                    sock = socket_module.socket(
                        socket_module.AF_INET, socket_module.SOCK_STREAM
                    )
                    sock.connect(("127.0.0.1", _RESTART_COMMAND_TCP_PORT))
                    sock.sendall(command.encode("utf-8") + b"\n")
                    sock.close()
                    signal_name = command
                except Exception as e:
                    logger.warning(f"Failed to send restart command via TCP: {e}")
                    signal_name = f"TCP_FAILED: {e}"
            message = (
                "已请求 jarvis-service 重启所有服务"
                if restart_frontend
                else "已请求 jarvis-service 只重启网关服务（前端保持运行）"
            )
            return {
                "success": True,
                "data": {
                    "pid": service_pid,
                    "signal": signal_name,
                    "message": message,
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

    @app.post("/api/nodes/{node_id}/code-update", dependencies=[Depends(verify_token)])
    async def node_code_update(node_id: str, request: Request) -> Dict[str, Any]:
        """更新指定节点的代码到 main 分支（需要admin:config权限）。"""
        from fastapi import HTTPException

        user_info = getattr(request.state, "user_info", None)
        if (
            user_info
            and user_info.get("user_id") != "system"
            and not permission_manager.check_permission(
                user_info["user_id"], "admin:config"
            )
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Permission denied: admin:config",
                },
            )
        try:
            # 检查是否是本地节点
            if node_id in (node_runtime.local_node_id, "master"):
                # 本地节点直接执行更新
                try:
                    import subprocess

                    result = subprocess.run(
                        ["git", "pull", "origin", "main"],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if result.returncode == 0:
                        return {
                            "success": True,
                            "data": {
                                "node_id": node_id,
                                "message": "代码更新成功",
                                "output": result.stdout,
                            },
                        }
                    else:
                        return {
                            "success": False,
                            "error": {
                                "code": "UPDATE_FAILED",
                                "message": result.stderr or "代码更新失败",
                            },
                        }
                except subprocess.TimeoutExpired:
                    return {
                        "success": False,
                        "error": {
                            "code": "TIMEOUT",
                            "message": "代码更新超时",
                        },
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "error": {
                            "code": "UPDATE_FAILED",
                            "message": str(e),
                        },
                    }

            # 检查远程节点状态
            node_info = node_runtime.node_registry.get(node_id)
            if node_info is None:
                return {
                    "success": False,
                    "error": {
                        "code": "NODE_NOT_FOUND",
                        "message": f"Node not found: {node_id}",
                    },
                }

            if node_info.status != "online":
                return {
                    "success": False,
                    "error": {
                        "code": "NODE_OFFLINE",
                        "message": f"Node is offline: {node_id}",
                    },
                }

            # 发送更新请求到远程节点
            response = await node_connection_manager.send_request_to_node(
                node_id,
                CODE_UPDATE_TO_MAIN_REQUEST,
                {},
                timeout=60.0,
            )

            payload = response.get("payload") or {}
            if payload.get("success"):
                return {
                    "success": True,
                    "data": {
                        "node_id": node_id,
                        "message": "代码更新成功",
                        "output": payload.get("data", {}).get("message", ""),
                    },
                }
            else:
                return {
                    "success": False,
                    "error": {
                        "code": "UPDATE_FAILED",
                        "message": payload.get("error", {}).get(
                            "message", "代码更新失败"
                        ),
                    },
                }
        except Exception as e:
            error_message = str(e).strip()
            if not error_message:
                if isinstance(e, TimeoutError):
                    error_message = f"Code update timed out for node: {node_id}"
                else:
                    error_message = f"Code update failed for node: {node_id}"
            logger.error(
                "[CODE UPDATE] failed node_id=%s error=%s",
                node_id,
                error_message,
                exc_info=True,
            )
            return {
                "success": False,
                "error": {
                    "code": "UPDATE_FAILED",
                    "message": error_message,
                },
            }

    # HTTP API：创建 Agent（需要认证）
    @app.post("/api/agents", dependencies=[Depends(verify_token)])
    async def create_agent(
        request_body: Dict[str, Any], request: Request
    ) -> Dict[str, Any]:
        """创建 Agent。"""
        try:
            # 从认证信息获取owner_id
            user_info = getattr(request.state, "user_info", None)
            if user_info and user_info.get("user_id"):
                owner_id = user_info["user_id"]
            else:
                owner_id = request_body.get("owner_id")
            agent_type = request_body.get("agent_type")
            working_dir = request_body.get("working_dir")
            name = request_body.get("name")
            llm_group = request_body.get("llm_group", "default")
            tool_group = request_body.get("tool_group", "default")
            config_file = request_body.get("config_file")
            task = request_body.get("task")
            additional_args = request_body.get("additional_args")
            worktree = bool(request_body.get("worktree", False))
            quick_mode = bool(request_body.get("quick_mode", False))
            restore_session = request_body.get("restore_session")
            # 确保 restore_session 是布尔值或字符串
            if isinstance(restore_session, str):
                # 如果是字符串，保持原样（指定文件路径）
                pass
            elif restore_session:
                # 如果是真值（如 True），转换为布尔值
                restore_session = True
            else:
                # 如果是假值（如 False, None），转换为 False
                restore_session = False
            no_interaction_mode = bool(request_body.get("no_interaction_mode", False))
            proxy_node = request_body.get("proxy_node")
            access_acl = request_body.get("access_acl")
            target_node_id = str(request_body.get("node_id") or "").strip()

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

            # 验证无交互模式：必须提供 task
            if no_interaction_mode and not task:
                return {
                    "success": False,
                    "error": {
                        "code": "MISSING_TASK",
                        "message": "task is required when no_interaction_mode is enabled",
                    },
                }

            resolved_target_node = target_node_id or node_runtime.local_node_id

            # 节点访问校验
            if owner_id and owner_id != "system" and permission_manager:
                if not permission_manager.check_node_access(
                    owner_id, resolved_target_node
                ):
                    return {
                        "success": False,
                        "error": {
                            "code": "PERMISSION_DENIED",
                            "message": f"Permission denied: no access to node {resolved_target_node}",
                        },
                    }

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
                        "quick_mode": quick_mode,
                        "restore_session": restore_session,
                        "no_interaction_mode": no_interaction_mode,
                        "proxy_node": proxy_node,
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
                quick_mode=quick_mode,
                restore_session=restore_session,
                no_interaction_mode=no_interaction_mode,
                proxy_node=proxy_node,
                owner_id=owner_id,
                access_acl=access_acl,
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
    async def get_agents(request: Request) -> Dict[str, Any]:
        """获取 Agent 列表（按用户权限过滤）。"""
        try:
            agents = agent_manager.get_agent_list()
            user_info = getattr(request.state, "user_info", None)
            user_id = user_info.get("user_id") if user_info else None
            known_agent_ids: set[str] = set()
            for agent in agents:
                agent_id = str(agent.get("agent_id") or "")
                if agent_id:
                    known_agent_ids.add(agent_id)
                route = node_runtime.agent_route_registry.get(agent_id)
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
            # 按用户权限过滤：非system用户只能看到自己owner的、ACL中有read权限的、或有agent:delete权限的
            if user_id and user_id != "system":
                filtered = []
                for agent in agents:
                    agent_id = agent.get("agent_id", "")
                    owner_id = agent.get("owner_id")
                    # owner可见
                    if owner_id == user_id:
                        filtered.append(agent)
                        continue
                    # ACL中有read权限可见
                    access_acl = agent.get("access_acl") or {}
                    if user_id in (access_acl.get("read") or []):
                        filtered.append(agent)
                        continue
                    # 有agent:delete权限可见
                    if permission_manager.check_permission(user_id, "agent:delete"):
                        filtered.append(agent)
                        continue
                agents = filtered

            return {"success": True, "data": agents}
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：获取模型组列表
    def _reload_model_groups_config() -> Dict[str, Any]:
        """重新加载模型组相关配置，不影响全局配置。"""
        try:
            # 查找并加载配置文件

            # 获取用户主目录的配置文件
            user_config_path = os.path.expanduser("~/.jarvis/config.yaml")
            config_files = []

            # 添加用户配置文件（如果存在）
            if os.path.exists(user_config_path):
                config_files.append(user_config_path)

            # 查找项目配置文件
            project_config_files = _find_all_config_files(os.getcwd())
            config_files.extend(project_config_files)

            if not config_files:
                return {}

            # 合并配置（项目配置覆盖用户配置）
            _, merged_config = _merge_configs(config_files)
            return merged_config

        except Exception:
            # 如果重新加载失败，返回空配置
            return {}

    @app.get("/api/model-groups", dependencies=[Depends(verify_token)])
    async def get_model_groups() -> Dict[str, Any]:
        """获取模型组列表。"""
        try:
            # 每次请求都重新加载配置，确保获取最新数据
            config = _reload_model_groups_config()
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
                            smart_model = str(smart_config.get("model", smart_llm_ref))

                    if normal_llm_ref and normal_llm_ref in llms:
                        normal_config = llms[normal_llm_ref]
                        if isinstance(normal_config, dict):
                            normal_model = str(
                                normal_config.get("model", normal_llm_ref)
                            )

                    if cheap_llm_ref and cheap_llm_ref in llms:
                        cheap_config = llms[cheap_llm_ref]
                        if isinstance(cheap_config, dict):
                            cheap_model = str(cheap_config.get("model", cheap_llm_ref))

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
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：停止 Agent
    @app.delete("/api/agents/{agent_id}/stop", dependencies=[Depends(verify_token)])
    async def stop_agent(agent_id: str, request: Request) -> Dict[str, Any]:
        """停止 Agent。"""
        # 权限检查：只有owner或admin可以停止Agent
        user_info = getattr(request.state, "user_info", None)
        if user_info and user_info.get("user_id") != "system":
            agent_info = agent_manager.get_agent(agent_id)
            if (
                agent_info
                and agent_info.owner_id
                and agent_info.owner_id != user_info.get("user_id")
            ):
                if not permission_manager.check_permission(
                    user_info["user_id"], "agent:delete"
                ):
                    return {
                        "success": False,
                        "error": {
                            "code": "FORBIDDEN",
                            "message": "You can only stop your own agents",
                        },
                    }
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
                        nid,
                        AGENT_STOP_REQUEST,
                        {"agent_id": agent_id},
                        timeout=10.0,
                    )
                    payload = response.get("payload") or {}
                    if payload.get("success"):
                        return {"success": True, "data": payload.get("result")}
                except Exception as e:
                    save_exception(
                        e,
                        module="jarvis_web_gateway.app",
                        function="_reload_model_groups_config",
                    )
                    pass
            return {
                "success": False,
                "error": {
                    "code": "AGENT_NOT_FOUND",
                    "message": f"Agent not found: {agent_id}",
                },
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：更新 Agent（重命名）
    @app.patch("/api/agents/{agent_id}", dependencies=[Depends(verify_token)])
    async def patch_agent(
        agent_id: str, request_body: Dict[str, Any], request: Request
    ) -> Dict[str, Any]:
        """更新 Agent 信息（目前只支持重命名）。"""
        # 权限检查：只有owner或admin可以更新Agent
        user_info = getattr(request.state, "user_info", None)
        if user_info and user_info.get("user_id") != "system":
            agent_info = agent_manager.get_agent(agent_id)
            if (
                agent_info
                and agent_info.owner_id
                and agent_info.owner_id != user_info.get("user_id")
            ):
                if not permission_manager.check_permission(
                    user_info["user_id"], "agent:delete"
                ):
                    return {
                        "success": False,
                        "error": {
                            "code": "FORBIDDEN",
                            "message": "You can only update your own agents",
                        },
                    }
        try:
            name = request_body.get("name")
            target_node_id = str(request_body.get("node_id") or "").strip()

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
                            "message": error.get(
                                "message", "Remote agent update failed"
                            ),
                        },
                    }
                body = payload.get("body") or "{}"
                return json.loads(body)  # type: ignore[no-any-return]

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

    # HTTP API：更新 Agent 访问控制
    @app.put("/api/agents/{agent_id}/access", dependencies=[Depends(verify_token)])
    async def update_agent_access(
        agent_id: str, request_body: Dict[str, Any], request: Request
    ) -> Dict[str, Any]:
        """更新 Agent 的访问控制列表（仅 owner 可操作）。"""
        user_info = getattr(request.state, "user_info", None)
        if user_info and user_info.get("user_id") != "system":
            agent_info = agent_manager.get_agent(agent_id)
            if (
                agent_info
                and agent_info.owner_id
                and agent_info.owner_id != user_info.get("user_id")
            ):
                return {
                    "success": False,
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "Only the agent owner can update access control",
                    },
                }

        access_acl = request_body.get("access_acl")
        if access_acl is not None and not isinstance(access_acl, dict):
            return {
                "success": False,
                "error": {
                    "code": "INVALID_ARGUMENT",
                    "message": "access_acl must be a dict",
                },
            }

        try:
            result = agent_manager.update_agent_access(agent_id, access_acl or {})
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

    @app.delete("/api/agents/{agent_id}", dependencies=[Depends(verify_token)])
    async def delete_agent(
        agent_id: str, request: Request, node_id: str = ""
    ) -> Dict[str, Any]:
        """删除 Agent。"""
        # 权限检查：只有owner或admin可以删除Agent
        user_info = getattr(request.state, "user_info", None)
        if user_info and user_info.get("user_id") != "system":
            agent_info = agent_manager.get_agent(agent_id)
            if (
                agent_info
                and agent_info.owner_id
                and agent_info.owner_id != user_info.get("user_id")
            ):
                if not permission_manager.check_permission(
                    user_info["user_id"], "agent:delete"
                ):
                    return {
                        "success": False,
                        "error": {
                            "code": "FORBIDDEN",
                            "message": "You can only delete your own agents",
                        },
                    }
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
                node_runtime.agent_route_registry.remove(agent_id)
                return {"success": True, "data": payload.get("result")}
            # Try local first
            try:
                result = agent_manager.delete_agent(agent_id)
                node_runtime.agent_route_registry.remove(agent_id)
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
                        nid,
                        AGENT_DELETE_REQUEST,
                        {"agent_id": agent_id},
                        timeout=10.0,
                    )
                    payload = response.get("payload") or {}
                    if payload.get("success"):
                        node_runtime.agent_route_registry.remove(agent_id)
                        return {"success": True, "data": payload.get("result")}
                except Exception as e:
                    save_exception(
                        e,
                        module="jarvis_web_gateway.app",
                        function="_reload_model_groups_config",
                    )
                    pass
            return {
                "success": False,
                "error": {
                    "code": "AGENT_NOT_FOUND",
                    "message": f"Agent not found: {agent_id}",
                },
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
                            "message": error.get(
                                "message", "Remote session list failed"
                            ),
                        },
                    }
                body = payload.get("body") or "{}"
                return json.loads(body)  # type: ignore[no-any-return]

            agent_info = agent_manager.get_agent(agent_id)
            if agent_info is None:
                return {
                    "success": False,
                    "error": {"code": "AGENT_NOT_FOUND", "message": "Agent not found"},
                }

            # 代理到 Agent 进程的 /sessions 接口
            import httpx

            async with httpx.AsyncClient() as client:
                http_response = await client.get(
                    f"http://127.0.0.1:{agent_info.port}/sessions"
                )
                return http_response.json()  # type: ignore[no-any-return]
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
                            "message": error.get(
                                "message", "Remote session restore failed"
                            ),
                        },
                    }
                body = payload.get("body") or "{}"
                return json.loads(body)  # type: ignore[no-any-return]

            agent_info = agent_manager.get_agent(agent_id)
            if agent_info is None:
                return {
                    "success": False,
                    "error": {"code": "AGENT_NOT_FOUND", "message": "Agent not found"},
                }

            # 代理到 Agent 进程的 /sessions 接口
            import httpx

            async with httpx.AsyncClient() as client:
                http_response = await client.post(
                    f"http://127.0.0.1:{agent_info.port}/sessions", json=request
                )
                return http_response.json()  # type: ignore[no-any-return]
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
                            "message": error.get(
                                "message", "Remote completions failed"
                            ),
                        },
                    }
                body = payload.get("body") or "{}"
                return json.loads(body)  # type: ignore[no-any-return]

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
    async def search_completions(
        agent_id: str, query: str = "", node_id: str = ""
    ) -> Dict[str, Any]:
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
                            "message": error.get(
                                "message", "Remote completion search failed"
                            ),
                        },
                    }
                body = payload.get("body") or "{}"
                return cast(Dict[str, Any], json.loads(body))

            import subprocess
            from fuzzywuzzy import process
            from jarvis.jarvis_utils.utils import decode_output

            # 获取 Agent 的工作目录
            agent = agent_manager.get_agent(agent_id)
            if not agent:
                return {
                    "success": False,
                    "error": {"code": "AGENT_NOT_FOUND", "message": "Agent not found"},
                }
            working_dir = agent.working_dir
            # 获取 git 文件列表（显式指定 cwd，避免 os.chdir 进程级竞态导致读到他 agent 目录）
            result = subprocess.run(
                ["git", "ls-files"],
                cwd=working_dir,
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

            # 使用 fzf 进行模糊搜索
            search_results = []
            if query and files:
                import shutil

                if shutil.which("fzf"):
                    # fzf 过滤模式 - 按相关性排序
                    try:
                        proc = subprocess.run(
                            ["fzf", "-f", query],
                            input="\n".join(files).encode("utf-8"),
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                        )
                        if proc.returncode == 0:
                            matched = (
                                decode_output(proc.stdout).strip().split("\n")[:300]
                            )
                            for path in matched:
                                if path:
                                    search_results.append(
                                        {
                                            "type": "file",
                                            "value": path,
                                            "display": path,
                                            "description": "File",
                                        }
                                    )
                    except Exception as e:
                        save_exception(
                            e,
                            module="jarvis_web_gateway.app",
                            function="_reload_model_groups_config",
                        )
                        pass

                # 回退到 fuzzywuzzy
                if not search_results:
                    scored_items = process.extract(
                        query,
                        files,
                        limit=300,
                    )
                    scored_items = [
                        (item[0], item[1]) for item in scored_items if item[1] > 10
                    ]
                    for path, score in scored_items:
                        search_results.append(
                            {
                                "type": "file",
                                "value": path,
                                "display": f"{path} ({score}%)"
                                if score < 100
                                else path,
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
                            "message": error.get(
                                "message", "Remote global search failed"
                            ),
                        },
                    }
                body = payload.get("body") or "{}"
                return cast(Dict[str, Any], json.loads(body))

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
        owner_id = action_params.get("owner_id")

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
                "owner_id": owner_id,
            },
        }

        def _create_agent_callback() -> None:
            auth_token = os.environ.get("JARVIS_AUTH_TOKEN")
            proxy_node = action_params.get("proxy_node")
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
                proxy_node=proxy_node,
                owner_id=owner_id,
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
        user_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_method = str(method or "GET").upper()
        normalized_path = "/" + str(path or "").lstrip("/")
        if normalized_path.startswith("/api/"):
            normalized_path = "/" + normalized_path[len("/api/") :].lstrip("/")

        # 构造模拟Request，传递user_info给需要request参数的API函数
        class _MockRequest:
            pass

        _mock_req = _MockRequest()
        _mock_req.state = type("state", (), {"user_info": user_info})()
        # 若无user_info，尝试从headers解析JWT
        if user_info is None:
            auth_header = headers.get("authorization", headers.get("Authorization", ""))
            if auth_header and auth_header.startswith("Bearer "):
                try:
                    from jarvis.jarvis_web_gateway.jwt_utils import verify_jwt_token

                    token = auth_header[7:]
                    token_payload = verify_jwt_token(token)
                    if token_payload:
                        _mock_req.state.user_info = token_payload
                except Exception:
                    pass

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
        elif normalized_method == "POST" and normalized_path == "/upload":
            result = await _handle_file_upload(payload)
        elif normalized_path.startswith("/data/"):
            from jarvis.jarvis_web_gateway.data_storage import (
                save_data,
                load_data,
                delete_data,
            )

            key = normalized_path[len("/data/") :]
            if normalized_method == "POST":
                # 如果 payload 包含 data 字段，则提取 data 字段的值进行存储
                data_to_save = payload.get("data", payload)
                success, error = save_data(key, data_to_save)
                if success:
                    result = {"success": True, "message": "Data saved successfully"}
                else:
                    result = {"success": False, "error": error}
            elif normalized_method == "GET":
                success, data, error = load_data(key)
                if success:
                    result = {"success": True, "data": data}
                else:
                    result = {"success": False, "error": error}
            elif normalized_method == "DELETE":
                success, error = delete_data(key)
                if success:
                    result = {"success": True, "message": "Data deleted successfully"}
                else:
                    result = {"success": False, "error": error}
            else:
                result = {"success": False, "error": "Method not allowed"}
        elif normalized_method == "GET" and normalized_path == "/node/status":
            result = await get_node_status()
        elif normalized_method == "POST" and normalized_path == "/service/restart":
            result = await restart_service(payload, _mock_req)
        elif normalized_method == "GET" and normalized_path == "/agents":
            result = await get_agents(_mock_req)
        elif normalized_method == "POST" and normalized_path == "/agents":
            result = await create_agent(payload, _mock_req)
        elif normalized_path.startswith("/agents/") and normalized_path.endswith(
            "/sessions"
        ):
            agent_id = normalized_path[len("/agents/") : -len("/sessions")].strip("/")
            if normalized_method == "GET":
                result = await list_agent_sessions(
                    agent_id, str(payload.get("node_id") or "")
                )
            elif normalized_method == "POST":
                result = await restore_agent_session(agent_id, payload)
            else:
                result = {
                    "success": False,
                    "error": {
                        "code": "METHOD_NOT_ALLOWED",
                        "message": "Unsupported method",
                    },
                }
        elif (
            normalized_path.startswith("/agents/")
            and normalized_path.endswith("/access")
            and normalized_method == "PUT"
        ):
            agent_id = normalized_path[len("/agents/") : -len("/access")].strip("/")
            result = await update_agent_access(agent_id, payload, _mock_req)
        elif (
            normalized_path.startswith("/agents/")
            and normalized_path.endswith("/stop")
            and normalized_method == "DELETE"
        ):
            agent_id = normalized_path[len("/agents/") : -len("/stop")].strip("/")
            result = await stop_agent(agent_id, _mock_req)
        elif normalized_path.startswith("/completions/") and normalized_path.endswith(
            "/search"
        ):
            agent_id = normalized_path[len("/completions/") : -len("/search")].strip(
                "/"
            )
            result = await search_completions(
                agent_id,
                query=str(payload.get("query") or ""),
                node_id=str(payload.get("node_id") or ""),
            )
        elif normalized_path.startswith("/completions/"):
            agent_id = normalized_path[len("/completions/") :].strip("/")
            result = await get_completions(agent_id, str(payload.get("node_id") or ""))
        elif (
            normalized_path.startswith("/global-search/")
            and normalized_method == "POST"
        ):
            agent_id = normalized_path[len("/global-search/") :].strip("/")
            result = await global_search(agent_id, payload)
        elif normalized_method == "GET" and normalized_path == "/model-groups":
            result = await get_model_groups()
        elif normalized_path.startswith("/agents/") and "/" not in normalized_path[
            len("/agents/") :
        ].strip("/"):
            agent_id = normalized_path[len("/agents/") :].strip("/")
            if normalized_method == "DELETE":
                result = await delete_agent(
                    agent_id, _mock_req, str(payload.get("node_id") or "")
                )
            elif normalized_method == "PATCH":
                result = await patch_agent(agent_id, payload, _mock_req)
            else:
                result = {
                    "success": False,
                    "error": {
                        "code": "METHOD_NOT_ALLOWED",
                        "message": "Unsupported method",
                    },
                }
        elif normalized_path.startswith("/http_proxy/"):
            # 远程节点 HTTP 代理：转发请求到外部 API
            # 路径格式：/http_proxy/{target_url}
            target_url = normalized_path[len("/http_proxy/") :]
            logger.info(
                f"[REMOTE HTTP PROXY] 收到代理请求：target_url={target_url}, method={normalized_method}, query={query}"
            )
            if not target_url.startswith(("http://", "https://")):
                logger.error(f"[REMOTE HTTP PROXY] URL 格式错误：{target_url}")
                return {
                    "success": False,
                    "status_code": 400,
                    "headers": {"content-type": "application/json"},
                    "body": json.dumps(
                        {"error": "URL must start with http:// or https://"}
                    ),
                }
            if query:
                target_url = f"{target_url}?{query}"
            logger.info(f"[REMOTE HTTP PROXY] 发起请求：{target_url}")
            try:
                proxy_headers = {
                    k: str(v) for k, v in headers.items() if k.lower() != "host"
                }
                async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                    response = await client.request(
                        method=normalized_method,
                        url=target_url,
                        headers=proxy_headers,
                        content=body,
                    )
                logger.info(f"[REMOTE HTTP PROXY] 响应状态码：{response.status_code}")
                logger.info(f"[REMOTE HTTP PROXY] 响应头：{dict(response.headers)}")
                # 记录响应体前 500 字符用于调试
                response_text = response.text
                logger.info(
                    f"[REMOTE HTTP PROXY] 响应体 (前 500 字符): {response_text[:500] if response_text else '空'}"
                )
                excluded_headers = {
                    "content-encoding",
                    "content-length",
                    "transfer-encoding",
                    "connection",
                }
                response_headers = {
                    k: v
                    for k, v in response.headers.items()
                    if k.lower() not in excluded_headers
                }
                result = {
                    "success": True,
                    "status_code": response.status_code,
                    "headers": response_headers,
                    "body": response.text,
                }
            except httpx.TimeoutException:
                result = {
                    "success": False,
                    "status_code": 504,
                    "headers": {"content-type": "application/json"},
                    "body": json.dumps({"error": "Request timeout"}),
                }
            except httpx.RequestError as e:
                logger.error(f"[REMOTE HTTP PROXY] Request error: {e}")
                result = {
                    "success": False,
                    "status_code": 502,
                    "headers": {"content-type": "application/json"},
                    "body": json.dumps({"error": f"Request failed: {str(e)}"}),
                }
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

    @app.post("/api/data/{key}", dependencies=[Depends(verify_token)])
    async def save_data_api(key: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """保存数据到存储。"""
        from jarvis.jarvis_web_gateway.data_storage import save_data

        success, error = save_data(key, request)
        if success:
            return {"success": True, "message": "Data saved successfully"}
        else:
            return {"success": False, "error": error}

    @app.get("/api/data/{key}", dependencies=[Depends(verify_token)])
    async def load_data_api(key: str) -> Dict[str, Any]:
        """从存储中读取数据。"""
        from jarvis.jarvis_web_gateway.data_storage import load_data

        success, data, error = load_data(key)
        if success:
            return {"success": True, "data": data}
        else:
            return {"success": False, "error": error}

    @app.delete("/api/data/{key}", dependencies=[Depends(verify_token)])
    async def delete_data_api(key: str) -> Dict[str, Any]:
        """从存储中删除数据。"""
        from jarvis.jarvis_web_gateway.data_storage import delete_data

        success, error = delete_data(key)
        if success:
            return {"success": True, "message": "Data deleted successfully"}
        else:
            return {"success": False, "error": error}

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

    # ==================== 群组管理 API ====================

    # HTTP API：创建群组
    @app.post("/api/groups", dependencies=[Depends(verify_token)])
    async def create_group(request: Request) -> Dict[str, Any]:
        """创建群组。

        Args:
            request: 请求体，包含 name（群组名称）

        Returns:
            {"success": True, "data": {"group_id": str, "name": str, "members": list}}
        """
        try:
            body = await request.json()
            name = body.get("name")
            if not name:
                return {
                    "success": False,
                    "error": {"code": "INVALID_PARAMS", "message": "name is required"},
                }

            # 生成群组 ID
            group_id = str(uuid.uuid4())[:8]

            # 创建群组
            groups[group_id] = {
                "name": name,
                "members": set(),
            }

            return {
                "success": True,
                "data": {
                    "group_id": group_id,
                    "name": name,
                    "members": [],
                },
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：查询所有群组
    @app.get("/api/groups", dependencies=[Depends(verify_token)])
    async def list_groups() -> Dict[str, Any]:
        """查询所有群组。

        Returns:
            {"success": True, "data": [{"group_id": str, "name": str, "members": list}]}
        """
        try:
            group_list = [
                {
                    "group_id": group_id,
                    "name": info["name"],
                    "members": list(info["members"]),
                }
                for group_id, info in groups.items()
            ]
            return {"success": True, "data": group_list}
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：查询群组详情
    @app.get("/api/groups/{group_id}", dependencies=[Depends(verify_token)])
    async def get_group(group_id: str) -> Dict[str, Any]:
        """查询群组详情。

        Args:
            group_id: 群组 ID

        Returns:
            {"success": True, "data": {"group_id": str, "name": str, "members": list}}
        """
        try:
            if group_id not in groups:
                return {
                    "success": False,
                    "error": {"code": "NOT_FOUND", "message": "Group not found"},
                }

            info = groups[group_id]
            return {
                "success": True,
                "data": {
                    "group_id": group_id,
                    "name": info["name"],
                    "members": list(info["members"]),
                },
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：加入群组
    @app.post("/api/groups/{group_id}/join", dependencies=[Depends(verify_token)])
    async def join_group(group_id: str, request: Request) -> Dict[str, Any]:
        """加入群组。

        Args:
            group_id: 群组 ID
            request: 请求体，包含 agent_id

        Returns:
            {"success": True}
        """
        try:
            if group_id not in groups:
                return {
                    "success": False,
                    "error": {"code": "NOT_FOUND", "message": "Group not found"},
                }

            try:
                body = await request.json()
            except Exception:
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_PARAMS",
                        "message": "Invalid JSON body",
                    },
                }

            agent_id = body.get("agent_id") if body else None
            if not agent_id:
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_PARAMS",
                        "message": "agent_id is required",
                    },
                }

            groups[group_id]["members"].add(agent_id)
            return {"success": True}
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：退出群组
    @app.post("/api/groups/{group_id}/leave", dependencies=[Depends(verify_token)])
    async def leave_group(group_id: str, request: Request) -> Dict[str, Any]:
        """退出群组。

        Args:
            group_id: 群组 ID
            request: 请求体，包含 agent_id

        Returns:
            {"success": True}
        """
        try:
            if group_id not in groups:
                return {
                    "success": False,
                    "error": {"code": "NOT_FOUND", "message": "Group not found"},
                }

            try:
                body = await request.json()
            except Exception:
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_PARAMS",
                        "message": "Invalid JSON body",
                    },
                }

            agent_id = body.get("agent_id") if body else None
            if not agent_id:
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_PARAMS",
                        "message": "agent_id is required",
                    },
                }

            groups[group_id]["members"].discard(agent_id)
            return {"success": True}
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：发送群组消息
    @app.post("/api/groups/{group_id}/message", dependencies=[Depends(verify_token)])
    async def send_group_message(group_id: str, request: Request) -> Dict[str, Any]:
        """发送群组消息。

        向群组所有成员发送消息（不包括发送者）。

        Args:
            group_id: 群组 ID
            request: 请求体，包含 sender_id 和 content

        Returns:
            {"success": True, "data": {"sent_to": list, "failed": list}}
        """
        try:
            if group_id not in groups:
                return {
                    "success": False,
                    "error": {"code": "NOT_FOUND", "message": "Group not found"},
                }

            body = await request.json()
            sender_id = body.get("sender_id")
            content = body.get("content")
            if not sender_id or not content:
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_PARAMS",
                        "message": "sender_id and content are required",
                    },
                }

            # 获取群组成员（不包括发送者）
            members = groups[group_id]["members"]
            recipients = [m for m in members if m != sender_id]

            if not recipients:
                return {
                    "success": True,
                    "data": {"sent_to": [], "failed": [], "message": "No recipients"},
                }

            # 向每个成员发送消息
            sent_to = []
            failed = []
            for agent_id in recipients:
                try:
                    # 调用 agent 的 /message 接口
                    agent_info = agent_manager.get_agent(agent_id)
                    if not agent_info or not agent_info.port:
                        failed.append(
                            {"agent_id": agent_id, "error": "Agent not found"}
                        )
                        continue

                    port = agent_info.port
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(
                            f"http://127.0.0.1:{port}/message",
                            json={
                                "sender_id": sender_id,
                                "content": content,
                                "group_id": group_id,
                                "group_name": groups[group_id]["name"],
                                "message_type": "group_message",
                            },
                            timeout=5.0,
                        )
                        if resp.status_code == 200:
                            sent_to.append(agent_id)
                        else:
                            failed.append(
                                {
                                    "agent_id": agent_id,
                                    "error": f"HTTP {resp.status_code}",
                                }
                            )
                except Exception as e:
                    failed.append({"agent_id": agent_id, "error": str(e)})

            return {
                "success": True,
                "data": {"sent_to": sent_to, "failed": failed},
            }
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

    uvicorn.run(create_app(node_config=node_config, port=port), host=host, port=port)


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
                await websocket.send_json(message)
            except Exception as e:
                save_exception(e, module="jarvis_web_gateway.app", function="_sender")
                pass

        try:
            asyncio.run_coroutine_threadsafe(_send(), loop)
        except Exception as e:
            save_exception(e, module="jarvis_web_gateway.app", function="_sender")
            pass

    return _sender


async def _handle_file_upload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """处理文件上传请求。

    Args:
        payload: 包含文件数据的字典
            - agent_id: Agent ID
            - file_name: 文件名
            - file_data: Base64 编码的文件数据
            - target_dir: 目标目录 (默认为 Jarvis 数据目录下的 uploads 子目录)

    Returns:
        处理结果字典
    """
    import base64
    import uuid
    import os

    try:
        from jarvis.jarvis_utils.config import get_data_dir

        file_name = payload.get("file_name")
        file_data = payload.get("file_data")
        target_dir = payload.get("target_dir", "")

        # 如果 target_dir 为空或未指定，使用 Jarvis 数据目录下的 uploads 子目录
        if not target_dir:
            target_dir = os.path.join(get_data_dir(), "uploads")

        if not file_data:
            return {"success": False, "error": "Missing file data"}

        # 解析 Base64 数据
        if "," in file_data:
            header, data = file_data.split(",", 1)
            # 尝试从 header 提取扩展名
            try:
                mime_type = header.split(":")[1].split(";")[0]
                ext = mime_type.split("/")[1]
            except Exception:
                ext = "png"
        else:
            data = file_data
            ext = "png"

        # 解码
        try:
            file_bytes = base64.b64decode(data)
        except Exception as e:
            return {"success": False, "error": f"Invalid base64 data: {str(e)}"}

        # 验证文件大小 (限制 20MB)
        if len(file_bytes) > 20 * 1024 * 1024:
            return {"success": False, "error": "File too large (>20MB)"}

        # 生成唯一文件名
        # 如果 file_name 已有扩展名，则移除它，避免重复
        base_name = os.path.splitext(file_name or "image")[0] if file_name else "image"
        unique_name = f"{uuid.uuid4().hex[:8]}_{base_name}.{ext}"
        file_path = os.path.join(target_dir, unique_name)

        # 确保目录存在
        os.makedirs(target_dir, exist_ok=True)

        # 写入文件
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        return {
            "success": True,
            "data": {"file_path": file_path, "file_size": len(file_bytes)},
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def _send_error(websocket: WebSocket, code: str, message: str) -> None:
    error_msg = {"type": "error", "payload": {"code": code, "message": message}}
    await websocket.send_json(error_msg)
