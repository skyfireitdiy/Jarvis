# -*- coding: utf-8 -*-
"""守护进程「同机器旧连接自动清理」的回归测试。

守护目标：
1. daemon 重启后 client_id 变化（含 PID），同一台机器（同 user_id + 同 hostname）
   的新连接必须顶掉旧连接，list_sessions 不得出现幽灵条目；
2. 不同 hostname 的连接必须并存，不得互相清理；
3. hostname 为空时无法识别身份，不得做任何清理（避免误杀）；
4. 被替换的旧会话若有挂起调用，其 Future 必须被置为异常，避免调用方永久等待。

隔离：数据目录由 ``conftest.py`` 的 autouse fixture 重定向到 tmp_path；
全程使用 TestClient（ASGI 内存传输），不监听端口。
"""

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from jarvis.jarvis_web_gateway.app import create_app
from jarvis.jarvis_web_gateway.daemon_capability_manager import (
    DAEMON_SUBPROTOCOL,
    DaemonCapabilityManager,
)


def _token_subprotocol(token: str) -> list:
    """构造携带 jarvis-token 的 WS 子协议列表。"""
    from urllib.parse import quote

    return [DAEMON_SUBPROTOCOL, "jarvis-token." + quote(token, safe="")]


@pytest.fixture
def client(auth_token):
    """构造隔离后的应用客户端；auth_token 决定 JARVIS_AUTH_TOKEN。"""
    app = create_app()
    with TestClient(app) as c:
        yield c


def _hello(client_id: str, hostname: str = "", **extra) -> dict:
    """构造 daemon hello 帧；hostname 非空时放入 system_info。"""
    frame: dict = {
        "type": "hello",
        "client_id": client_id,
        "extension_version": "0.0.1-test",
        "tabs": [],
    }
    if hostname:
        frame["system_info"] = {"hostname": hostname, "os_name": "Ubuntu"}
    frame.update(extra)
    return frame


def test_new_connection_replaces_same_host_session(client, auth_token):
    """同 hostname 的新连接应顶掉旧连接，list_sessions 只剩最新一条。"""
    manager = client.app.state.daemon_capability_manager
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws1:
        ws1.send_json(_hello("daemon-host-1001", hostname="same-host"))
        assert ws1.receive_json().get("type") == "hello_ack"
        assert len(manager.list_sessions()) == 1
        old_session_id = manager.list_sessions()[0]["session_id"]

        # 模拟 daemon 重启：client_id 因 PID 变化而不同，hostname 不变
        with client.websocket_connect(
            "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
        ) as ws2:
            ws2.send_json(_hello("daemon-host-2002", hostname="same-host"))
            assert ws2.receive_json().get("type") == "hello_ack"

            sessions = manager.list_sessions()
            assert len(sessions) == 1, f"旧会话未被清理: {sessions}"
            assert sessions[0]["client_id"] == "daemon-host-2002"
            assert sessions[0]["session_id"] != old_session_id
            # 旧会话已从表中移除
            assert manager.get_session(old_session_id) is None


def test_different_host_not_replaced(client, auth_token):
    """不同 hostname 的连接应并存，不得互相清理。"""
    manager = client.app.state.daemon_capability_manager
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws1:
        ws1.send_json(_hello("daemon-hostA-1", hostname="host-a"))
        assert ws1.receive_json().get("type") == "hello_ack"

        with client.websocket_connect(
            "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
        ) as ws2:
            ws2.send_json(_hello("daemon-hostB-1", hostname="host-b"))
            assert ws2.receive_json().get("type") == "hello_ack"

            sessions = manager.list_sessions()
            assert len(sessions) == 2
            hostnames = {s["hostname"] for s in sessions}
            assert hostnames == {"host-a", "host-b"}


def test_empty_hostname_not_replaced(client, auth_token):
    """hostname 为空的连接无法识别身份，应并存而非互相清理。"""
    manager = client.app.state.daemon_capability_manager
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws1:
        ws1.send_json(_hello("daemon-nohost-1"))
        assert ws1.receive_json().get("type") == "hello_ack"

        with client.websocket_connect(
            "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
        ) as ws2:
            ws2.send_json(_hello("daemon-nohost-2"))
            assert ws2.receive_json().get("type") == "hello_ack"

            sessions = manager.list_sessions()
            assert len(sessions) == 2, f"空 hostname 不应被清理: {sessions}"


def test_replacement_fails_pending_calls():
    """被替换的旧会话若有挂起调用，其 Future 必须被置为异常。"""
    manager = DaemonCapabilityManager()

    async def _run() -> None:
        loop = asyncio.get_running_loop()
        # 构造一个「旧会话」，带一个挂起的能力调用
        manager._sessions["old-session"] = {
            "websocket": None,
            "user_id": "u1",
            "client_id": "daemon-host-1001",
            "node_id": "daemon-host-1001",
            "hostname": "same-host",
            "platform": "Ubuntu",
            "system_info": {"hostname": "same-host"},
            "daemon_version": "0.0.1",
            "capabilities": [],
            "connected_at": 0.0,
            "last_seen": 0.0,
        }
        pending: asyncio.Future = loop.create_future()
        setattr(pending, "_daemon_session", "old-session")
        manager._pending_calls["call-1"] = pending

        await manager._replace_stale_sessions("new-session", "u1", "same-host")

        assert "old-session" not in manager._sessions
        assert pending.done()
        with pytest.raises(RuntimeError, match="disconnected"):
            pending.result()
        assert "call-1" not in manager._pending_calls

    asyncio.run(_run())
