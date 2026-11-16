# -*- coding: utf-8 -*-
"""子节点终端输出广播到 admin 用户的单元测试。

覆盖 NodeConnectionManager._publish_terminal_output_to_admins：
1. 子节点终端的输出应广播给所有 admin 用户（ACL 决策统一在 master）
2. 排除发起者 session_id，避免重复推送
3. 无 terminal_session_manager 时安全返回
"""

import os

# 必须在导入 jarvis 模块之前设置环境变量，避免触发交互式配置
os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"

import asyncio
import base64

from unittest.mock import MagicMock

from jarvis.jarvis_web_gateway.node_manager import (
    ChildNodeClient,
    NodeConnectionManager,
)


def _make_manager(admin_sids, router=None):
    """构造一个带 mock terminal_session_manager 的 NodeConnectionManager。"""
    tsm = MagicMock()
    tsm.get_all_admin_session_ids.return_value = admin_sids
    return NodeConnectionManager(
        node_runtime=MagicMock(),
        agent_manager=MagicMock(),
        agent_proxy_manager=MagicMock(),
        node_http_dispatcher=None,
        router=router or MagicMock(),
        terminal_session_manager=tsm,
    )


def test_publish_terminal_output_broadcasts_to_all_admins():
    """子节点终端输出应广播给所有 admin 用户。"""
    published = []

    class FakeRouter:
        def publish(self, message, session_id=None, connection_id=None):
            published.append(session_id)

    m = _make_manager(["session_admin-a", "session_admin-b"], router=FakeRouter())
    m._publish_terminal_output_to_admins({"type": "execution"}, "session_owner1")

    assert "session_admin-a" in published
    assert "session_admin-b" in published


def test_publish_terminal_output_excludes_initiator():
    """广播时应排除发起者 session_id，避免重复推送。"""
    published = []

    class FakeRouter:
        def publish(self, message, session_id=None, connection_id=None):
            published.append(session_id)

    # 发起者本身也是 admin
    m = _make_manager(["session_admin-a", "session_admin-b"], router=FakeRouter())
    m._publish_terminal_output_to_admins({"type": "execution"}, "session_admin-a")

    assert "session_admin-a" not in published
    assert "session_admin-b" in published


def test_publish_terminal_output_no_manager_is_safe():
    """无 terminal_session_manager 时应安全返回，不抛异常。"""
    m = NodeConnectionManager(
        node_runtime=MagicMock(),
        agent_manager=MagicMock(),
        agent_proxy_manager=MagicMock(),
        node_http_dispatcher=None,
        router=MagicMock(),
        terminal_session_manager=None,
    )
    # 不应抛异常
    m._publish_terminal_output_to_admins({"type": "execution"}, "session_owner1")


def _make_child_client(tsm):
    """构造一个带 mock terminal_session_manager 的 ChildNodeClient（子节点侧）。"""
    ncm = MagicMock()
    ncm._terminal_session_manager = tsm
    return ChildNodeClient(
        node_runtime=MagicMock(),
        agent_manager=MagicMock(),
        agent_proxy_manager=MagicMock(),
        node_connection_manager=ncm,
    )


def _attach_message(terminal_id, request_id="req-1"):
    return {
        "request_id": request_id,
        "payload": {
            "action": "terminal_attach",
            "session_id": "default",
            "payload": {"terminal_id": terminal_id},
        },
    }


def test_child_terminal_attach_returns_output_buffer():
    """子节点 terminal_attach 应返回输出缓冲（base64 列表）。"""
    chunk1 = b"hello "
    chunk2 = b"world\n"
    session = MagicMock()
    session.interpreter = "bash"
    session.working_dir = "/home/user"
    session.get_output_buffer.return_value = [chunk1, chunk2]

    tsm = MagicMock()
    tsm.get_session.return_value = session

    client = _make_child_client(tsm)
    resp = asyncio.run(client._handle_node_terminal_request(_attach_message("term-1")))

    payload = resp["payload"]
    assert payload["success"] is True
    data = payload["data"]
    assert data["terminal_id"] == "term-1"
    assert data["interpreter"] == "bash"
    assert data["working_dir"] == "/home/user"
    assert data["output"] == [
        base64.b64encode(chunk1).decode("utf-8"),
        base64.b64encode(chunk2).decode("utf-8"),
    ]
    tsm.get_session.assert_called_once_with("term-1")


def test_child_terminal_attach_missing_session_returns_not_found():
    """子节点 terminal_attach 找不到会话时应返回 NOT_FOUND。"""
    tsm = MagicMock()
    tsm.get_session.return_value = None

    client = _make_child_client(tsm)
    resp = asyncio.run(
        client._handle_node_terminal_request(_attach_message("missing-term"))
    )

    payload = resp["payload"]
    assert payload["success"] is False
    assert payload["error"]["code"] == "NOT_FOUND"


def test_child_terminal_attach_empty_terminal_id_returns_not_found():
    """子节点 terminal_attach 空 terminal_id 时应返回 NOT_FOUND。"""
    tsm = MagicMock()

    client = _make_child_client(tsm)
    resp = asyncio.run(client._handle_node_terminal_request(_attach_message("")))

    payload = resp["payload"]
    assert payload["success"] is False
    assert payload["error"]["code"] == "NOT_FOUND"
    # 空 terminal_id 不应调用 get_session
    tsm.get_session.assert_not_called()


# ---------------------------------------------------------------------------
# 子节点终端进程自行退出（event_type=closed）→ 前端 terminal_closed
# ---------------------------------------------------------------------------


def _closed_event(terminal_id="t1"):
    return {
        "type": "execution",
        "payload": {
            "event_type": "closed",
            "data": "",
            "encoded": True,
            "sequence": 5,
            "execution_id": f"terminal_{terminal_id}",
        },
    }


def test_is_terminal_closed_event():
    """仅 event_type=closed 判定为退出通知。"""
    assert NodeConnectionManager._is_terminal_closed_event(_closed_event())
    assert not NodeConnectionManager._is_terminal_closed_event(
        {"type": "execution", "payload": {"event_type": "stdout"}}
    )
    assert not NodeConnectionManager._is_terminal_closed_event(None)
    assert not NodeConnectionManager._is_terminal_closed_event({"payload": "x"})


def test_handle_terminal_process_exit_publishes_terminal_closed():
    """进程退出应推 terminal_closed 给 owner/被分享用户并清理影子会话。"""
    published = []

    class FakeRouter:
        def publish(self, message, session_id=None, connection_id=None):
            published.append((message, session_id))

    tsm = MagicMock()
    tsm.get_all_admin_session_ids.return_value = ["session_admin-a"]
    tsm.get_access_session_ids.return_value = ["session_owner1", "session_viewer"]
    m = NodeConnectionManager(
        node_runtime=MagicMock(),
        agent_manager=MagicMock(),
        agent_proxy_manager=MagicMock(),
        node_http_dispatcher=None,
        router=FakeRouter(),
        terminal_session_manager=tsm,
    )
    m._handle_terminal_process_exit(_closed_event("t1"), "session_owner1")
    closed = [(msg, sid) for msg, sid in published if msg.get("type") == "terminal_closed"]
    assert closed, "应当推送 terminal_closed"
    assert all(msg["payload"]["terminal_id"] == "t1" for msg, _ in closed)
    sids = {sid for _, sid in closed}
    assert {"session_owner1", "session_viewer", "session_admin-a"} <= sids
    tsm.unregister_session.assert_called_once_with("t1")
    # 不应把 closed 事件当普通输出透传
    assert not any(msg.get("payload", {}).get("event_type") == "closed" for msg, _ in published)


def test_handle_terminal_process_exit_without_manager_is_safe():
    """无 terminal_session_manager 时也应安全推送 terminal_closed。"""
    published = []

    class FakeRouter:
        def publish(self, message, session_id=None, connection_id=None):
            published.append((message, session_id))

    m = NodeConnectionManager(
        node_runtime=MagicMock(),
        agent_manager=MagicMock(),
        agent_proxy_manager=MagicMock(),
        node_http_dispatcher=None,
        router=FakeRouter(),
        terminal_session_manager=None,
    )
    m._handle_terminal_process_exit(_closed_event("t9"), "session_owner1")
    assert any(
        msg.get("type") == "terminal_closed" and sid == "session_owner1"
        for msg, sid in published
    )
