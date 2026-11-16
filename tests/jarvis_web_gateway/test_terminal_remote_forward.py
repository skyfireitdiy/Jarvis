# -*- coding: utf-8 -*-
"""master 侧终端 input/resize 转发到远端节点的单元测试。

背景：daemon / 子节点终端在 master 上只是影子会话（register_remote_session，
无 master_fd / proc）。修复前 terminal_session_input / terminal_session_resize
只在本地 write_input / resize，写入的是空会话，前端表现为"输入无反应"。

覆盖 WebSocketConnectionManager._forward_terminal_to_remote：
1. 本地会话（node_id 为 master / 本地节点）→ 返回 False，由调用方本地处理
2. daemon 节点会话 → 经 _forward_terminal_to_daemon 转发，返回 True
3. 普通子节点会话 → 经 _node_connection_manager.send_request_to_node 转发，返回 True
4. 会话不存在 → 返回 False
"""

import os

# 必须在导入 jarvis 模块之前设置环境变量，避免触发交互式配置
os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

import jarvis.jarvis_web_gateway.app as app_module
from jarvis.jarvis_web_gateway.app import WebSocketConnectionManager


def _make_manager():
    """构造一个最小可用的 WebSocketConnectionManager（不依赖真实 router）。"""
    manager = WebSocketConnectionManager.__new__(WebSocketConnectionManager)
    manager._router = MagicMock()
    manager._permission_manager = None
    manager._auth_store = {}
    return manager


def _patch_app(monkeypatch, *, tsm, node_runtime=None, node_conn=None):
    monkeypatch.setattr(app_module, "_terminal_session_manager", tsm, raising=False)
    monkeypatch.setattr(app_module, "_node_runtime", node_runtime, raising=False)
    monkeypatch.setattr(
        app_module, "_node_connection_manager", node_conn, raising=False
    )


def test_local_session_not_forwarded(monkeypatch):
    """本地会话（node_id=master）应返回 False，交由本地处理。"""
    tsm = MagicMock()
    tsm.get_session_info.return_value = {"terminal_id": "t1", "node_id": "master"}
    _patch_app(monkeypatch, tsm=tsm)

    manager = _make_manager()
    forwarded = asyncio.run(
        manager._forward_terminal_to_remote(
            "t1", "terminal_session_input", {"terminal_id": "t1", "data": "ls\r"}, "s1"
        )
    )
    assert forwarded is False


def test_missing_session_not_forwarded(monkeypatch):
    """会话不存在（影子会话已清理）时应返回 False。"""
    tsm = MagicMock()
    tsm.get_session_info.return_value = None
    _patch_app(monkeypatch, tsm=tsm)

    manager = _make_manager()
    forwarded = asyncio.run(
        manager._forward_terminal_to_remote(
            "t1", "terminal_session_input", {"terminal_id": "t1", "data": "ls\r"}, "s1"
        )
    )
    assert forwarded is False


def test_daemon_session_forwarded(monkeypatch):
    """daemon 节点终端应经 _forward_terminal_to_daemon 转发。"""
    tsm = MagicMock()
    tsm.get_session_info.return_value = {
        "terminal_id": "t1",
        "node_id": "daemon-SF-PC-40356",
    }
    _patch_app(monkeypatch, tsm=tsm)

    manager = _make_manager()
    captured = {}

    async def fake_forward_daemon(session, message_type, payload, session_id, node_id):
        captured.update(
            session=session,
            message_type=message_type,
            payload=payload,
            session_id=session_id,
            node_id=node_id,
        )

    manager._forward_terminal_to_daemon = fake_forward_daemon

    fake_dcm = MagicMock()
    fake_dcm.get_session_by_node_id.return_value = {"session_id": "ds-1"}
    monkeypatch.setattr(app_module, "daemon_capability_manager", fake_dcm, raising=False)

    forwarded = asyncio.run(
        manager._forward_terminal_to_remote(
            "t1", "terminal_session_input", {"terminal_id": "t1", "data": "ls\r"}, "s1"
        )
    )
    assert forwarded is True
    assert captured["node_id"] == "daemon-SF-PC-40356"
    assert captured["message_type"] == "terminal_session_input"
    assert captured["payload"]["data"] == "ls\r"
    assert captured["payload"]["node_id"] == "daemon-SF-PC-40356"


def test_child_node_session_forwarded(monkeypatch):
    """普通子节点终端应经 _node_connection_manager 转发。"""
    tsm = MagicMock()
    tsm.get_session_info.return_value = {"terminal_id": "t2", "node_id": "node-abc"}
    node_conn = MagicMock()
    node_conn.send_request_to_node = AsyncMock(return_value={"payload": {}})
    _patch_app(monkeypatch, tsm=tsm, node_conn=node_conn)

    fake_dcm = MagicMock()
    fake_dcm.get_session_by_node_id.return_value = None
    monkeypatch.setattr(app_module, "daemon_capability_manager", fake_dcm, raising=False)

    manager = _make_manager()
    forwarded = asyncio.run(
        manager._forward_terminal_to_remote(
            "t2",
            "terminal_session_resize",
            {"terminal_id": "t2", "rows": 40, "cols": 120},
            "s1",
        )
    )
    assert forwarded is True
    node_conn.send_request_to_node.assert_awaited_once()
    args = node_conn.send_request_to_node.await_args.args
    assert args[0] == "node-abc"
    assert args[2]["action"] == "terminal_session_resize"
    assert args[2]["payload"]["rows"] == 40
    assert args[2]["payload"]["cols"] == 120
