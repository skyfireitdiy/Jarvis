# -*- coding: utf-8 -*-
"""Node 主子节点连接与基础状态管理。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import random
import uuid
from typing import Any, Dict, Optional

import websockets
from fastapi import WebSocket

from .agent_manager import AgentManager
from .node_protocol import (
    AGENT_CREATE_REQUEST,
    AGENT_CREATE_RESPONSE,
    AGENT_HTTP_REQUEST,
    AGENT_HTTP_RESPONSE,
    NODE_HTTP_PROXY_REQUEST,
    NODE_HTTP_PROXY_RESPONSE,
    AGENT_LIST_REQUEST,
    AGENT_LIST_RESPONSE,
    AGENT_STOP_REQUEST,
    AGENT_STOP_RESPONSE,
    AGENT_DELETE_REQUEST,
    AGENT_DELETE_RESPONSE,
    AGENT_WS_CLOSE_REQUEST,
    AGENT_WS_CLOSE_RESPONSE,
    AGENT_WS_OPEN_REQUEST,
    AGENT_WS_OPEN_RESPONSE,
    AGENT_WS_RECV_REQUEST,
    AGENT_WS_RECV_RESPONSE,
    AGENT_WS_REQUEST,
    AGENT_WS_RESPONSE,
    AGENT_WS_SEND_REQUEST,
    AGENT_WS_SEND_RESPONSE,
    DIRECTORY_LIST_REQUEST,
    DIRECTORY_LIST_RESPONSE,
    NODE_TERMINAL_REQUEST,
    NODE_TERMINAL_RESPONSE,
    NODE_TERMINAL_OUTPUT,
    NODE_AUTH,
    NODE_AUTH_RESULT,
    NODE_HEARTBEAT,
    build_error_message,
    build_node_message,
)
from .node_runtime import AgentRouteInfo, NodeInfo, NodeRuntime

logger = logging.getLogger(__name__)

CHILD_HEARTBEAT_INTERVAL_SECONDS = 10
CHILD_RECONNECT_MIN_SECONDS = 5
CHILD_RECONNECT_MAX_SECONDS = 10


class NodeConnectionManager:
    def __init__(
        self,
        node_runtime: NodeRuntime,
        agent_manager: AgentManager,
        agent_proxy_manager: Any,
        node_http_dispatcher: Optional[Any] = None,
        router: Optional[Any] = None,
        terminal_session_manager: Optional[Any] = None,
    ) -> None:
        self._node_runtime = node_runtime
        self._agent_manager = agent_manager
        self._agent_proxy_manager = agent_proxy_manager
        self._node_http_dispatcher = node_http_dispatcher
        self._router = router
        self._terminal_session_manager = terminal_session_manager
        self._connections: Dict[str, WebSocket] = {}
        self._connection_to_node: Dict[str, str] = {}
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._agent_ws_sessions: Dict[str, Any] = {}

    async def handle_node_websocket(self, websocket: WebSocket) -> None:
        await websocket.accept()
        connection_id = str(uuid.uuid4())
        try:
            message = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        except Exception:
            await websocket.send_json(
                build_error_message(
                    "NODE_AUTH_REQUIRED",
                    "first message must be node_auth",
                )
            )
            await websocket.close(code=4401)
            return

        if not isinstance(message, dict) or message.get("type") != NODE_AUTH:
            await websocket.send_json(
                build_error_message(
                    "INVALID_NODE_MESSAGE", "first message must be node_auth"
                )
            )
            await websocket.close(code=4401)
            return

        payload = message.get("payload") or {}
        node_id = str(payload.get("node_id") or "").strip()
        secret = str(payload.get("secret") or "").strip()
        if not node_id or not secret:
            await websocket.send_json(
                build_error_message(
                    "NODE_AUTH_FAILED", "node_id and secret are required"
                )
            )
            await websocket.close(code=4401)
            return

        expected_secret = (self._node_runtime.config.node_secret or "").strip()
        if not expected_secret or secret != expected_secret:
            await websocket.send_json(
                build_error_message("NODE_AUTH_FAILED", "invalid node credentials")
            )
            await websocket.close(code=4401)
            return

        self._connections[node_id] = websocket
        self._connection_to_node[connection_id] = node_id
        self._node_runtime.node_registry.upsert(
            NodeInfo(
                node_id=node_id,
                status="online",
                connection_id=connection_id,
                capabilities=payload.get("capabilities") or {},
                metadata={},
            )
        )
        await websocket.send_json(
            build_node_message(
                "node_auth_result",
                {
                    "success": True,
                    "node_id": node_id,
                    "token": os.environ.get("JARVIS_AUTH_TOKEN"),
                    "heartbeat_interval": 10,
                },
                request_id=message.get("request_id"),
            )
        )

        try:
            while True:
                next_message = await websocket.receive_json()
                if not isinstance(next_message, dict):
                    continue
                message_type = next_message.get("type")
                request_id = next_message.get("request_id")
                logger.info(
                    "[NODE] recv message node_id=%s type=%s request_id=%s",
                    node_id,
                    message_type,
                    request_id,
                )
                if message_type == NODE_HEARTBEAT:
                    self._node_runtime.node_registry.mark_heartbeat(node_id)
                    continue
                if (
                    message_type
                    in (
                        AGENT_CREATE_RESPONSE,
                        AGENT_HTTP_RESPONSE,
                        NODE_HTTP_PROXY_RESPONSE,
                        AGENT_LIST_RESPONSE,
                        AGENT_STOP_RESPONSE,
                        AGENT_DELETE_RESPONSE,
                        AGENT_WS_RESPONSE,
                        AGENT_WS_OPEN_RESPONSE,
                        AGENT_WS_SEND_RESPONSE,
                        AGENT_WS_RECV_RESPONSE,
                        AGENT_WS_CLOSE_RESPONSE,
                        DIRECTORY_LIST_RESPONSE,
                        NODE_TERMINAL_RESPONSE,
                    )
                    and request_id
                ):
                    future = self._pending_requests.pop(request_id, None)
                    if future is not None and not future.done():
                        future.set_result(next_message)
                    continue
                if message_type == NODE_TERMINAL_OUTPUT:
                    # child 端推送的终端输出，转发给前端
                    terminal_payload = (next_message.get("payload") or {})
                    output_session_id = terminal_payload.get("session_id") or "default"
                    output_message = terminal_payload.get("message")
                    if output_message and self._router:
                        self._router.publish(output_message, session_id=output_session_id)
                    continue
                if message_type == AGENT_CREATE_REQUEST:
                    response = self._handle_agent_create_request(next_message, node_id)
                    await websocket.send_json(response)
                    continue
                if message_type == AGENT_HTTP_REQUEST:
                    response = await self._handle_agent_http_request(next_message)
                    await websocket.send_json(response)
                    continue
                if message_type == NODE_HTTP_PROXY_REQUEST:
                    response = await self._handle_node_http_proxy_request(next_message)
                    await websocket.send_json(response)
                    continue
                if message_type == AGENT_LIST_REQUEST:
                    response = self._handle_agent_list_request(next_message)
                    await websocket.send_json(response)
                    continue
                if message_type == AGENT_STOP_REQUEST:
                    response = self._handle_agent_stop_request(next_message)
                    await websocket.send_json(response)
                    continue
                if message_type == AGENT_DELETE_REQUEST:
                    response = self._handle_agent_delete_request(next_message)
                    await websocket.send_json(response)
                    continue
                if message_type == AGENT_WS_REQUEST:
                    response = await self._handle_agent_ws_request(next_message)
                    await websocket.send_json(response)
                    continue
                if message_type == AGENT_WS_OPEN_REQUEST:
                    response = await self._handle_agent_ws_open_request(next_message)
                    await websocket.send_json(response)
                    continue
                if message_type == AGENT_WS_SEND_REQUEST:
                    response = await self._handle_agent_ws_send_request(next_message)
                    await websocket.send_json(response)
                    continue
                if message_type == AGENT_WS_RECV_REQUEST:
                    response = await self._handle_agent_ws_recv_request(next_message)
                    await websocket.send_json(response)
                    continue
                if message_type == AGENT_WS_CLOSE_REQUEST:
                    response = await self._handle_agent_ws_close_request(next_message)
                    await websocket.send_json(response)
                    continue
                if message_type == DIRECTORY_LIST_REQUEST:
                    logger.info(
                        "[NODE] handling directory list request node_id=%s request_id=%s",
                        node_id,
                        request_id,
                    )
                    response = self._handle_directory_list_request(next_message)
                    await websocket.send_json(response)
                    logger.info(
                        "[NODE] sent directory list response node_id=%s request_id=%s",
                        node_id,
                        request_id,
                    )
                    continue
                logger.warning(
                    "[NODE] unhandled message node_id=%s type=%s request_id=%s",
                    node_id,
                    message_type,
                    request_id,
                )
        except Exception:
            logger.info("[NODE] node disconnected: %s", node_id)
        finally:
            self._node_runtime.node_registry.mark_offline(node_id)
            self._connections.pop(node_id, None)
            self._connection_to_node.pop(connection_id, None)

    def get_node_connection(self, node_id: str) -> Optional[WebSocket]:
        return self._connections.get(node_id)

    async def send_request_to_node(
        self,
        node_id: str,
        message_type: str,
        payload: Dict[str, Any],
        timeout: float = 60.0,
    ) -> Dict[str, Any]:
        websocket = self._connections.get(node_id)
        if websocket is None:
            raise RuntimeError(f"node connection not found: {node_id}")
        request_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending_requests[request_id] = future
        try:
            logger.info(
                "[NODE] send request node_id=%s type=%s request_id=%s",
                node_id,
                message_type,
                request_id,
            )
            await websocket.send_json(
                build_node_message(message_type, payload, request_id=request_id)
            )
            response = await asyncio.wait_for(future, timeout=timeout)
            logger.info(
                "[NODE] received response node_id=%s type=%s request_id=%s",
                node_id,
                response.get("type") if isinstance(response, dict) else None,
                request_id,
            )
            if not isinstance(response, dict):
                raise RuntimeError("invalid node response")
            return response
        finally:
            self._pending_requests.pop(request_id, None)

    def _handle_agent_create_request(
        self, message: Dict[str, Any], source_node_id: str
    ) -> Dict[str, Any]:
        payload = message.get("payload") or {}
        request_id = message.get("request_id")
        try:
            auth_token = os.environ.get("JARVIS_AUTH_TOKEN")
            agent_info = self._agent_manager.create_agent(
                auth_token=auth_token,
                agent_type=payload.get("agent_type"),
                working_dir=payload.get("working_dir"),
                name=payload.get("name"),
                llm_group=payload.get("llm_group", "default"),
                tool_group=payload.get("tool_group", "default"),
                config_file=payload.get("config_file"),
                task=payload.get("task"),
                additional_args=payload.get("additional_args"),
                worktree=bool(payload.get("worktree", False)),
                node_id=self._node_runtime.local_node_id,
            )
            self._node_runtime.agent_route_registry.register(
                AgentRouteInfo(
                    agent_id=agent_info["agent_id"],
                    node_id=agent_info.get("node_id", self._node_runtime.local_node_id),
                    status=agent_info.get("status", "running"),
                    working_dir=agent_info.get("working_dir"),
                    port=agent_info.get("port"),
                )
            )
            return build_node_message(
                AGENT_CREATE_RESPONSE,
                {
                    "success": True,
                    "agent_info": agent_info,
                    "source_node_id": source_node_id,
                },
                request_id=request_id,
            )
        except Exception as exc:
            return build_node_message(
                AGENT_CREATE_RESPONSE,
                {
                    "success": False,
                    "error": {
                        "code": "AGENT_CREATE_FAILED",
                        "message": str(exc),
                    },
                },
                request_id=request_id,
            )

    def _handle_agent_list_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        request_id = message.get("request_id")
        try:
            agents = self._agent_manager.get_agent_list()
            for agent in agents:
                agent["node_id"] = self._node_runtime.local_node_id
            return build_node_message(
                AGENT_LIST_RESPONSE,
                {"success": True, "agents": agents},
                request_id=request_id,
            )
        except Exception as exc:
            return build_node_message(
                AGENT_LIST_RESPONSE,
                {
                    "success": False,
                    "error": {"code": "AGENT_LIST_FAILED", "message": str(exc)},
                },
                request_id=request_id,
            )

    async def _handle_node_http_proxy_request(
        self, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        payload = message.get("payload") or {}
        request_id = message.get("request_id")
        try:
            if self._node_http_dispatcher is None:
                raise RuntimeError("node http dispatcher is not configured")

            result = await self._node_http_dispatcher(
                method=str(payload.get("method") or "GET"),
                path=str(payload.get("path") or ""),
                query=str(payload.get("query") or ""),
                headers=payload.get("headers") or {},
                body=str(payload.get("body") or ""),
            )
            return build_node_message(
                NODE_HTTP_PROXY_RESPONSE,
                result,
                request_id=request_id,
            )
        except Exception as exc:
            return build_node_message(
                NODE_HTTP_PROXY_RESPONSE,
                {
                    "success": False,
                    "error": {"code": "NODE_HTTP_PROXY_FAILED", "message": str(exc)},
                },
                request_id=request_id,
            )

    def _handle_agent_stop_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        payload = message.get("payload") or {}
        request_id = message.get("request_id")
        agent_id = str(payload.get("agent_id") or "").strip()
        try:
            result = self._agent_manager.stop_agent(agent_id)
            return build_node_message(
                AGENT_STOP_RESPONSE,
                {"success": True, "result": result},
                request_id=request_id,
            )
        except KeyError as exc:
            return build_node_message(
                AGENT_STOP_RESPONSE,
                {
                    "success": False,
                    "error": {"code": "AGENT_NOT_FOUND", "message": str(exc)},
                },
                request_id=request_id,
            )
        except Exception as exc:
            return build_node_message(
                AGENT_STOP_RESPONSE,
                {
                    "success": False,
                    "error": {"code": "AGENT_STOP_FAILED", "message": str(exc)},
                },
                request_id=request_id,
            )

    def _handle_agent_delete_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        payload = message.get("payload") or {}
        request_id = message.get("request_id")
        agent_id = str(payload.get("agent_id") or "").strip()
        try:
            result = self._agent_manager.delete_agent(agent_id)
            return build_node_message(
                AGENT_DELETE_RESPONSE,
                {"success": True, "result": result},
                request_id=request_id,
            )
        except KeyError as exc:
            return build_node_message(
                AGENT_DELETE_RESPONSE,
                {
                    "success": False,
                    "error": {"code": "AGENT_NOT_FOUND", "message": str(exc)},
                },
                request_id=request_id,
            )
        except Exception as exc:
            return build_node_message(
                AGENT_DELETE_RESPONSE,
                {
                    "success": False,
                    "error": {"code": "AGENT_DELETE_FAILED", "message": str(exc)},
                },
                request_id=request_id,
            )

    async def _handle_agent_http_request(
        self, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        payload = message.get("payload") or {}
        request_id = message.get("request_id")
        try:
            from fastapi import Request
            from starlette.requests import Request as StarletteRequest

            scope = {
                "type": "http",
                "method": payload.get("method", "GET"),
                "path": "/" + str(payload.get("path") or "").lstrip("/"),
                "query_string": str(payload.get("query") or "").encode("utf-8"),
                "headers": [
                    (str(k).lower().encode("utf-8"), str(v).encode("utf-8"))
                    for k, v in (payload.get("headers") or {}).items()
                ],
                "client": ("127.0.0.1", 0),
                "server": ("127.0.0.1", 0),
                "scheme": "http",
            }
            body = str(payload.get("body") or "").encode("utf-8")

            async def receive() -> Dict[str, Any]:
                return {"type": "http.request", "body": body, "more_body": False}

            request = StarletteRequest(scope, receive)
            response = await self._agent_proxy_manager.proxy_http_request(
                request,
                str(payload.get("agent_id") or ""),
                str(payload.get("path") or ""),
            )
            response_body = (
                response.body.decode("utf-8", errors="replace") if response.body else ""
            )
            headers = {k: v for k, v in response.headers.items()}
            return build_node_message(
                AGENT_HTTP_RESPONSE,
                {
                    "success": True,
                    "status_code": response.status_code,
                    "headers": headers,
                    "body": response_body,
                },
                request_id=request_id,
            )
        except Exception as exc:
            return build_node_message(
                AGENT_HTTP_RESPONSE,
                {
                    "success": False,
                    "error": {
                        "code": "HTTP_PROXY_FAILED",
                        "message": str(exc),
                    },
                },
                request_id=request_id,
            )

    async def _handle_agent_ws_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        payload = message.get("payload") or {}
        request_id = message.get("request_id")
        try:
            agent_id = str(payload.get("agent_id") or "")
            ws_path = str(payload.get("path") or "ws")
            port = await self._agent_proxy_manager.get_agent_port(agent_id)
            agent_url = f"ws://127.0.0.1:{port}/ws"
            auth_token = os.environ.get("JARVIS_AUTH_TOKEN")
            subprotocols = ["jarvis-ws"]
            if auth_token:
                subprotocols.append(f"jarvis-token.{auth_token}")
            async with websockets.connect(
                agent_url,
                close_timeout=30,
                proxy=None,
                subprotocols=subprotocols,
            ) as agent_ws:
                for item in payload.get("messages") or []:
                    await agent_ws.send(str(item))
                collected: list[str] = []
                while True:
                    try:
                        reply = await asyncio.wait_for(agent_ws.recv(), timeout=0.5)
                        collected.append(
                            reply if isinstance(reply, str) else reply.decode()
                        )
                    except asyncio.TimeoutError:
                        break
            return build_node_message(
                AGENT_WS_RESPONSE,
                {
                    "success": True,
                    "messages": collected,
                    "path": ws_path,
                },
                request_id=request_id,
            )
        except Exception as exc:
            return build_node_message(
                AGENT_WS_RESPONSE,
                {
                    "success": False,
                    "error": {
                        "code": "WS_PROXY_FAILED",
                        "message": str(exc),
                    },
                },
                request_id=request_id,
            )

    async def _handle_agent_ws_open_request(
        self, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        payload = message.get("payload") or {}
        request_id = message.get("request_id")
        session_id = str(payload.get("session_id") or "").strip()
        agent_id = str(payload.get("agent_id") or "").strip()
        logger.info(
            "[NODE AGENT WS OPEN] request_id=%s agent_id=%s session_id=%s",
            request_id,
            agent_id,
            session_id,
        )
        try:
            if not session_id:
                raise ValueError("session_id is required")
            if not agent_id:
                raise ValueError("agent_id is required")
            port = await self._agent_proxy_manager.get_agent_port(agent_id)
            agent_url = f"ws://127.0.0.1:{port}/ws"
            auth_token = os.environ.get("JARVIS_AUTH_TOKEN")
            subprotocols = ["jarvis-ws"]
            if auth_token:
                subprotocols.append(f"jarvis-token.{auth_token}")
            logger.info(
                "[NODE AGENT WS OPEN] connecting agent_id=%s session_id=%s agent_url=%s subprotocol_count=%s",
                agent_id,
                session_id,
                agent_url,
                len(subprotocols),
            )
            agent_ws = await websockets.connect(
                agent_url,
                close_timeout=30,
                proxy=None,
                subprotocols=subprotocols,
            )
            self._agent_ws_sessions[session_id] = agent_ws
            logger.info(
                "[NODE AGENT WS OPEN] success agent_id=%s session_id=%s",
                agent_id,
                session_id,
            )
            return build_node_message(
                AGENT_WS_OPEN_RESPONSE,
                {"success": True, "session_id": session_id},
                request_id=request_id,
            )
        except Exception as exc:
            logger.error(
                "[NODE AGENT WS OPEN] failed request_id=%s agent_id=%s session_id=%s error=%s",
                request_id,
                agent_id,
                session_id,
                exc,
            )
            return build_node_message(
                AGENT_WS_OPEN_RESPONSE,
                {
                    "success": False,
                    "error": {"code": "WS_OPEN_FAILED", "message": str(exc)},
                },
                request_id=request_id,
            )

    async def _handle_agent_ws_send_request(
        self, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        payload = message.get("payload") or {}
        request_id = message.get("request_id")
        session_id = str(payload.get("session_id") or "").strip()
        logger.info(
            "[NODE AGENT WS SEND] request_id=%s session_id=%s message_count=%s",
            request_id,
            session_id,
            len(payload.get("messages") or []),
        )
        try:
            agent_ws = self._agent_ws_sessions.get(session_id)
            if agent_ws is None:
                raise RuntimeError(f"ws session not found: {session_id}")
            for item in payload.get("messages") or []:
                await agent_ws.send(str(item))
            return build_node_message(
                AGENT_WS_SEND_RESPONSE,
                {"success": True, "session_id": session_id},
                request_id=request_id,
            )
        except Exception as exc:
            logger.error(
                "[NODE AGENT WS SEND] failed request_id=%s session_id=%s error=%s",
                request_id,
                session_id,
                exc,
            )
            return build_node_message(
                AGENT_WS_SEND_RESPONSE,
                {
                    "success": False,
                    "error": {"code": "WS_SEND_FAILED", "message": str(exc)},
                },
                request_id=request_id,
            )

    async def _handle_agent_ws_recv_request(
        self, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        payload = message.get("payload") or {}
        request_id = message.get("request_id")
        session_id = str(payload.get("session_id") or "").strip()
        timeout = float(payload.get("timeout") or 0.5)
        try:
            agent_ws = self._agent_ws_sessions.get(session_id)
            if agent_ws is None:
                raise RuntimeError(f"ws session not found: {session_id}")
            messages: list[str] = []
            while True:
                try:
                    reply = await asyncio.wait_for(agent_ws.recv(), timeout=timeout)
                    messages.append(reply if isinstance(reply, str) else reply.decode())
                    timeout = 0.05
                except asyncio.TimeoutError:
                    break
            logger.info(
                "[NODE AGENT WS RECV] request_id=%s session_id=%s message_count=%s",
                request_id,
                session_id,
                len(messages),
            )
            return build_node_message(
                AGENT_WS_RECV_RESPONSE,
                {"success": True, "session_id": session_id, "messages": messages},
                request_id=request_id,
            )
        except Exception as exc:
            logger.error(
                "[NODE AGENT WS RECV] failed request_id=%s session_id=%s error=%s",
                request_id,
                session_id,
                exc,
            )
            return build_node_message(
                AGENT_WS_RECV_RESPONSE,
                {
                    "success": False,
                    "error": {"code": "WS_RECV_FAILED", "message": str(exc)},
                },
                request_id=request_id,
            )

    async def _handle_agent_ws_close_request(
        self, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        payload = message.get("payload") or {}
        request_id = message.get("request_id")
        session_id = str(payload.get("session_id") or "").strip()
        logger.info(
            "[NODE AGENT WS CLOSE] request_id=%s session_id=%s",
            request_id,
            session_id,
        )
        agent_ws = self._agent_ws_sessions.pop(session_id, None)
        try:
            if agent_ws is not None:
                await agent_ws.close()
            return build_node_message(
                AGENT_WS_CLOSE_RESPONSE,
                {"success": True, "session_id": session_id},
                request_id=request_id,
            )
        except Exception as exc:
            logger.error(
                "[NODE AGENT WS CLOSE] failed request_id=%s session_id=%s error=%s",
                request_id,
                session_id,
                exc,
            )
            return build_node_message(
                AGENT_WS_CLOSE_RESPONSE,
                {
                    "success": False,
                    "error": {"code": "WS_CLOSE_FAILED", "message": str(exc)},
                },
                request_id=request_id,
            )

    def _handle_directory_list_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        payload = message.get("payload") or {}
        request_id = message.get("request_id")
        raw_path = str(payload.get("path") or "").strip()
        logger.info(
            "[NODE] _handle_directory_list_request path=%s request_id=%s",
            raw_path,
            request_id,
        )
        try:
            if not raw_path or raw_path == "~":
                target_path = pathlib.Path.home()
            else:
                target_path = pathlib.Path(raw_path).expanduser()

            target_path = target_path.resolve()

            if not target_path.exists():
                return build_node_message(
                    DIRECTORY_LIST_RESPONSE,
                    {
                        "success": False,
                        "error": {
                            "code": "NOT_FOUND",
                            "message": f"Path does not exist: {raw_path}",
                        },
                    },
                    request_id=request_id,
                )

            if not target_path.is_dir():
                return build_node_message(
                    DIRECTORY_LIST_RESPONSE,
                    {
                        "success": False,
                        "error": {
                            "code": "NOT_A_DIRECTORY",
                            "message": f"Path is not a directory: {raw_path}",
                        },
                    },
                    request_id=request_id,
                )

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
                items.sort(key=lambda item: (item["type"] != "directory", item["name"]))
            except PermissionError:
                pass

            logger.info(
                "[NODE] directory list success path=%s resolved=%s item_count=%s request_id=%s",
                raw_path,
                target_path,
                len(items),
                request_id,
            )
            return build_node_message(
                DIRECTORY_LIST_RESPONSE,
                {
                    "success": True,
                    "data": {
                        "current_path": str(target_path),
                        "parent_path": parent_path,
                        "items": items,
                    },
                },
                request_id=request_id,
            )
        except PermissionError:
            logger.warning(
                "[NODE] directory list permission denied path=%s request_id=%s",
                raw_path,
                request_id,
            )
            return build_node_message(
                DIRECTORY_LIST_RESPONSE,
                {
                    "success": False,
                    "error": {
                        "code": "PERMISSION_DENIED",
                        "message": "Permission denied",
                    },
                },
                request_id=request_id,
            )
        except Exception as exc:
            logger.exception(
                "[NODE] directory list failed path=%s request_id=%s error=%r",
                raw_path,
                request_id,
                exc,
            )
            return build_node_message(
                DIRECTORY_LIST_RESPONSE,
                {
                    "success": False,
                    "error": {
                        "code": "DIRECTORY_LIST_FAILED",
                        "message": str(exc),
                    },
                },
                request_id=request_id,
            )


class ChildNodeClient:
    def __init__(
        self,
        node_runtime: NodeRuntime,
        agent_manager: AgentManager,
        agent_proxy_manager: Any,
        node_connection_manager: NodeConnectionManager,
    ) -> None:
        self._node_runtime = node_runtime
        self._agent_manager = agent_manager
        self._agent_proxy_manager = agent_proxy_manager
        self._node_connection_manager = node_connection_manager
        self._ws: Optional[Any] = None
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def _run(self) -> None:
        config = self._node_runtime.config
        if not config.master_url:
            self._node_runtime.token_sync_state.mark_failed("master_url is missing")
            self._node_runtime.mark_degraded()
            return

        master_url = config.master_url.rstrip("/")
        if master_url.startswith("https://"):
            ws_url = "wss://" + master_url[len("https://") :]
        elif master_url.startswith("http://"):
            ws_url = "ws://" + master_url[len("http://") :]
        else:
            ws_url = master_url
        ws_url = ws_url.rstrip("/") + "/ws/node"

        while True:
            try:
                await self._connect_once(ws_url)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("[NODE] child node connection failed: %s", exc)
                self._node_runtime.token_sync_state.mark_failed(
                    str(exc), source_node_id="master"
                )
                self._node_runtime.mark_degraded()
            finally:
                if self._ws is not None:
                    try:
                        await self._ws.close()
                    except Exception:
                        pass
                    self._ws = None

            reconnect_delay = random.uniform(
                CHILD_RECONNECT_MIN_SECONDS,
                CHILD_RECONNECT_MAX_SECONDS,
            )
            logger.info("[NODE] reconnect to master in %.2f seconds", reconnect_delay)
            await asyncio.sleep(reconnect_delay)

    async def _connect_once(self, ws_url: str) -> None:
        config = self._node_runtime.config
        self._ws = await websockets.connect(ws_url, close_timeout=10, proxy=None)
        await self._ws.send(
            json.dumps(
                build_node_message(
                    NODE_AUTH,
                    {
                        "node_id": config.effective_node_id,
                        "secret": config.node_secret,
                        "capabilities": {
                            "agent_creation": True,
                            "agent_proxy": True,
                        },
                    },
                )
            )
        )
        raw_message = await self._ws.recv()
        message = json.loads(raw_message)
        if (
            not isinstance(message, dict)
            or message.get("type") != NODE_AUTH_RESULT
            or not (message.get("payload") or {}).get("success")
        ):
            raise RuntimeError("node auth failed")

        token = (message.get("payload") or {}).get("token")
        if not token:
            raise RuntimeError("missing token from master")

        os.environ["JARVIS_AUTH_TOKEN"] = token
        self._node_runtime.token_sync_state.mark_success("master")
        self._node_runtime.mark_ready()
        logger.info(
            "[NODE] child connected to master node_id=%s ws_url=%s",
            config.effective_node_id,
            ws_url,
        )

        async def heartbeat_loop() -> None:
            while True:
                await asyncio.sleep(CHILD_HEARTBEAT_INTERVAL_SECONDS)
                if self._ws is None:
                    raise RuntimeError("node websocket is closed")
                await self._ws.send(
                    json.dumps(
                        build_node_message(
                            NODE_HEARTBEAT,
                            {"node_id": config.effective_node_id},
                        )
                    )
                )

        async def recv_loop() -> None:
            while True:
                if self._ws is None:
                    raise RuntimeError("node websocket is closed")
                raw_next_message = await self._ws.recv()
                next_message = json.loads(raw_next_message)
                if not isinstance(next_message, dict):
                    continue
                message_type = next_message.get("type")
                request_id = next_message.get("request_id")
                logger.info(
                    "[NODE] child recv message type=%s request_id=%s",
                    message_type,
                    request_id,
                )
                if message_type == AGENT_CREATE_REQUEST:
                    response = (
                        self._node_connection_manager._handle_agent_create_request(
                            next_message, "master"
                        )
                    )
                    await self._ws.send(json.dumps(response))
                    continue
                if message_type == AGENT_HTTP_REQUEST:
                    response = (
                        await self._node_connection_manager._handle_agent_http_request(
                            next_message
                        )
                    )
                    await self._ws.send(json.dumps(response))
                    continue
                if message_type == NODE_HTTP_PROXY_REQUEST:
                    response = await self._node_connection_manager._handle_node_http_proxy_request(
                        next_message
                    )
                    await self._ws.send(json.dumps(response))
                    continue
                if message_type == AGENT_LIST_REQUEST:
                    response = self._node_connection_manager._handle_agent_list_request(
                        next_message
                    )
                    await self._ws.send(json.dumps(response))
                    continue
                if message_type == AGENT_STOP_REQUEST:
                    response = self._node_connection_manager._handle_agent_stop_request(
                        next_message
                    )
                    await self._ws.send(json.dumps(response))
                    continue
                if message_type == AGENT_DELETE_REQUEST:
                    response = (
                        self._node_connection_manager._handle_agent_delete_request(
                            next_message
                        )
                    )
                    await self._ws.send(json.dumps(response))
                    continue
                if message_type == AGENT_WS_REQUEST:
                    response = (
                        await self._node_connection_manager._handle_agent_ws_request(
                            next_message
                        )
                    )
                    await self._ws.send(json.dumps(response))
                    continue
                if message_type == AGENT_WS_OPEN_REQUEST:
                    response = await self._node_connection_manager._handle_agent_ws_open_request(
                        next_message
                    )
                    await self._ws.send(json.dumps(response))
                    continue
                if message_type == AGENT_WS_SEND_REQUEST:
                    response = await self._node_connection_manager._handle_agent_ws_send_request(
                        next_message
                    )
                    await self._ws.send(json.dumps(response))
                    continue
                if message_type == AGENT_WS_RECV_REQUEST:
                    response = await self._node_connection_manager._handle_agent_ws_recv_request(
                        next_message
                    )
                    await self._ws.send(json.dumps(response))
                    continue
                if message_type == AGENT_WS_CLOSE_REQUEST:
                    response = await self._node_connection_manager._handle_agent_ws_close_request(
                        next_message
                    )
                    await self._ws.send(json.dumps(response))
                    continue
                if message_type == DIRECTORY_LIST_REQUEST:
                    response = (
                        self._node_connection_manager._handle_directory_list_request(
                            next_message
                        )
                    )
                    await self._ws.send(json.dumps(response))
                    continue
                if message_type == NODE_TERMINAL_REQUEST:
                    response = await self._handle_node_terminal_request(
                        next_message
                    )
                    await self._ws.send(json.dumps(response))
                    continue
                logger.warning(
                    "[NODE] child unhandled message type=%s request_id=%s",
                    message_type,
                    request_id,
                )

        heartbeat_task = asyncio.create_task(heartbeat_loop())
        recv_task = asyncio.create_task(recv_loop())
        done, pending = await asyncio.wait(
            {heartbeat_task, recv_task},
            return_when=asyncio.FIRST_EXCEPTION,
        )
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception()
            if exc is not None:
                raise exc
