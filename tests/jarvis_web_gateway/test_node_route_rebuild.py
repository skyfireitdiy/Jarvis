# -*- coding: utf-8 -*-
"""回归测试：master 在 child 上线后重建 agent 路由表不能阻塞读循环。

历史缺陷：handle_node_websocket 在认证后同步 await send_request_to_node(
AGENT_LIST_REQUEST)，但响应只能由随后的 while 读循环投递，读循环尚未
启动 -> 必然空等 timeout(10s) 才继续，且每次节点上线都白等 10 秒。

修复后：路由重建改为读循环启动后的后台任务，响应能被正常投递，
重建在毫秒级完成。
"""
import os

os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"

import asyncio
import json
import time
from unittest.mock import MagicMock

import pytest
import websockets

from jarvis.jarvis_web_gateway.node_manager import NodeConnectionManager
from jarvis.jarvis_web_gateway.node_protocol import NODE_AUTH, build_node_message


class _Adapter:
    """把 websockets ServerConnection 适配成 FastAPI WebSocket 接口。"""

    def __init__(self, conn):
        self._conn = conn

    async def accept(self, *args, **kwargs):
        return None

    async def receive_json(self):
        return json.loads(await self._conn.recv())

    async def send_json(self, data):
        await self._conn.send(json.dumps(data))

    async def close(self, code=1000, reason=""):
        await self._conn.close(code=code, reason=reason)


@pytest.mark.asyncio
async def test_agent_routes_rebuilt_without_blocking_read_loop():
    manager = NodeConnectionManager(
        node_runtime=MagicMock(),
        agent_manager=MagicMock(),
        agent_proxy_manager=MagicMock(),
        node_http_dispatcher=None,
        router=MagicMock(),
        terminal_session_manager=None,
    )
    manager._node_runtime.config.node_secret = "s"
    manager._node_runtime.node_registry = MagicMock()
    registry = manager._node_runtime.agent_route_registry
    registry.get.return_value = None

    async def handler(ws):
        await manager.handle_node_websocket(_Adapter(ws))

    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        child = await websockets.connect(f"ws://127.0.0.1:{port}")
        await child.send(
            json.dumps(
                build_node_message(
                    NODE_AUTH, {"node_id": "n1", "secret": "s", "capabilities": {}}
                )
            )
        )
        auth = json.loads(await child.recv())
        assert auth["type"] == "node_auth_result"

        async def responder():
            while True:
                try:
                    msg = json.loads(await child.recv())
                except Exception:
                    return
                if msg.get("type") == "agent_list_request":
                    await child.send(
                        json.dumps(
                            build_node_message(
                                "agent_list_response",
                                {
                                    "success": True,
                                    "agents": [
                                        {"agent_id": "a1", "status": "running"}
                                    ],
                                },
                                request_id=msg.get("request_id"),
                            )
                        )
                    )

        responder_task = asyncio.create_task(responder())
        start = time.time()
        while time.time() - start < 5:
            if registry.register.called:
                break
            await asyncio.sleep(0.02)
        elapsed = time.time() - start

        assert registry.register.called, "agent 路由未被重建（响应没被读循环投递）"
        # 修复前必然 >= 10s（超时）；修复后应为毫秒级
        assert elapsed < 2.0, f"路由重建耗时 {elapsed:.2f}s，读循环仍被阻塞"

        responder_task.cancel()
        await child.close()
