# -*- coding: utf-8 -*-
"""终端名称（hello 帧 ``name`` 字段）的回归测试。

背景：用户在 Jarvis 网页设置页配置「终端名称」（默认值为计算机名），
该值随 daemon / 浏览器扩展的 hello 帧上报给网关，使网关/Agent 能以
可读名称识别终端。守护目标：

1. daemon hello 携带 ``name`` 时，会话应落库并可从 list_sessions/get_session 读出；
2. daemon hello 未携带 ``name`` 时，回退为 hostname（旧版 daemon 兼容）；
3. daemon hello 携带空/空白 ``name`` 时同样回退 hostname；
4. 浏览器扩展 hello 携带 ``name`` 时落库并可从 list_sessions/get_session 读出；
5. 浏览器扩展 hello 未携带 ``name`` 时返回空字符串（不报错）；
6. 浏览器扩展重连 hello 可刷新 ``name``。

隔离：数据目录由 ``conftest.py`` 的 autouse fixture 重定向到 tmp_path；
全程使用 TestClient（ASGI 内存传输），不监听端口。
"""

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


def _ext_subprotocol(token: str) -> list:
    """构造浏览器扩展端点的子协议列表（jarvis-ext + token）。"""
    from urllib.parse import quote

    return ["jarvis-ext", "jarvis-token." + quote(token, safe="")]


@pytest.fixture
def client(auth_token):
    """构造隔离后的应用客户端；auth_token 决定 JARVIS_AUTH_TOKEN。"""
    app = create_app()
    with TestClient(app) as c:
        yield c


# ----------------------------------------------------------------------
# 守护进程（daemon）侧
# ----------------------------------------------------------------------


def test_daemon_hello_name_persisted(client, auth_token):
    """daemon hello 携带 name 时，会话应落库并可从 list_sessions/get_session 读出。"""
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        ws.send_json(
            {
                "type": "hello",
                "client_id": "daemon-name-1",
                "extension_version": "0.0.1-test",
                "name": "SF-PC",
                "system_info": {"hostname": "sf-pc-host", "os_name": "Windows"},
                "tabs": [],
            }
        )
        ack = ws.receive_json()
        assert ack.get("type") == "hello_ack"

        manager = client.app.state.daemon_capability_manager
        sessions = manager.list_sessions()
        assert len(sessions) == 1
        session = sessions[0]
        # name 原样落库，且不被 hostname 覆盖
        assert session["name"] == "SF-PC"
        assert session["hostname"] == "sf-pc-host"

        # get_session 同样带 name
        detail = manager.get_session(session["session_id"])
        assert detail is not None
        assert detail["name"] == "SF-PC"


def test_daemon_hello_without_name_falls_back_to_hostname(client, auth_token):
    """兼容旧版：daemon hello 无 name 时，返回的 name 回退为 hostname。"""
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        ws.send_json(
            {
                "type": "hello",
                "client_id": "daemon-noname-1",
                "extension_version": "0.0.0-legacy",
                "system_info": {"hostname": "legacy-host", "os_name": "Linux"},
                "tabs": [],
            }
        )
        ack = ws.receive_json()
        assert ack.get("type") == "hello_ack"

        manager = client.app.state.daemon_capability_manager
        sessions = manager.list_sessions()
        assert len(sessions) == 1
        # 无 name 字段时回退 hostname
        assert sessions[0]["name"] == "legacy-host"
        detail = manager.get_session(sessions[0]["session_id"])
        assert detail is not None
        assert detail["name"] == "legacy-host"


def test_daemon_hello_blank_name_falls_back_to_hostname(client, auth_token):
    """daemon hello 携带空白 name 时，同样回退 hostname，不得落库空白串。"""
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        ws.send_json(
            {
                "type": "hello",
                "client_id": "daemon-blankname-1",
                "extension_version": "0.0.0",
                "name": "   ",
                "system_info": {"hostname": "blank-host", "os_name": "Linux"},
                "tabs": [],
            }
        )
        ack = ws.receive_json()
        assert ack.get("type") == "hello_ack"

        manager = client.app.state.daemon_capability_manager
        sessions = manager.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["name"] == "blank-host"


def test_daemon_list_sessions_without_name_returns_hostname():
    """未落库 name 的旧会话，list_sessions/get_session 的 name 应回退 hostname 而非 None。"""
    manager = DaemonCapabilityManager()
    manager._sessions["s1"] = {
        "websocket": None,
        "user_id": "u1",
        "client_id": "c1",
        "node_id": "c1",
        "hostname": "fallback-host",
        "platform": "",
        "capabilities": [],
        "connected_at": 0.0,
        "last_seen": 0.0,
    }
    sessions = manager.list_sessions()
    assert sessions[0]["name"] == "fallback-host"
    detail = manager.get_session("s1")
    assert detail is not None
    assert detail["name"] == "fallback-host"


# ----------------------------------------------------------------------
# 浏览器扩展侧
# ----------------------------------------------------------------------


def test_extension_hello_name_persisted(client, auth_token):
    """扩展 hello 携带 name 时，会话应落库并可从 list_sessions/get_session 读出。"""
    with client.websocket_connect(
        "/api/browser-ext/ws", subprotocols=_ext_subprotocol(auth_token)
    ) as ws:
        ws.send_json(
            {
                "type": "hello",
                "client_id": "ext-name-1",
                "extension_version": "0.0.1-test",
                "name": "SF-PC",
                "browser_info": {"user_agent": "UA", "platform": "Win32"},
                "tabs": [],
            }
        )
        ack = ws.receive_json()
        assert ack.get("type") == "hello_ack"

        manager = client.app.state.browser_extension_manager
        sessions = manager.list_sessions()
        assert len(sessions) == 1
        session = sessions[0]
        assert session["name"] == "SF-PC"

        detail = manager.get_session(session["session_id"])
        assert detail is not None
        assert detail["name"] == "SF-PC"


def test_extension_hello_without_name_returns_empty(client, auth_token):
    """兼容旧版：扩展 hello 无 name 时返回空字符串，不得抛异常。"""
    with client.websocket_connect(
        "/api/browser-ext/ws", subprotocols=_ext_subprotocol(auth_token)
    ) as ws:
        ws.send_json(
            {
                "type": "hello",
                "client_id": "ext-noname-1",
                "extension_version": "0.0.0-legacy",
                "browser_info": {"platform": "Win32"},
                "tabs": [],
            }
        )
        ack = ws.receive_json()
        assert ack.get("type") == "hello_ack"

        manager = client.app.state.browser_extension_manager
        sessions = manager.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["name"] == ""
        detail = manager.get_session(sessions[0]["session_id"])
        assert detail is not None
        assert detail["name"] == ""


def test_extension_reconnect_hello_refreshes_name(client, auth_token):
    """扩展重连后重新握手时，name 应被刷新为最新值。"""
    with client.websocket_connect(
        "/api/browser-ext/ws", subprotocols=_ext_subprotocol(auth_token)
    ) as ws:
        ws.send_json(
            {
                "type": "hello",
                "client_id": "ext-refresh-1",
                "extension_version": "0.0.1-test",
                "name": "old-name",
                "tabs": [],
            }
        )
        ack = ws.receive_json()
        assert ack.get("type") == "hello_ack"

        manager = client.app.state.browser_extension_manager
        session_id = manager.list_sessions()[0]["session_id"]
        assert manager.get_session(session_id)["name"] == "old-name"

        # 同一连接上再次发送 hello（重连握手），name 应刷新
        ws.send_json(
            {
                "type": "hello",
                "client_id": "ext-refresh-1",
                "extension_version": "0.0.1-test",
                "name": "new-name",
                "tabs": [],
            }
        )
        # 触发一次 ping/pong 以确认消息已被处理
        ws.send_json({"type": "ping"})
        pong = ws.receive_json()
        assert pong.get("type") == "pong"

        assert manager.get_session(session_id)["name"] == "new-name"
