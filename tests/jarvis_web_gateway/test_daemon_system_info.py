# -*- coding: utf-8 -*-
"""守护进程 hello 上报 system_info 的回归测试。

守护目标：
1. daemon 首帧 hello 中的 ``system_info`` 必须被落库到会话；
2. ``hostname`` / ``platform`` 从 ``system_info`` 中取（platform 取 os_name）；
3. ``list_sessions()`` / ``get_session()`` 返回中必须带 ``system_info``；
4. 兼容旧版：``system_info`` 缺失时回退到 ``browser_info`` 的 hostname/platform，
   且不得抛异常。

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


@pytest.fixture
def client(auth_token):
    """构造隔离后的应用客户端；auth_token 决定 JARVIS_AUTH_TOKEN。"""
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_hello_system_info_persisted(client, auth_token):
    """hello 携带 system_info 时，会话应落库并可从 list_sessions 读出。"""
    system_info = {
        "hostname": "test-host",
        "kernel": "6.8.0-test",
        "os_name": "Ubuntu",
        "os_version": "24.04",
        "arch": "amd64",
        "cpu_count": 8,
        "cpu_model": "Test CPU",
        "mem_total_kb": 16000000,
        "mem_available_kb": 8000000,
        "uptime_sec": 12345,
        "user": "tester",
        "home": "/home/tester",
    }
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        ws.send_json(
            {
                "type": "hello",
                "client_id": "daemon-test-host-1",
                "extension_version": "0.0.1-test",
                "system_info": system_info,
                "tabs": [],
            }
        )
        ack = ws.receive_json()
        assert ack.get("type") == "hello_ack"

        sessions = client.app.state.daemon_capability_manager.list_sessions()
        assert len(sessions) == 1
        session = sessions[0]
        # system_info 原样落库
        assert session["system_info"] == system_info
        # hostname 取自 system_info
        assert session["hostname"] == "test-host"
        # platform 取自 system_info 的 os_name
        assert session["platform"] == "Ubuntu"
        # 既有字段未受影响
        assert session["client_id"] == "daemon-test-host-1"
        assert session["daemon_version"] == "0.0.1-test"

        # get_session 同样带 system_info
        detail = client.app.state.daemon_capability_manager.get_session(
            session["session_id"]
        )
        assert detail is not None
        assert detail["system_info"] == system_info


def test_hello_without_system_info_falls_back_to_browser_info(client, auth_token):
    """兼容旧版：无 system_info 时回退到 browser_info，且不抛异常。"""
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        ws.send_json(
            {
                "type": "hello",
                "client_id": "daemon-legacy-1",
                "extension_version": "0.0.0-legacy",
                "browser_info": {"hostname": "legacy-host", "platform": "linux"},
                "tabs": [],
            }
        )
        ack = ws.receive_json()
        assert ack.get("type") == "hello_ack"

        sessions = client.app.state.daemon_capability_manager.list_sessions()
        assert len(sessions) == 1
        session = sessions[0]
        assert session["system_info"] == {}
        assert session["hostname"] == "legacy-host"
        assert session["platform"] == "linux"


def test_hello_with_invalid_system_info_type(client, auth_token):
    """system_info 类型非法（非 dict）时应被规整为空 dict，不得抛异常。"""
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        ws.send_json(
            {
                "type": "hello",
                "client_id": "daemon-badtype-1",
                "extension_version": "0.0.0",
                "system_info": "not-a-dict",
                "tabs": [],
            }
        )
        ack = ws.receive_json()
        assert ack.get("type") == "hello_ack"

        sessions = client.app.state.daemon_capability_manager.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["system_info"] == {}


def test_list_sessions_without_system_info_returns_empty_dict():
    """未上报 system_info 的会话，list_sessions 应返回空 dict 而非 None。"""
    manager = DaemonCapabilityManager()
    manager._sessions["s1"] = {
        "websocket": None,
        "user_id": "u1",
        "client_id": "c1",
        "node_id": "c1",
        "hostname": "",
        "platform": "",
        "daemon_version": "0.0.0",
        "capabilities": [],
        "connected_at": 0.0,
        "last_seen": 0.0,
    }
    sessions = manager.list_sessions()
    assert sessions[0]["system_info"] == {}
    detail = manager.get_session("s1")
    assert detail is not None
    assert detail["system_info"] == {}


def test_hello_build_info_persisted(client, auth_token):
    """hello 携带 build_info 时，会话应落库并可从 list_sessions/get_session 读出。

    build_info 由新版 daemon 上报（含编译时间），供网关判断「当前运行的是哪一版、
    何时编译的」。旧版 daemon 不带该字段，见下一个用例。
    """
    build_info = {
        "version": "v5.0.6",
        "build_time": "2026-09-26T15:00:00Z",
        "build_time_unix": 1789000000,
        "build_time_source": "exe_mtime",
        "go_version": "go1.27.1",
        "os": "windows",
        "arch": "amd64",
        "exe_path": r"D:\jarvis-daemon.exe",
    }
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        ws.send_json(
            {
                "type": "hello",
                "client_id": "daemon-buildinfo-1",
                "extension_version": "v5.0.6",
                "build_info": build_info,
                "tabs": [],
            }
        )
        ack = ws.receive_json()
        assert ack.get("type") == "hello_ack"
        manager = client.app.state.daemon_capability_manager
        sessions = manager.list_sessions()
        assert len(sessions) == 1
        session = sessions[0]
        # build_info 原样落库
        assert session["build_info"] == build_info
        # 编译时间可读出
        assert session["build_info"]["build_time"] == "2026-09-26T15:00:00Z"
        assert session["build_info"]["build_time_source"] == "exe_mtime"
        # get_session 同样带 build_info
        detail = manager.get_session(session["session_id"])
        assert detail is not None
        assert detail["build_info"] == build_info


def test_hello_without_build_info_returns_empty_dict(client, auth_token):
    """兼容旧版：无 build_info 时应回退为空 dict，不得抛异常。"""
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        ws.send_json(
            {
                "type": "hello",
                "client_id": "daemon-nobuildinfo-1",
                "extension_version": "0.0.0-legacy",
                "tabs": [],
            }
        )
        ack = ws.receive_json()
        assert ack.get("type") == "hello_ack"
        manager = client.app.state.daemon_capability_manager
        sessions = manager.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["build_info"] == {}


def test_hello_with_invalid_build_info_type(client, auth_token):
    """build_info 类型非法（非 dict）时应被规整为空 dict，不得抛异常。"""
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        ws.send_json(
            {
                "type": "hello",
                "client_id": "daemon-badbuildinfo-1",
                "extension_version": "0.0.0",
                "build_info": "not-a-dict",
                "tabs": [],
            }
        )
        ack = ws.receive_json()
        assert ack.get("type") == "hello_ack"
        manager = client.app.state.daemon_capability_manager
        sessions = manager.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["build_info"] == {}


def test_list_sessions_without_build_info_returns_empty_dict():
    """未上报 build_info 的会话，list_sessions/get_session 应返回空 dict 而非 None。"""
    manager = DaemonCapabilityManager()
    manager._sessions["s1"] = {
        "websocket": None,
        "user_id": "u1",
        "client_id": "c1",
        "node_id": "c1",
        "hostname": "",
        "platform": "",
        "daemon_version": "0.0.0",
        "capabilities": [],
        "connected_at": 0.0,
        "last_seen": 0.0,
    }
    sessions = manager.list_sessions()
    assert sessions[0]["build_info"] == {}
    detail = manager.get_session("s1")
    assert detail is not None
    assert detail["build_info"] == {}


def test_system_info_update_merges_into_session(client, auth_token):
    """hello 后补发的 system_info_update 应合并进会话缓存。

    背景：hello 首帧只带「快速版」系统信息（避免握手超时），完整信息随后用
    system_info_update 补发。网关需合并（而非覆盖），使派生字段 hostname/platform
    同步刷新。
    """
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        # hello 只带零成本字段（快速版）。
        ws.send_json(
            {
                "type": "hello",
                "client_id": "daemon-fast-1",
                "extension_version": "0.0.1-test",
                "system_info": {"hostname": "fast-host", "arch": "amd64"},
                "tabs": [],
            }
        )
        ack = ws.receive_json()
        assert ack.get("type") == "hello_ack"

        # 随后补发完整系统信息。
        ws.send_json(
            {
                "type": "system_info_update",
                "system_info": {
                    "os_name": "Windows 10 Pro",
                    "os_version": "10.0.19045",
                    "mem_total_kb": 16000000,
                },
            }
        )
        # 再发一条 hello_ack 无关消息确保 update 已被处理（用 ping/pong 同步）。
        ws.send_json({"type": "ping"})
        pong = ws.receive_json()
        assert pong.get("type") == "pong"

        manager = client.app.state.daemon_capability_manager
        sessions = manager.list_sessions()
        assert len(sessions) == 1
        session = sessions[0]
        # 合并结果应同时含 hello 的快速字段与 update 的完整字段。
        assert session["system_info"]["hostname"] == "fast-host"
        assert session["system_info"]["arch"] == "amd64"
        assert session["system_info"]["os_name"] == "Windows 10 Pro"
        assert session["system_info"]["mem_total_kb"] == 16000000
        # 派生字段 platform 应随 os_name 刷新。
        assert session["platform"] == "Windows 10 Pro"


def test_system_info_update_ignored_when_not_dict(client, auth_token):
    """system_info_update 的 system_info 非 dict 时应安全忽略，不抛异常、不污染会话。"""
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        ws.send_json(
            {
                "type": "hello",
                "client_id": "daemon-badupd-1",
                "extension_version": "0.0.1-test",
                "system_info": {"hostname": "keep-host"},
                "tabs": [],
            }
        )
        ack = ws.receive_json()
        assert ack.get("type") == "hello_ack"

        # 非法 update：system_info 是字符串而非 dict。
        ws.send_json({"type": "system_info_update", "system_info": "not-a-dict"})
        # 用 ping/pong 同步，确保非法消息已被处理且连接未断。
        ws.send_json({"type": "ping"})
        pong = ws.receive_json()
        assert pong.get("type") == "pong"

        manager = client.app.state.daemon_capability_manager
        sessions = manager.list_sessions()
        assert len(sessions) == 1
        # 会话原 system_info 未被污染。
        assert sessions[0]["system_info"] == {"hostname": "keep-host"}
