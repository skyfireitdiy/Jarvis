# -*- coding: utf-8 -*-
"""网关 WebSocket 端点鉴权回归测试。

守护目标：所有对外 WS 端点都必须在「未携带 Token」时拒绝连接，
不得出现「无 token 也放行」的兜底逻辑（历史缺陷：
``else: authorized = any(auth is not None for auth in manager._auth_store.values())``）。

覆盖端点：
- ``/api/lsp/{server_id}``           语言服务器桥接
- ``/api/browser-ext/ws``            浏览器扩展
- ``/api/daemon/ws``                 守护进程
- ``/api/agent/{agent_id}/ws``       Agent 代理
- ``/api/node/{node_id}/agent/{agent_id}/ws``  跨节点 Agent 代理

断言口径：拒绝时服务端先发 ``{"type":"error","payload":{"code":"AUTH_FAILED"}}``，
随后以 close code ``4401`` 关闭；「带有效 token」则必须越过鉴权，
表现为得到与鉴权无关的业务错误码（4404/4000 等），而非 4401。

**为什么必须先建立一条已认证连接（关键）**：
``create_app()`` 里的 ``auth_store`` 初始为空 ``{}``，只有认证成功的连接
才会写入（``app.py`` 的 ``WebSocketConnectionManager.handle`` 中
``self._auth_store[session_id] = auth_payload``）。历史缺陷的兜底表达式
``any(a is not None for a in gateway._auth_store.values())`` 在空 store 上
恒为 ``False``，因此**若不先让 store 非空，缺陷不可达、测试形同虚设**。
``authenticated_session`` fixture 就是为此：先连一条合法连接使 store 非空，
后续「无 token 应被拒」的断言才真正具备杀伤力。

隔离：数据目录由 ``tests/jarvis_web_gateway/conftest.py`` 的 autouse fixture
重定向到 tmp_path；全程使用 TestClient（ASGI 内存传输），不监听端口。
"""

import sys
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from jarvis.jarvis_web_gateway.app import create_app

AUTH_FAILED_CODE = "AUTH_FAILED"
WS_UNAUTHORIZED_CLOSE = 4401


def _token_subprotocol(token: str) -> list:
    """构造携带 jarvis-token 的 WS 子协议列表。"""
    return ["jarvis-ws", "jarvis-token." + quote(token, safe="")]


@pytest.fixture
def client(auth_token):
    """构造隔离后的应用客户端；auth_token 决定 JARVIS_AUTH_TOKEN。"""
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def authenticated_session(client, auth_token):
    """先建立一条已认证连接，使 ``gateway._auth_store`` 非空。

    这是让「无 token 兜底放行」缺陷可达的前提：空 store 下
    ``any(...)`` 恒为 False，缺陷无法被触发，测试会假绿。

    必须用 ``/ws`` 端点：只有它走 ``WebSocketConnectionManager.handle``，
    才会在鉴权通过后执行 ``self._auth_store[session_id] = auth_payload``
    （app.py 约 884 行）。lsp / browser-ext / daemon / agent 等端点各自
    独立鉴权，**不会**写 ``_auth_store``，用它们建立连接 store 仍为空。
    """
    with client.websocket_connect(
        "/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"
        yield ws


def _expect_rejected_without_token(client: TestClient, url: str) -> None:
    """断言：不带 token 连接该 WS 端点会被 4401 拒绝。"""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(url) as ws:
            message = ws.receive_json()
            assert message["type"] == "error"
            assert message["payload"]["code"] == AUTH_FAILED_CODE
            ws.receive_text()  # 触发服务端 close
    assert exc_info.value.code == WS_UNAUTHORIZED_CLOSE


# --- 无 token：必须全部拒绝（store 非空，兜底缺陷可达）------------------------


def test_lsp_ws_rejects_without_token(client, authenticated_session):
    _expect_rejected_without_token(client, "/api/lsp/pyright")


def test_browser_ext_ws_rejects_without_token(client, authenticated_session):
    _expect_rejected_without_token(client, "/api/browser-ext/ws")


def test_daemon_ws_rejects_without_token(client, authenticated_session):
    _expect_rejected_without_token(client, "/api/daemon/ws")


def test_agent_ws_rejects_without_token(client, authenticated_session):
    _expect_rejected_without_token(client, "/api/agent/ghost-agent/ws")


def test_remote_node_agent_ws_rejects_without_token(client, authenticated_session):
    _expect_rejected_without_token(
        client, "/api/node/some-remote-node/agent/ghost-agent/ws"
    )


# --- 带有效 token：必须越过鉴权 ---------------------------------------------


def test_lsp_ws_with_valid_token_passes_auth(client, auth_token):
    """带有效 token 时不应再被 4401 拒绝，而是因 server_id 非法返回 4404。"""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            "/api/lsp/definitely-not-a-server",
            subprotocols=_token_subprotocol(auth_token),
        ) as ws:
            message = ws.receive_json()
            assert message["payload"]["code"] == "UNKNOWN_SERVER"
            ws.receive_text()
    assert exc_info.value.code == 4404


def test_agent_ws_with_valid_token_passes_auth(client, auth_token):
    """带有效 token 时越过鉴权，因 agent 不存在返回 4000（而非 4401）。"""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            "/api/agent/ghost-agent/ws",
            subprotocols=_token_subprotocol(auth_token),
        ) as ws:
            ws.receive_text()
    assert exc_info.value.code == 4000


def test_invalid_token_is_rejected(client, authenticated_session):
    """伪造 token 同样必须被 4401 拒绝（不能因「存在任意 token」而放行）。"""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            "/api/agent/ghost-agent/ws",
            subprotocols=_token_subprotocol("forged-token-not-valid"),
        ) as ws:
            message = ws.receive_json()
            assert message["payload"]["code"] == AUTH_FAILED_CODE
            ws.receive_text()
    assert exc_info.value.code == WS_UNAUTHORIZED_CLOSE


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
