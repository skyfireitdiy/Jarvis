# -*- coding: utf-8 -*-
"""Agent WS 推送模式端到端集成测试（真实 websockets 连接）。

用真实的 websockets 服务端/客户端模拟 master<->child 的 node 隧道，
验证：
1. child 侧推送泵产生的 AGENT_WS_OUTPUT 帧能通过真实 WS 传到 master；
2. master 的 handle_node_websocket 消息循环识别 AGENT_WS_OUTPUT 并投递到
   订阅队列（含 closed 收尾）；
3. 全程按 agent_ws 收到顺序到达，且不依赖 AGENT_WS_RECV 轮询。
"""
import os

os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"

import asyncio
import json
from unittest.mock import MagicMock

import pytest
import websockets

from jarvis.jarvis_web_gateway.node_manager import NodeConnectionManager
from jarvis.jarvis_web_gateway.node_protocol import (
    NODE_AUTH,
    build_node_message,
)


class _FakeAgentWS:
    def __init__(self, messages):
        self._messages = list(messages)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(0)

    async def close(self):
        pass


class _FastAPIWSAdapter:
    """把 websockets 的 ServerConnection 适配成 FastAPI WebSocket 接口。"""

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


def _make_manager():
    return NodeConnectionManager(
        node_runtime=MagicMock(),
        agent_manager=MagicMock(),
        agent_proxy_manager=MagicMock(),
        node_http_dispatcher=None,
        router=MagicMock(),
        terminal_session_manager=None,
    )


@pytest.mark.asyncio
async def test_output_frames_reach_master_subscriber_over_real_ws():
    master = _make_manager()
    # master 侧：node_runtime 需要支持 node_registry.upsert / mark_offline
    master._node_runtime.config.node_secret = "secret"
    master._node_runtime.node_registry = MagicMock()
    master._node_runtime.agent_route_registry = MagicMock()
    master._node_runtime.agent_route_registry.get.return_value = None

    session_id = "sess-e2e"
    queue = master.subscribe_agent_ws_output(session_id)

    # 认证后 master 会同步发送 AGENT_LIST_REQUEST 并等待响应，但读循环此时
    # 尚未启动（既有实现如此，真实环境会超时 10s 后继续）。测试中打桩跳过，
    # 避免无关的 10s 等待。
    async def _noop_list(*args, **kwargs):
        return {"payload": {"success": True, "agents": []}}

    master.send_request_to_node = _noop_list

    async def handler(ws):
        await master.handle_node_websocket(_FastAPIWSAdapter(ws))

    received = []

    async def consume():
        while True:
            item = await asyncio.wait_for(queue.get(), timeout=5)
            received.append(item)
            if item.get("closed"):
                return

    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        child_ws = await websockets.connect(f"ws://127.0.0.1:{port}")
        # 认证握手
        await child_ws.send(
            json.dumps(
                build_node_message(
                    NODE_AUTH,
                    {"node_id": "child-1", "secret": "secret", "capabilities": {}},
                )
            )
        )
        auth = json.loads(await child_ws.recv())
        assert auth["type"] == "node_auth_result"
        assert auth["payload"]["success"] is True

        # 让 master 侧 AGENT_LIST_REQUEST 之类不阻塞：master 会在认证后主动发
        # AGENT_LIST_REQUEST 并等响应，这里回一个空列表响应。
        async def child_responder():
            try:
                while True:
                    msg = json.loads(await child_ws.recv())
                    if msg.get("type") == "agent_list_request":
                        await child_ws.send(
                            json.dumps(
                                build_node_message(
                                    "agent_list_response",
                                    {"success": True, "agents": []},
                                    request_id=msg.get("request_id"),
                                )
                            )
                        )
            except Exception:
                pass

        responder_task = asyncio.create_task(child_responder())

        # child 侧：用同一个 manager 实例模拟 child 端（共享 _ws）
        child = _make_manager()
        child._ws = child_ws
        agent_ws = _FakeAgentWS(['{"t": 1}', '{"t": 2}'])
        child._agent_ws_sessions[session_id] = agent_ws
        child._start_agent_ws_pump(session_id, agent_ws)

        await asyncio.wait_for(consume(), timeout=8)
        responder_task.cancel()
        await child_ws.close()

    assert [r["messages"] for r in received] == [
        ['{"t": 1}'],
        ['{"t": 2}'],
        [],
    ]
    assert received[-1]["closed"] is True
