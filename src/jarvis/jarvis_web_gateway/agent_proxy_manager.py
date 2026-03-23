# -*- coding: utf-8 -*-
"""Agent Proxy Manager：管理 Agent 反向代理。

负责将前端请求代理到 Agent 网关端口，解决云环境下端口管理问题。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

import httpx
import websockets
from fastapi import Request, Response, WebSocket, WebSocketDisconnect

from jarvis.jarvis_web_gateway.agent_manager import AgentManager


# 配置日志
logger = logging.getLogger(__name__)


# 代理相关异常
class AgentProxyError(Exception):
    """代理异常基类。"""

    pass


class AgentNotFoundError(AgentProxyError):
    """Agent 不存在。"""

    pass


class AgentNotRunningError(AgentProxyError):
    """Agent 未运行。"""

    pass


class ProxyConnectionError(AgentProxyError):
    """代理连接失败。"""

    pass


class AgentProxyManager:
    """Agent 代理管理器：管理 Agent 反向代理。"""

    def __init__(
        self,
        agent_manager: AgentManager,
        http_timeout: float = 30.0,
        ws_timeout: float = 60.0,
    ) -> None:
        """初始化 AgentProxyManager。

        Args:
            agent_manager: AgentManager 实例
            http_timeout: HTTP 请求超时时间（秒）
            ws_timeout: WebSocket 连接超时时间（秒）
        """
        self._agent_manager = agent_manager
        self._http_timeout = http_timeout
        self._ws_timeout = ws_timeout

        # 创建 httpx 异步客户端（带连接池）
        self._http_client = httpx.AsyncClient(
            timeout=http_timeout,
            follow_redirects=True,
        )
        self._agent_message_cache: dict[str, list[str]] = defaultdict(list)
        self._agent_cache_limit = 200
        self._agent_cache_lock = asyncio.Lock()

        logger.info("[PROXY MANAGER] AgentProxyManager initialized")

    async def get_agent_port(self, agent_id: str) -> int:
        """获取 Agent 监听端口。

        Args:
            agent_id: Agent ID

        Returns:
            Agent 端口号

        Raises:
            AgentNotFoundError: Agent 不存在
            AgentNotRunningError: Agent 未运行
        """
        agent = self._agent_manager.get_agent(agent_id)
        if agent is None:
            raise AgentNotFoundError(f"Agent not found: {agent_id}")

        if agent.status != "running":
            raise AgentNotRunningError(
                f"Agent {agent_id} is not running (status: {agent.status})"
            )

        port = agent.port
        if port is None:
            raise AgentNotRunningError(f"Agent {agent_id} has no port assigned")

        logger.debug(f"[PROXY MANAGER] Got port {port} for agent {agent_id}")
        return port

    async def proxy_http_request(
        self,
        request: Request,
        agent_id: str,
        path: str,
    ) -> Response:
        """代理 HTTP 请求到 Agent。

        Args:
            request: FastAPI Request 对象
            agent_id: Agent ID
            path: 目标路径

        Returns:
            FastAPI Response 对象

        Raises:
            AgentProxyError: 代理失败
        """
        # 获取 Agent 端口
        try:
            port = await self.get_agent_port(agent_id)
        except AgentProxyError as e:
            logger.error(f"[PROXY MANAGER] Failed to get agent port: {e}")
            raise

        # 构建 Agent URL
        agent_url = f"http://127.0.0.1:{port}/{path}"
        logger.info(f"[PROXY MANAGER] Proxying HTTP {request.method} {agent_url}")

        # 准备请求头（过滤掉 Host 等需要重写的头）
        headers = dict(request.headers)
        headers.pop("host", None)
        headers["X-Forwarded-For"] = (
            request.client.host if request.client else "unknown"
        )
        headers["X-Forwarded-Proto"] = request.url.scheme

        # 读取请求体
        body = await request.body()

        try:
            # 发送代理请求
            response = await self._http_client.request(
                method=request.method,
                url=agent_url,
                headers=headers,
                content=body,
                params=request.query_params,
            )

            logger.debug(
                f"[PROXY MANAGER] Agent response: {response.status_code} "
                f"(headers: {len(response.headers)} bytes, body: {len(response.content)} bytes)"
            )

            # 构建响应
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
            logger.error(f"[PROXY MANAGER] HTTP proxy timeout: {agent_url}")
            raise ProxyConnectionError(f"HTTP proxy timeout: {agent_url}")
        except httpx.ConnectError as e:
            logger.error(f"[PROXY MANAGER] HTTP proxy connection error: {e}")
            raise ProxyConnectionError(f"Cannot connect to agent: {e}")
        except Exception as e:
            logger.error(f"[PROXY MANAGER] HTTP proxy error: {e}")
            raise ProxyConnectionError(f"HTTP proxy failed: {e}")

    async def proxy_websocket(
        self,
        client_ws: WebSocket,
        agent_id: str,
    ) -> None:
        """代理 WebSocket 连接到 Agent。

        Args:
            client_ws: 客户端 WebSocket 连接
            agent_id: Agent ID

        Raises:
            AgentProxyError: 代理失败
        """
        # 获取 Agent 端口
        try:
            port = await self.get_agent_port(agent_id)
        except AgentProxyError as e:
            logger.error(f"[PROXY MANAGER] Failed to get agent port: {e}")
            await client_ws.close(code=4000, reason=str(e))
            return  # 已关闭连接，不抛出异常

        # 构建 Agent WebSocket URL
        agent_url = f"ws://127.0.0.1:{port}/ws"
        logger.info(f"[PROXY MANAGER] Proxying WebSocket to {agent_url}")

        # 连接到 Agent
        try:
            agent_ws = await websockets.connect(
                agent_url,
                close_timeout=self._ws_timeout,
                proxy=None,  # 禁用自动代理，直接连接本地Agent
            )
        except Exception as e:
            logger.error(f"[PROXY MANAGER] Failed to connect to agent WebSocket: {e}")
            await client_ws.close(code=4001, reason="Cannot connect to agent")
            return  # 已关闭连接，不抛出异常

        logger.info(f"[PROXY MANAGER] WebSocket connected to agent {agent_id}")

        try:
            # 发送认证消息给 Agent Gateway
            # Agent Gateway 要求首条消息必须是认证消息
            import os

            auth_token = os.environ.get("JARVIS_AUTH_TOKEN")
            if auth_token:
                auth_message = json.dumps(
                    {"type": "auth", "payload": {"token": auth_token}}
                )
                await agent_ws.send(auth_message)
                logger.info(f"[PROXY MANAGER] Sent auth message to agent {agent_id}")

            await self._flush_cached_messages(client_ws, agent_id)

            # 创建双向转发任务
            client_to_agent_task = asyncio.create_task(
                self._forward_messages(client_ws, agent_ws, "client->agent", agent_id)
            )
            agent_to_client_task = asyncio.create_task(
                self._forward_messages(agent_ws, client_ws, "agent->client", agent_id)
            )

            # 优先等待 client->agent 结束；client 断开后，不再依赖向 client 发送失败来触发缓存，
            # 而是显式切换到继续消费 agent 消息并缓存的模式。
            await client_to_agent_task

            if not agent_to_client_task.done():
                agent_to_client_task.cancel()
                try:
                    await agent_to_client_task
                except asyncio.CancelledError:
                    pass

                try:
                    await asyncio.wait_for(
                        self._cache_messages_from_agent(agent_ws, agent_id),
                        timeout=self._ws_timeout,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "[PROXY MANAGER] Timed out while caching agent messages after client disconnect: %s",
                        agent_id,
                    )

            # 检查转发任务是否有异常
            for task in (client_to_agent_task, agent_to_client_task):
                if task.cancelled():
                    continue
                if task.exception():
                    logger.error(
                        f"[PROXY MANAGER] WebSocket forward task error: {task.exception()}"
                    )
                    # client_ws的关闭由app.py的agent_websocket_proxy统一管理
                    # 这里不关闭，避免重复关闭导致RuntimeError

        finally:
            # 清理连接
            try:
                if "agent_ws" in locals():
                    await agent_ws.close()
            except Exception as e:
                logger.warning(f"[PROXY MANAGER] Failed to close agent WebSocket: {e}")

            logger.info(f"[PROXY MANAGER] WebSocket proxy closed for agent {agent_id}")

    async def _forward_messages(
        self,
        source_ws: Any,
        target_ws: Any,
        direction: str,
        agent_id: str,
    ) -> None:
        """转发 WebSocket 消息。

        Args:
            source_ws: 源 WebSocket（websockets WebSocket 或 FastAPI WebSocket）
            target_ws: 目标 WebSocket
            direction: 转发方向（用于日志）
        """
        try:
            if isinstance(source_ws, WebSocket):
                # FastAPI WebSocket
                while True:
                    data = await source_ws.receive_text()
                    logger.debug(
                        f"[PROXY MANAGER] Forwarding {direction}: {len(data)} bytes"
                    )
                    if isinstance(target_ws, WebSocket):
                        await target_ws.send_text(data)
                    else:
                        await target_ws.send(data)
            else:
                # websockets WebSocket
                async for message in source_ws:
                    data = message if isinstance(message, str) else message.decode()
                    logger.debug(
                        f"[PROXY MANAGER] Forwarding {direction}: {len(data)} bytes"
                    )
                    try:
                        if isinstance(target_ws, WebSocket):
                            await target_ws.send_text(data)
                        else:
                            await target_ws.send(data)
                    except Exception as e:
                        if direction == "agent->client":
                            logger.info(
                                "[PROXY MANAGER] Client unavailable while forwarding agent message, caching it for %s: %s",
                                agent_id,
                                e,
                            )
                            await self._cache_agent_message(agent_id, data)
                            return
                        raise

        except WebSocketDisconnect:
            logger.debug(f"[PROXY MANAGER] {direction}: WebSocket disconnected")
        except Exception as e:
            logger.debug(f"[PROXY MANAGER] {direction}: Forward error: {e}")
            raise

    async def _cache_agent_message(self, agent_id: str, message: str) -> None:
        async with self._agent_cache_lock:
            cache_bucket = self._agent_message_cache[agent_id]
            cache_bucket.append(message)
            if len(cache_bucket) > self._agent_cache_limit:
                cache_bucket.pop(0)
            logger.info(
                "[PROXY MANAGER] Cached agent message for %s, cache_size=%d",
                agent_id,
                len(cache_bucket),
            )

    async def _cache_messages_from_agent(self, agent_ws: Any, agent_id: str) -> None:
        """在 client 断开后继续消费 agent 消息并写入缓存。"""
        try:
            async for message in agent_ws:
                data = message if isinstance(message, str) else message.decode()
                logger.info(
                    "[PROXY MANAGER] Caching agent message after client disconnect for %s: %d bytes",
                    agent_id,
                    len(data),
                )
                await self._cache_agent_message(agent_id, data)
        except Exception as e:
            logger.debug(
                f"[PROXY MANAGER] Stop caching agent messages for {agent_id}: {e}"
            )

    async def _flush_cached_messages(self, client_ws: WebSocket, agent_id: str) -> None:
        async with self._agent_cache_lock:
            cached_messages = list(self._agent_message_cache.get(agent_id, []))
            self._agent_message_cache.pop(agent_id, None)

        if not cached_messages:
            return

        logger.info(
            "[PROXY MANAGER] Flushing %d cached messages to agent client %s",
            len(cached_messages),
            agent_id,
        )
        for index, message in enumerate(cached_messages):
            try:
                await client_ws.send_text(message)
            except Exception:
                remaining_messages = cached_messages[index:]
                async with self._agent_cache_lock:
                    cache_bucket = self._agent_message_cache[agent_id]
                    for pending_message in remaining_messages:
                        cache_bucket.append(pending_message)
                    while len(cache_bucket) > self._agent_cache_limit:
                        cache_bucket.pop(0)
                logger.warning(
                    "[PROXY MANAGER] Failed while flushing cached messages for %s, restored %d messages",
                    agent_id,
                    len(remaining_messages),
                )
                raise

    async def cleanup(self) -> None:
        """清理资源。"""
        await self._http_client.aclose()
        logger.info("[PROXY MANAGER] Cleanup completed")
