# -*- coding: utf-8 -*-
"""Node 主子节点连接与基础状态管理。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import random
import shutil
import uuid
from typing import Any, Dict, Optional

import yaml

import websockets
from fastapi import WebSocket
from websockets.asyncio.connection import State

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
    SERVICE_RESTART_REQUEST,
    SERVICE_RESTART_RESPONSE,
    CONFIG_SYNC_REQUEST,
    CONFIG_SYNC_RESPONSE,
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
                        SERVICE_RESTART_RESPONSE,
                        CONFIG_SYNC_RESPONSE,
                    )
                    and request_id
                ):
                    future = self._pending_requests.pop(request_id, None)
                    if future is not None and not future.done():
                        future.set_result(next_message)
                    continue
                if message_type == NODE_TERMINAL_OUTPUT:
                    # child 端推送的终端输出，转发给前端
                    terminal_payload = next_message.get("payload") or {}
                    output_session_id = terminal_payload.get("session_id") or "default"
                    output_message = terminal_payload.get("message")
                    if output_message and self._router:
                        self._router.publish(
                            output_message, session_id=output_session_id
                        )
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
                if message_type == CONFIG_SYNC_REQUEST:
                    logger.info(
                        "[NODE] handling config sync request node_id=%s request_id=%s",
                        node_id,
                        request_id,
                    )
                    response = await self._handle_config_sync_request(next_message)
                    await websocket.send_json(response)
                    logger.info(
                        "[NODE] sent config sync response node_id=%s request_id=%s",
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
            try:
                response = await asyncio.wait_for(future, timeout=timeout)
            except asyncio.TimeoutError as exc:
                raise RuntimeError(
                    f"node request timed out: node_id={node_id}, type={message_type}, request_id={request_id}, timeout={timeout}s"
                ) from exc
            logger.info(
                "[NODE] received response node_id=%s type=%s request_id=%s",
                node_id,
                response.get("type") if isinstance(response, dict) else None,
                request_id,
            )
            if not isinstance(response, dict):
                raise RuntimeError(
                    f"invalid node response: node_id={node_id}, type={message_type}, request_id={request_id}"
                )
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
            # 清理已关闭的会话
            if agent_ws.state != State.OPEN:
                self._agent_ws_sessions.pop(session_id, None)
                raise RuntimeError(f"ws session already closed: {session_id}")
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
            # 清理已关闭的会话
            if agent_ws.state != State.OPEN:
                self._agent_ws_sessions.pop(session_id, None)
                raise RuntimeError(f"ws session already closed: {session_id}")
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

    async def _handle_config_sync_request(
        self, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理配置同步请求（child 端）。"""
        request_id = message.get("request_id")
        payload = message.get("payload") or {}
        config_sections = payload.get("config_sections", [])
        config_data = payload.get("config_data", {})

        logger.info(
            "[NODE CONFIG SYNC] child handling config sync request_id=%s sections=%s",
            request_id,
            config_sections,
        )

        try:
            # 获取配置文件路径
            config_file = pathlib.Path.home() / ".jarvis" / "config.yaml"

            # 备份原配置文件
            backup_file = config_file.with_suffix(".yaml.bak")
            if config_file.exists():
                shutil.copy2(config_file, backup_file)
                logger.info("[NODE CONFIG SYNC] backed up config to %s", backup_file)

            # 读取现有配置
            existing_config = {}
            if config_file.exists():
                with open(config_file, "r", encoding="utf-8") as f:
                    existing_config = yaml.safe_load(f) or {}

            # 更新配置
            updated_config = existing_config.copy()
            for section in config_sections:
                if section in config_data:
                    updated_config[section] = config_data[section]
                    logger.info("[NODE CONFIG SYNC] updated section: %s", section)

            # 保存配置
            config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(config_file, "w", encoding="utf-8") as f:
                yaml.safe_dump(
                    updated_config, f, allow_unicode=True, default_flow_style=False
                )

            logger.info(
                "[NODE CONFIG SYNC] child config sync completed request_id=%s",
                request_id,
            )
            return build_node_message(
                CONFIG_SYNC_RESPONSE,
                {
                    "success": True,
                    "data": {
                        "message": "配置同步成功",
                        "backup_file": str(backup_file),
                    },
                },
                request_id=request_id,
            )
        except Exception as exc:
            logger.error(
                "[NODE CONFIG SYNC] child config sync failed request_id=%s error=%s",
                request_id,
                exc,
            )
            # 尝试恢复备份
            try:
                if backup_file.exists():
                    shutil.copy2(backup_file, config_file)
                    logger.info("[NODE CONFIG SYNC] restored config from backup")
            except Exception as restore_exc:
                logger.error(
                    "[NODE CONFIG SYNC] failed to restore backup: %s", restore_exc
                )

            return build_node_message(
                CONFIG_SYNC_RESPONSE,
                {
                    "success": False,
                    "error": {"code": "CONFIG_SYNC_ERROR", "message": str(exc)},
                },
                request_id=request_id,
            )


class NodeTerminalOutputProxy:
    """代理 Publisher，将 child 端终端输出通过 NODE_TERMINAL_OUTPUT 推送给 master。

    TerminalSession._publish_output 在同步线程中调用 publish()，
    因此需要用 asyncio.run_coroutine_threadsafe 桥接到事件循环。
    """

    def __init__(self, ws: Any, loop: asyncio.AbstractEventLoop) -> None:
        self._ws = ws
        self._loop = loop

    def publish(self, message: Any, session_id: str = "default") -> None:
        """将终端输出消息通过 NODE_TERMINAL_OUTPUT 发送给 master。"""
        try:
            output_msg = json.dumps(
                build_node_message(
                    NODE_TERMINAL_OUTPUT,
                    {
                        "session_id": session_id,
                        "message": message,
                    },
                )
            )
            future = asyncio.run_coroutine_threadsafe(
                self._ws.send(output_msg), self._loop
            )
            future.result(timeout=5)
        except Exception as e:
            logger.warning("[NODE TERMINAL PROXY] failed to send output: %s", e)


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
                    response = await self._handle_node_terminal_request(next_message)
                    await self._ws.send(json.dumps(response))
                    continue
                if message_type == SERVICE_RESTART_REQUEST:
                    response = await self._handle_service_restart_request(next_message)
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

    async def _handle_node_terminal_request(
        self, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理 master 转发的终端请求（child 端）。"""
        payload = message.get("payload") or {}
        request_id = message.get("request_id")
        action = str(payload.get("action") or "").strip()
        inner_payload = payload.get("payload") or {}
        session_id = str(payload.get("session_id") or "default")
        tsm = self._node_connection_manager._terminal_session_manager

        logger.info(
            "[NODE TERMINAL] child handling action=%s request_id=%s",
            action,
            request_id,
        )

        if tsm is None:
            return build_node_message(
                NODE_TERMINAL_RESPONSE,
                {
                    "success": False,
                    "error": {
                        "code": "NO_TERMINAL_MANAGER",
                        "message": "terminal session manager not available",
                    },
                },
                request_id=request_id,
            )

        try:
            if action == "terminal_create":
                interpreter = inner_payload.get("interpreter") or os.environ.get(
                    "SHELL", "bash"
                )
                raw_working_dir = inner_payload.get("working_dir")
                working_dir = str(raw_working_dir).strip() if raw_working_dir else ""
                if not working_dir:
                    import pathlib as _pathlib

                    working_dir = str(_pathlib.Path.home())
                # 创建代理 publisher，将终端输出推送回 master
                proxy_publisher = NodeTerminalOutputProxy(
                    self._ws, asyncio.get_running_loop()
                )
                terminal_id, error = tsm.create_session(
                    interpreter=interpreter,
                    working_dir=working_dir,
                    stream_publisher=proxy_publisher,
                    session_id=session_id,
                )
                if terminal_id:
                    return build_node_message(
                        NODE_TERMINAL_RESPONSE,
                        {
                            "success": True,
                            "data": {
                                "terminal_id": terminal_id,
                                "interpreter": interpreter,
                                "working_dir": working_dir,
                            },
                        },
                        request_id=request_id,
                    )
                else:
                    return build_node_message(
                        NODE_TERMINAL_RESPONSE,
                        {
                            "success": False,
                            "error": {
                                "code": "TERMINAL_CREATE_FAILED",
                                "message": error or "unknown error",
                            },
                        },
                        request_id=request_id,
                    )

            elif action == "terminal_close":
                terminal_id = str(inner_payload.get("terminal_id") or "").strip()
                if terminal_id:
                    tsm.close_session(terminal_id)
                return build_node_message(
                    NODE_TERMINAL_RESPONSE,
                    {"success": True},
                    request_id=request_id,
                )

            elif action == "terminal_session_input":
                terminal_id = str(inner_payload.get("terminal_id") or "").strip()
                data = inner_payload.get("data", "")
                if terminal_id:
                    tsm.write_input(terminal_id, data)
                return build_node_message(
                    NODE_TERMINAL_RESPONSE,
                    {"success": True},
                    request_id=request_id,
                )

            elif action == "terminal_session_resize":
                terminal_id = str(inner_payload.get("terminal_id") or "").strip()
                rows = int(inner_payload.get("rows") or 24)
                cols = int(inner_payload.get("cols") or 80)
                if terminal_id:
                    tsm.resize(terminal_id, rows, cols)
                return build_node_message(
                    NODE_TERMINAL_RESPONSE,
                    {"success": True},
                    request_id=request_id,
                )

            else:
                return build_node_message(
                    NODE_TERMINAL_RESPONSE,
                    {
                        "success": False,
                        "error": {
                            "code": "UNKNOWN_ACTION",
                            "message": f"unknown terminal action: {action}",
                        },
                    },
                    request_id=request_id,
                )

        except Exception as exc:
            logger.error("[NODE TERMINAL] child action=%s failed: %s", action, exc)
            return build_node_message(
                NODE_TERMINAL_RESPONSE,
                {
                    "success": False,
                    "error": {"code": "TERMINAL_ERROR", "message": str(exc)},
                },
                request_id=request_id,
            )

    async def _handle_service_restart_request(
        self, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理 master 转发的服务重启请求（child 端）。"""
        request_id = message.get("request_id")
        payload = message.get("payload") or {}
        restart_frontend = bool(payload.get("restart_frontend", True))

        logger.info(
            "[NODE RESTART] child handling service restart request_id=%s restart_frontend=%s",
            request_id,
            restart_frontend,
        )

        try:
            from jarvis.jarvis_service.cli import get_single_instance_lock_path

            lock_file_path = get_single_instance_lock_path()
            if not lock_file_path.exists():
                return build_node_message(
                    SERVICE_RESTART_RESPONSE,
                    {
                        "success": False,
                        "error": {
                            "code": "UNSUPPORTED",
                            "message": "当前环境不支持重启：未检测到 jarvis-service 锁文件",
                        },
                    },
                    request_id=request_id,
                )

            service_pid_text = lock_file_path.read_text(encoding="utf-8").strip()
            if not service_pid_text:
                return build_node_message(
                    SERVICE_RESTART_RESPONSE,
                    {
                        "success": False,
                        "error": {
                            "code": "UNSUPPORTED",
                            "message": "当前环境不支持重启：未检测到 service PID",
                        },
                    },
                    request_id=request_id,
                )

            import signal

            service_pid = int(service_pid_text)
            # 根据 restart_frontend 参数选择信号
            signal_to_send = signal.SIGUSR1 if restart_frontend else signal.SIGUSR2
            signal_name = "SIGUSR1" if restart_frontend else "SIGUSR2"
            os.kill(service_pid, signal_to_send)

            message_text = (
                "已请求 jarvis-service 重启所有服务"
                if restart_frontend
                else "已请求 jarvis-service 只重启网关服务"
            )
            logger.info(
                "[NODE RESTART] child service restart requested pid=%s signal=%s request_id=%s",
                service_pid,
                signal_name,
                request_id,
            )
            return build_node_message(
                SERVICE_RESTART_RESPONSE,
                {
                    "success": True,
                    "data": {
                        "pid": service_pid,
                        "signal": signal_name,
                        "message": message_text,
                    },
                },
                request_id=request_id,
            )
        except (ValueError, ProcessLookupError):
            return build_node_message(
                SERVICE_RESTART_RESPONSE,
                {
                    "success": False,
                    "error": {
                        "code": "UNSUPPORTED",
                        "message": "当前环境不支持重启：未通过 jarvis-service 启动",
                    },
                },
                request_id=request_id,
            )
        except PermissionError:
            return build_node_message(
                SERVICE_RESTART_RESPONSE,
                {
                    "success": False,
                    "error": {
                        "code": "PERMISSION_DENIED",
                        "message": "无权限向 jarvis-service 发送重启信号",
                    },
                },
                request_id=request_id,
            )
        except Exception as exc:
            logger.error(
                "[NODE RESTART] child restart failed request_id=%s error=%s",
                request_id,
                exc,
            )
            return build_node_message(
                SERVICE_RESTART_RESPONSE,
                {
                    "success": False,
                    "error": {"code": "INTERNAL_ERROR", "message": str(exc)},
                },
                request_id=request_id,
            )
