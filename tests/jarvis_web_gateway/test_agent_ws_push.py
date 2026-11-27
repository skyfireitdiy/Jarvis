# -*- coding: utf-8 -*-
"""Agent WS 推送模式测试。

重点：child 侧推送泵必须通过 ChildNodeClient 显式注入的连接获取器
（set_child_connection_provider）拿到 child->master 连接。历史事故：
泵曾用 getattr(self, "_ws") 取连接，而 _ws 属于 ChildNodeClient、
NodeConnectionManager 上不存在，取值恒为 None，所有推送被静默丢弃，
导致远端 Agent 与前端完全不通。

因此本文件所有涉及「推送泵取连接」的用例，都必须通过真实装配路径：
构造 NodeConnectionManager + 真实 ChildNodeClient，由后者注入 provider，
绝不手工给 manager 塞 _ws。
"""
import os

os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from jarvis.jarvis_web_gateway import node_manager as nm
from jarvis.jarvis_web_gateway.node_manager import (
    ChildNodeClient,
    NodeConnectionManager,
)
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
    """模拟 agent 侧 websocket：async for 逐个产出预置消息后结束。"""

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


class _BlockingAgentWS:
    """永不产出消息的 agent_ws，用于测试泵处于等待态时的取消。"""

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.Event().wait()
        raise StopAsyncIteration

    async def close(self):
        pass


class _FakeMasterConn:
    """模拟 child->master 连接，记录 send 的原始 JSON。"""

    def __init__(self):
        self.sent = []

    async def send(self, raw):
        self.sent.append(json.loads(raw))


def _outputs(conn):
    return [m for m in conn.sent if m.get("type") == AGENT_WS_OUTPUT]


# ---------------------------------------------------------------------------
# 1. 核心回归：provider 由真实 ChildNodeClient 注入，推送能真正发出去
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pump_sends_output_via_child_client_injected_provider():
    mgr = _make_manager()
    # 真实装配路径：ChildNodeClient 构造时注入 provider
    child = ChildNodeClient(
        node_runtime=mgr._node_runtime,
        agent_manager=mgr._agent_manager,
        agent_proxy_manager=mgr._agent_proxy_manager,
        node_connection_manager=mgr,
    )
    conn = _FakeMasterConn()
    child._ws = conn  # 模拟连接已建立（provider 读取的就是这个属性）

    session_id = "sess-real"
    agent_ws = _FakeAgentWS(['{"t": 1}', '{"t": 2}'])
    mgr._agent_ws_sessions[session_id] = agent_ws
    mgr._start_agent_ws_pump(session_id, agent_ws)

    for _ in range(100):
        await asyncio.sleep(0.01)
        if len(_outputs(conn)) >= 3:
            break

    outs = _outputs(conn)
    assert len(outs) == 3, f"推送未发出，实际={conn.sent}"
    assert outs[0]["payload"]["messages"] == ['{"t": 1}']
    assert outs[1]["payload"]["messages"] == ['{"t": 2}']
    assert outs[2]["payload"]["closed"] is True
    assert all(o["payload"]["session_id"] == session_id for o in outs)
    assert session_id not in mgr._agent_ws_pumps


@pytest.mark.asyncio
async def test_provider_reflects_reconnect():
    """provider 是 lambda: self._ws，断线重连换新连接后应发到新连接。"""
    mgr = _make_manager()
    child = ChildNodeClient(
        node_runtime=mgr._node_runtime,
        agent_manager=mgr._agent_manager,
        agent_proxy_manager=mgr._agent_proxy_manager,
        node_connection_manager=mgr,
    )
    old_conn = _FakeMasterConn()
    child._ws = old_conn
    new_conn = _FakeMasterConn()
    child._ws = new_conn  # 模拟重连后替换连接

    await mgr._send_agent_ws_output("s", ["m"], closed=False)
    assert _outputs(old_conn) == []
    assert len(_outputs(new_conn)) == 1


@pytest.mark.asyncio
async def test_no_provider_means_no_send_and_no_crash():
    """master 侧（未注入 provider）调用推送应安全返回。"""
    mgr = _make_manager()
    assert mgr._child_connection_provider is None
    await mgr._send_agent_ws_output("s", ["m"], closed=False)  # 不应抛异常


# ---------------------------------------------------------------------------
# 2. 推送模式下 RECV 不抢占 agent_ws
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recv_request_does_not_steal_when_pump_active():
    mgr = _make_manager()
    child = ChildNodeClient(
        node_runtime=mgr._node_runtime,
        agent_manager=mgr._agent_manager,
        agent_proxy_manager=mgr._agent_proxy_manager,
        node_connection_manager=mgr,
    )
    child._ws = _FakeMasterConn()

    session_id = "sess-recv"
    agent_ws = _BlockingAgentWS()
    mgr._agent_ws_sessions[session_id] = agent_ws
    mgr._start_agent_ws_pump(session_id, agent_ws)
    try:
        resp = await mgr._handle_agent_ws_recv_request(
            {"payload": {"session_id": session_id, "timeout": 0.01}, "request_id": "r1"}
        )
        payload = resp["payload"]
        assert payload["success"] is True
        assert payload["push_mode"] is True
        assert payload["messages"] == []
    finally:
        mgr._stop_agent_ws_pump(session_id)


# ---------------------------------------------------------------------------
# 3. master 侧分发
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dispatch_output_to_subscriber_queue():
    mgr = _make_manager()
    session_id = "sess-disp"
    queue = mgr.subscribe_agent_ws_output(session_id)

    mgr._dispatch_agent_ws_output(
        {
            "payload": {"session_id": session_id, "messages": ["m1"], "closed": False}
        }
    )
    mgr._dispatch_agent_ws_output(
        {"payload": {"session_id": session_id, "messages": [], "closed": True}}
    )

    assert await asyncio.wait_for(queue.get(), 1) == {
        "messages": ["m1"],
        "closed": False,
    }
    assert await asyncio.wait_for(queue.get(), 1) == {"messages": [], "closed": True}

    mgr.unsubscribe_agent_ws_output(session_id)
    assert session_id not in mgr._agent_ws_output_queues


def test_dispatch_without_subscriber_is_safe():
    mgr = _make_manager()
    mgr._dispatch_agent_ws_output(
        {"payload": {"session_id": "nobody", "messages": ["x"], "closed": False}}
    )
    mgr._dispatch_agent_ws_output({"payload": {}})


def test_bounded_queue_drops_oldest_when_full():
    mgr = _make_manager()
    session_id = "sess-bp"
    queue = mgr.subscribe_agent_ws_output(session_id)
    cap = nm._AGENT_WS_OUTPUT_QUEUE_MAX
    assert queue.maxsize == cap

    for i in range(cap + 5):
        mgr._dispatch_agent_ws_output(
            {"payload": {"session_id": session_id, "messages": [f"m{i}"], "closed": False}}
        )
    assert queue.qsize() == cap
    assert queue.get_nowait()["messages"] == ["m5"]


# ---------------------------------------------------------------------------
# 4. 取消与清理
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stop_pump_does_not_send_closed():
    mgr = _make_manager()
    child = ChildNodeClient(
        node_runtime=mgr._node_runtime,
        agent_manager=mgr._agent_manager,
        agent_proxy_manager=mgr._agent_proxy_manager,
        node_connection_manager=mgr,
    )
    conn = _FakeMasterConn()
    child._ws = conn

    session_id = "sess-cancel"
    agent_ws = _BlockingAgentWS()
    mgr._agent_ws_sessions[session_id] = agent_ws
    mgr._start_agent_ws_pump(session_id, agent_ws)

    await asyncio.sleep(0.02)
    mgr._stop_agent_ws_pump(session_id)
    await asyncio.sleep(0.05)

    assert _outputs(conn) == []
    assert session_id not in mgr._agent_ws_pumps


def test_stop_all_pumps_clears_state():
    mgr = _make_manager()
    mgr._agent_ws_sessions["a"] = MagicMock()
    mgr._agent_ws_sessions["b"] = MagicMock()
    mgr._agent_ws_pumps["a"] = MagicMock(done=lambda: True)
    mgr._agent_ws_pumps["b"] = MagicMock(done=lambda: True)
    mgr._stop_all_agent_ws_pumps()
    assert mgr._agent_ws_pumps == {}
    assert mgr._agent_ws_sessions == {}
# ---------------------------------------------------------------------------
# 5. 重连竞态：旧连接的清理不得误杀新连接的推送泵
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stop_all_pumps_only_clears_own_connection():
    mgr = _make_manager()
    child = ChildNodeClient(
        node_runtime=mgr._node_runtime,
        agent_manager=mgr._agent_manager,
        agent_proxy_manager=mgr._agent_proxy_manager,
        node_connection_manager=mgr,
    )
    conn = _FakeMasterConn()
    child._ws = conn
    # 旧连接上启动的泵
    mgr._current_connection_id = "old-conn"
    mgr._agent_ws_sessions["old"] = _BlockingAgentWS()
    mgr._start_agent_ws_pump("old", mgr._agent_ws_sessions["old"])
    # 重连后新连接上启动的泵
    mgr._current_connection_id = "new-conn"
    mgr._agent_ws_sessions["new"] = _BlockingAgentWS()
    mgr._start_agent_ws_pump("new", mgr._agent_ws_sessions["new"])
    await asyncio.sleep(0.02)
    # 旧连接的 finally 迟到执行：只应清理旧泵
    mgr._stop_all_agent_ws_pumps("old-conn")
    await asyncio.sleep(0.02)
    assert "old" not in mgr._agent_ws_pumps
    assert "new" in mgr._agent_ws_pumps
    assert "new" in mgr._agent_ws_sessions
    # 新连接断开时才清理新泵
    mgr._stop_all_agent_ws_pumps("new-conn")
    assert mgr._agent_ws_pumps == {}
    assert mgr._agent_ws_sessions == {}
