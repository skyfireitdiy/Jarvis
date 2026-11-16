# -*- coding: utf-8 -*-
"""terminal_create 的解释器 / 工作目录兜底策略测试。

背景（真实故障）：前端右键「打开终端」只发 ``{type: terminal_create,
payload: {node_id: daemon-SF-PC-3948}}``，不带 interpreter / working_dir。
master 侧原来一律兜底成 ``os.environ["SHELL"]``（Linux 上是 /bin/bash）与
``pathlib.Path.home()``（Linux 家目录），这两个值被转发到 Windows daemon 后，
ConPTY 的 CreateProcess 直接失败：

    failed to start terminal: Failed to create console process:
    The system cannot find the file specified.   (ERROR_FILE_NOT_FOUND)

修复：远端节点不预设 interpreter / working_dir，交由节点按自身平台决定。

覆盖：
1. 远端节点 + 未指定解释器 → 转发 payload 中 interpreter 为空、working_dir 为空
2. 本地节点 + 未指定解释器 → 仍按 master 的 $SHELL / home 兜底
3. 显式指定解释器 → 原样透传
4. _forward_terminal_to_remote 用影子会话补齐 interpreter / working_dir
"""

import os

os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"

import asyncio
from unittest.mock import MagicMock

import jarvis.jarvis_web_gateway.app as app_module
from jarvis.jarvis_web_gateway.app import WebSocketConnectionManager


def _make_manager():
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


def _run_create(monkeypatch, *, payload, node_id, daemon_session):
    """执行一次 terminal_create，返回转发给 daemon 的 payload。"""
    tsm = MagicMock()
    _patch_app(monkeypatch, tsm=tsm)

    manager = _make_manager()
    captured = {}

    async def fake_forward_daemon(session, message_type, fwd_payload, sid, node):
        captured.update(
            message_type=message_type, payload=fwd_payload, node_id=node
        )
        return {"success": True, "data": {"terminal_id": "t1"}}

    manager._forward_terminal_to_daemon = fake_forward_daemon

    fake_dcm = MagicMock()
    fake_dcm.get_session_by_node_id.return_value = daemon_session
    monkeypatch.setattr(app_module, "daemon_capability_manager", fake_dcm, raising=False)

    asyncio.run(
        manager._handle_message(
            "session_u1",
            {"type": "terminal_create", "payload": payload},
            MagicMock(),
        )
    )
    return captured


def test_remote_node_does_not_inherit_master_interpreter(monkeypatch):
    """远端节点不继承 master 的 $SHELL / home（Windows 上不可用）。"""
    captured = _run_create(
        monkeypatch,
        payload={"node_id": "daemon-SF-PC-3948"},
        node_id="daemon-SF-PC-3948",
        daemon_session={"session_id": "ds-1"},
    )
    assert captured["message_type"] == "terminal_create"
    assert not captured["payload"].get("interpreter")
    assert not captured["payload"].get("working_dir")


def test_remote_node_keeps_explicit_interpreter(monkeypatch):
    """显式指定解释器时原样透传。"""
    captured = _run_create(
        monkeypatch,
        payload={"node_id": "daemon-SF-PC-3948", "interpreter": "powershell.exe"},
        node_id="daemon-SF-PC-3948",
        daemon_session={"session_id": "ds-1"},
    )
    assert captured["payload"]["interpreter"] == "powershell.exe"


def test_forward_to_remote_fills_shadow_session_fields(monkeypatch):
    """input/resize 转发时用影子会话补齐 interpreter / working_dir。"""
    tsm = MagicMock()
    tsm.get_session_info.return_value = {
        "terminal_id": "t1",
        "node_id": "daemon-SF-PC-3948",
        "interpreter": "cmd.exe",
        "working_dir": "C:\\Users\\skyfire",
    }
    _patch_app(monkeypatch, tsm=tsm)

    manager = _make_manager()
    captured = {}

    async def fake_forward_daemon(session, message_type, fwd_payload, sid, node):
        captured.update(payload=fwd_payload)

    manager._forward_terminal_to_daemon = fake_forward_daemon

    fake_dcm = MagicMock()
    fake_dcm.get_session_by_node_id.return_value = {"session_id": "ds-1"}
    monkeypatch.setattr(app_module, "daemon_capability_manager", fake_dcm, raising=False)

    forwarded = asyncio.run(
        manager._forward_terminal_to_remote(
            "t1", "terminal_session_input", {"terminal_id": "t1", "data": "dir\r"}, "s1"
        )
    )
    assert forwarded is True
    assert captured["payload"]["interpreter"] == "cmd.exe"
    assert captured["payload"]["working_dir"] == "C:\\Users\\skyfire"
    assert captured["payload"]["data"] == "dir\r"
