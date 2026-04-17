"""连接模块 - WebSocket连接管理，重试逻辑与web版本对齐"""

import asyncio
import json
import logging
from typing import Callable, Dict, Any
from dataclasses import dataclass
from enum import Enum

import websockets

logger = logging.getLogger(__name__)

# 与web版本对齐的重试配置
MAX_RETRIES = 12  # 最多重试12次
RETRY_DELAY = 2.0  # 2秒重试间隔
CONNECTION_TIMEOUT = 10.0  # 10秒连接超时


class ConnectionState(Enum):
    """连接状态"""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class ConnectionConfig:
    """连接配置"""

    host: str
    port: int
    protocol: str = "ws"


class ConnectionManager:
    """连接管理器

    与web版本对齐:
    - Gateway连接: 主WebSocket连接
    - Agent连接: 每个Agent独立的WebSocket连接
    - 重试逻辑: 最大12次，间隔2秒，超时10秒
    """

    def __init__(self):
        self._gateway_ws: Any = None
        self._agent_ws: Dict[str, Any] = {}
        self._gateway_state = ConnectionState.DISCONNECTED
        self._agent_states: Dict[str, ConnectionState] = {}
        self._message_handlers: Dict[str, Callable] = {}

    def get_gateway_state(self) -> ConnectionState:
        """获取Gateway连接状态"""
        return self._gateway_state

    def get_agent_state(self, agent_id: str) -> ConnectionState:
        """获取Agent连接状态"""
        return self._agent_states.get(agent_id, ConnectionState.DISCONNECTED)

    def is_connected(self) -> bool:
        """检查Gateway是否已连接"""
        return self._gateway_state == ConnectionState.CONNECTED

    def is_agent_connected(self, agent_id: str) -> bool:
        """检查Agent是否已连接"""
        return self._agent_states.get(agent_id) == ConnectionState.CONNECTED

    def register_message_handler(self, message_type: str, handler: Callable) -> None:
        """注册消息处理器"""
        self._message_handlers[message_type] = handler

    async def connect_gateway(self, host: str, port: int, token: str) -> bool:
        """连接到Gateway WebSocket

        Args:
            host: 网关主机
            port: 网关端口
            token: 认证Token

        Returns:
            bool: 连接是否成功
        """
        url = f"ws://{host}:{port}/api/node/master/ws"

        try:
            self._gateway_state = ConnectionState.CONNECTING

            # 使用Authorization header传递Token
            extra_headers = {"Authorization": f"Bearer {token}"}

            self._gateway_ws = await asyncio.wait_for(
                websockets.connect(url, additional_headers=extra_headers),
                timeout=CONNECTION_TIMEOUT,
            )

            self._gateway_state = ConnectionState.CONNECTED
            logger.info(f"Gateway connected: {url}")

            # 启动消息接收任务
            asyncio.create_task(self._receive_gateway_messages())

            return True

        except asyncio.TimeoutError:
            self._gateway_state = ConnectionState.ERROR
            logger.error(f"Gateway connection timeout: {url}")
            return False
        except Exception as e:
            self._gateway_state = ConnectionState.ERROR
            logger.error(f"Gateway connection failed: {e}")
            return False

    async def disconnect_gateway(self) -> None:
        """断开Gateway连接"""
        if self._gateway_ws:
            await self._gateway_ws.close()
            self._gateway_ws = None
        self._gateway_state = ConnectionState.DISCONNECTED
        logger.info("Gateway disconnected")

    async def connect_agent(
        self, agent_id: str, host: str, port: int, token: str, node_id: str = "master"
    ) -> bool:
        """连接到Agent（带重试逻辑，与web版本对齐）

        重试逻辑:
        - 最大重试次数: 12次
        - 重试间隔: 2秒
        - 连接超时: 10秒
        - 重试前清理旧连接

        Args:
            agent_id: Agent ID
            host: 网关主机
            port: 网关端口
            token: 认证Token
            node_id: 节点ID

        Returns:
            bool: 连接是否成功
        """
        return await self._connect_agent_with_retry(
            agent_id, host, port, token, node_id, retry_count=0
        )

    async def _connect_agent_with_retry(
        self,
        agent_id: str,
        host: str,
        port: int,
        token: str,
        node_id: str,
        retry_count: int,
    ) -> bool:
        """带重试的Agent连接（内部实现）"""
        url = f"ws://{host}:{port}/api/node/{node_id}/agent/{agent_id}/ws"

        # 清理旧连接
        await self._cleanup_agent_connection(agent_id)

        self._agent_states[agent_id] = ConnectionState.CONNECTING

        try:
            extra_headers = {"Authorization": f"Bearer {token}"}

            ws = await asyncio.wait_for(
                websockets.connect(url, additional_headers=extra_headers),
                timeout=CONNECTION_TIMEOUT,
            )

            self._agent_ws[agent_id] = ws
            self._agent_states[agent_id] = ConnectionState.CONNECTED
            logger.info(f"Agent {agent_id} connected")

            # 启动消息接收任务
            asyncio.create_task(self._receive_agent_messages(agent_id))

            return True

        except asyncio.TimeoutError:
            logger.warning(
                f"Agent {agent_id} connection timeout (retry {retry_count + 1}/{MAX_RETRIES})"
            )

            if retry_count < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)
                return await self._connect_agent_with_retry(
                    agent_id, host, port, token, node_id, retry_count + 1
                )
            else:
                self._agent_states[agent_id] = ConnectionState.ERROR
                logger.error(
                    f"Agent {agent_id} connection failed after {MAX_RETRIES} retries"
                )
                return False

        except Exception as e:
            logger.warning(
                f"Agent {agent_id} connection error: {e} (retry {retry_count + 1}/{MAX_RETRIES})"
            )

            if retry_count < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)
                return await self._connect_agent_with_retry(
                    agent_id, host, port, token, node_id, retry_count + 1
                )
            else:
                self._agent_states[agent_id] = ConnectionState.ERROR
                logger.error(
                    f"Agent {agent_id} connection failed after {MAX_RETRIES} retries"
                )
                return False

    async def _cleanup_agent_connection(self, agent_id: str) -> None:
        """清理Agent连接（与web版本对齐）"""
        if agent_id in self._agent_ws:
            ws = self._agent_ws[agent_id]
            if ws and not ws.closed:
                await ws.close()
                # 等待连接完全关闭
                for _ in range(20):  # 最多等待1秒
                    if ws.closed:
                        break
                    await asyncio.sleep(0.05)
            del self._agent_ws[agent_id]

        if agent_id in self._agent_states:
            del self._agent_states[agent_id]

    async def disconnect_agent(self, agent_id: str) -> None:
        """断开Agent连接"""
        await self._cleanup_agent_connection(agent_id)
        logger.info(f"Agent {agent_id} disconnected")

    async def disconnect_all(self) -> None:
        """断开所有连接"""
        # 断开所有Agent连接
        for agent_id in list(self._agent_ws.keys()):
            await self.disconnect_agent(agent_id)

        # 断开Gateway连接
        await self.disconnect_gateway()

    async def send_to_gateway(self, message: Dict[str, Any]) -> None:
        """发送消息到Gateway"""
        if not self._gateway_ws or self._gateway_ws.closed:
            raise ConnectionError("Gateway not connected")

        await self._gateway_ws.send(json.dumps(message))

    async def send_to_agent(self, agent_id: str, message: Dict[str, Any]) -> None:
        """发送消息到Agent"""
        ws = self._agent_ws.get(agent_id)
        if not ws or ws.closed:
            raise ConnectionError(f"Agent {agent_id} not connected")

        await ws.send(json.dumps(message))

    async def _receive_gateway_messages(self) -> None:
        """接收Gateway消息"""
        if not self._gateway_ws:
            return

        try:
            async for message in self._gateway_ws:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type")

                    handler = self._message_handlers.get(msg_type)
                    if handler:
                        await handler(data)
                    else:
                        logger.debug(f"No handler for gateway message type: {msg_type}")

                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON from gateway: {message}")
                except Exception as e:
                    logger.error(f"Error handling gateway message: {e}")

        except websockets.ConnectionClosed:
            logger.info("Gateway connection closed")
            self._gateway_state = ConnectionState.DISCONNECTED
        except Exception as e:
            logger.error(f"Gateway message receive error: {e}")
            self._gateway_state = ConnectionState.ERROR

    async def _receive_agent_messages(self, agent_id: str) -> None:
        """接收Agent消息"""
        ws = self._agent_ws.get(agent_id)
        if not ws:
            return

        try:
            async for message in ws:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type")

                    # 添加agent_id到消息
                    data["_agent_id"] = agent_id

                    handler = self._message_handlers.get(msg_type)
                    if handler:
                        await handler(data)
                    else:
                        logger.debug(f"No handler for agent message type: {msg_type}")

                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON from agent {agent_id}: {message}")
                except Exception as e:
                    logger.error(f"Error handling agent message: {e}")

        except websockets.ConnectionClosed:
            logger.info(f"Agent {agent_id} connection closed")
            self._agent_states[agent_id] = ConnectionState.DISCONNECTED
        except Exception as e:
            logger.error(f"Agent {agent_id} message receive error: {e}")
            self._agent_states[agent_id] = ConnectionState.ERROR


class ConnectionError(Exception):
    """连接错误"""

    pass
