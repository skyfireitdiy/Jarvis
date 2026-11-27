# -*- coding: utf-8 -*-
"""Agent WS 推送模式（child 主动推 AGENT_WS_OUTPUT）单元测试。

覆盖：
1. child 侧推送泵：agent_ws 收到的消息按序通过 _ws 发 AGENT_WS_OUTPUT，
   会话结束发 closed=True。
2. 推送模式下 _handle_agent_ws_recv_request 不抢占 agent_ws（返回空消息 +
   push_mode=True），避免并发 recv 报错。
3. master 侧 _dispatch_agent_ws_output 把推送投递到订阅队列，closed 透传。
4. 未订阅时投递不报错；_stop_all_agent_ws_pumps 清理所有泵。
"""
import os

# 必须在导入 jarvis 模块之前设置环境变量，避免触发交互式配置
os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from jarvis.jarvis_web_gateway.node_manager import NodeConnectionManager
from jarvis.jarvis_web_gateway.node_protocol import AGENT_WS_OUTPUT


def _make_manager():
    return NodeConnectionManager(
        node_runtime=MagicMock(),
        agent_manager=MagicMock(),
        agent_proxy_manager=MagicMock(),
        node_http_dispatcher=None,
        router=MagicMock(),
        terminal_session_manager=None,
    )


class _FakeAgentWS:
    """模拟 websockets 客户端：async for 逐个产出预置消息后结束。"""

    def __init__(self, messages):
        self._messages = list(messages)
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(0)

    async def close(self):
        self.closed = True


class _BlockingAgentWS:
    """永不产出消息的 agent_ws，用于测试泵处于等待态时的取消。"""

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.Event().wait()  # 永久挂起，直到被 cancel
        raise StopAsyncIteration

    async def close(self):
        pass


class _FakeWS:
    """模拟 child 到 master 的连接，记录 send 的原始 JSON。"""

    def __init__(self):
        self.sent = []

    async def send(self, raw):
        self.sent.append(json.loads(raw))


@pytest.mark.asyncio
async def test_pump_pushes_messages_in_order_then_closed():
    mgr = _make_manager()
    fake_ws = _FakeWS()
    mgr._ws = fake_ws
    agent_ws = _FakeAgentWS(['{"a": 1}', '{"b": 2}'])

    session_id = "sess-1"
    mgr._agent_ws_sessions[session_id] = agent_ws
    mgr._start_agent_ws_pump(session_id, agent_ws)

    # 等待泵把两条消息和 closed 都推完
    for _ in range(100):
        await asyncio.sleep(0.01)
        if len(fake_ws.sent) >= 3:
            break

    outputs = [m for m in fake_ws.sent if m.get("type") == AGENT_WS_OUTPUT]
    assert len(outputs) == 3, fake_ws.sent
    assert outputs[0]["payload"]["messages"] == ['{"a": 1}']
    assert outputs[1]["payload"]["messages"] == ['{"b": 2}']
    assert outputs[2]["payload"]["messages"] == []
    assert outputs[2]["payload"]["closed"] is True
    assert all(o["payload"]["session_id"] == session_id for o in outputs)
    # 泵结束后本地状态清理
    assert session_id not in mgr._agent_ws_pumps
    assert session_id not in mgr._agent_ws_sessions


@pytest.mark.asyncio
async def test_recv_request_does_not_steal_when_pump_active():
    mgr = _make_manager()
    mgr._ws = _FakeWS()
    agent_ws = _FakeAgentWS([])  # 永不产出，保持泵挂起
    session_id = "sess-2"
    mgr._agent_ws_sessions[session_id] = agent_ws
    mgr._start_agent_ws_pump(session_id, agent_ws)

    try:
        resp = await mgr._handle_agent_ws_recv_request(
            {
                "payload": {"session_id": session_id, "timeout": 0.01},
                "request_id": "r1",
            }
        )
        payload = resp["payload"]
        assert payload["success"] is True
        assert payload["push_mode"] is True
        assert payload["messages"] == []
    finally:
        mgr._stop_agent_ws_pump(session_id)


@pytest.mark.asyncio
async def test_dispatch_output_to_subscriber_queue():
    mgr = _make_manager()
    session_id = "sess-3"
    queue = mgr.subscribe_agent_ws_output(session_id)

    mgr._dispatch_agent_ws_output(
        {
            "type": AGENT_WS_OUTPUT,
            "payload": {"session_id": session_id, "messages": ["m1"], "closed": False},
        }
    )
    mgr._dispatch_agent_ws_output(
        {
            "type": AGENT_WS_OUTPUT,
            "payload": {"session_id": session_id, "messages": [], "closed": True},
        }
    )

    first = await asyncio.wait_for(queue.get(), timeout=1)
    second = await asyncio.wait_for(queue.get(), timeout=1)
    assert first == {"messages": ["m1"], "closed": False}
    assert second == {"messages": [], "closed": True}

    mgr.unsubscribe_agent_ws_output(session_id)
    assert session_id not in mgr._agent_ws_output_queues


def test_dispatch_without_subscriber_is_safe():
    mgr = _make_manager()
    # 不应抛异常
    mgr._dispatch_agent_ws_output(
        {"payload": {"session_id": "nobody", "messages": ["x"], "closed": False}}
    )
    mgr._dispatch_agent_ws_output({"payload": {}})  # 空 session_id 也不报错


def test_stop_all_pumps_clears_state():
    mgr = _make_manager()
    mgr._agent_ws_sessions["a"] = MagicMock()
    mgr._agent_ws_sessions["b"] = MagicMock()
    mgr._agent_ws_pumps["a"] = MagicMock(done=lambda: True)
    mgr._agent_ws_pumps["b"] = MagicMock(done=lambda: True)
    mgr._stop_all_agent_ws_pumps()
    assert mgr._agent_ws_pumps == {}
    assert mgr._agent_ws_sessions == {}


def test_bounded_queue_drops_oldest_when_full():
    """慢消费者时队列不无界增长，丢最旧帧。"""
    from jarvis.jarvis_web_gateway import node_manager as nm

    mgr = _make_manager()
    session_id = "sess-bp"
    queue = mgr.subscribe_agent_ws_output(session_id)
    cap = nm._AGENT_WS_OUTPUT_QUEUE_MAX
    assert queue.maxsize == cap

    total = cap + 5
    for i in range(total):
        mgr._dispatch_agent_ws_output(
            {
                "payload": {
                    "session_id": session_id,
                    "messages": [f"m{i}"],
                    "closed": False,
                }
            }
        )
    assert queue.qsize() == cap
    # 最早的 5 帧被丢弃，队首应为 m5
    first = queue.get_nowait()
    assert first["messages"] == ["m5"]


@pytest.mark.asyncio
async def test_stop_pump_does_not_send_closed():
    """主动停止泵（close 流程/断连）不应再推 closed，由调用方负责。"""
    mgr = _make_manager()
    fake_ws = _FakeWS()
    mgr._ws = fake_ws
    session_id = "sess-cancel"
    agent_ws = _BlockingAgentWS()
    mgr._agent_ws_sessions[session_id] = agent_ws
    mgr._start_agent_ws_pump(session_id, agent_ws)

    await asyncio.sleep(0.02)
    mgr._stop_agent_ws_pump(session_id)
    await asyncio.sleep(0.05)

    assert [m for m in fake_ws.sent if m.get("type") == AGENT_WS_OUTPUT] == []
    assert session_id not in mgr._agent_ws_pumps
