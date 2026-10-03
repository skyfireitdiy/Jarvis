# -*- coding: utf-8 -*-
"""浏览器扩展 hello 上报 capabilities 的端到端回归测试。

守护目标：
1. 扩展首帧 hello 携带 ``capabilities`` 数组时必须被落库到会话；
2. ``list_sessions()`` / ``get_session()`` 返回中必须带 ``capabilities``；
3. 兼容旧版：hello 未携带 capabilities（或非 list）时回退为 ``[]``，不抛异常；
4. GET /api/browser-ext/sessions 端到端返回的 capabilities 与上报一致。

隔离：数据目录由 conftest.py 的 autouse fixture 重定向到 tmp_path；
全程使用 TestClient（ASGI 内存传输），不监听端口。
"""

import sys
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from jarvis.jarvis_web_gateway.app import create_app

EXT_SUBPROTOCOL = "jarvis-ext"


def _token_subprotocol(token: str) -> list:
    """构造携带 jarvis-token 的 WS 子协议列表（扩展用 jarvis-ext 子协议）。"""
    return [EXT_SUBPROTOCOL, "jarvis-token." + quote(token, safe="")]


@pytest.fixture
def client(auth_token):
    """构造隔离后的应用客户端；auth_token 决定 JARVIS_AUTH_TOKEN。"""
    app = create_app()
    with TestClient(app) as c:
        yield c


CAPS = [
    {
        "name": "tab.list",
        "description": "列出浏览器当前打开的标签页",
        "parameters": {},
        "platform": "browser",
    },
    {
        "name": "dom.click",
        "description": "点击页面元素",
        "parameters": {"selector": "string"},
        "platform": "browser",
    },
]


def test_hello_capabilities_persisted(client, auth_token):
    """hello 携带 capabilities 时，会话应落库并可从 list_sessions 读出。"""
    with client.websocket_connect(
        "/api/browser-ext/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        ws.send_json(
            {
                "type": "hello",
                "client_id": "ext-client-1",
                "extension_version": "6.0.7",
                "browser_info": {"name": "Edge", "version": "120"},
                "capabilities": CAPS,
                "tabs": [],
            }
        )
        # 读 hello_ack
        ack = ws.receive_json()
        assert ack["type"] == "hello_ack"

        # 通过 HTTP 接口读会话
        resp = client.get(
            "/api/browser-ext/sessions",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        sessions = resp.json()["sessions"]
        assert len(sessions) >= 1
        session = next(s for s in sessions if s["client_id"] == "ext-client-1")
        assert session["capabilities"] == CAPS


def test_hello_without_capabilities_falls_back_to_empty(client, auth_token):
    """旧版扩展 hello 未携带 capabilities 时，回退为 [] 不抛异常。"""
    with client.websocket_connect(
        "/api/browser-ext/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        ws.send_json(
            {
                "type": "hello",
                "client_id": "ext-client-legacy",
                "extension_version": "6.0.0",
                "browser_info": {"name": "Chrome"},
                "tabs": [],
            }
        )
        ack = ws.receive_json()
        assert ack["type"] == "hello_ack"

        resp = client.get(
            "/api/browser-ext/sessions",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        sessions = resp.json()["sessions"]
        assert len(sessions) >= 1
        session = next(s for s in sessions if s["client_id"] == "ext-client-legacy")
        assert session["capabilities"] == []
