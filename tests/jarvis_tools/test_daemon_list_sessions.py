# -*- coding: utf-8 -*-
"""daemon 工具 list_sessions 透传 system_info 的回归测试。

守护目标：网关 ``/api/daemon/sessions`` 返回的 ``system_info`` 必须原样出现在
``DaemonTool`` 的 list_sessions 结果中，不得被字段裁剪掉——这是 Agent 判断
「后台服务所在机器环境、可调用哪些能力」的依据。

隔离：不发起真实网络请求，直接替换 ``_request_gateway`` 返回构造好的网关响应。
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from jarvis.jarvis_tools.daemon import DaemonTool


@pytest.fixture
def tool(monkeypatch):
    """构造 DaemonTool，并绕过 master_url 校验与真实网络请求。"""
    from jarvis.jarvis_tools import daemon as daemon_module

    monkeypatch.setattr(daemon_module.jglobals, "master_url", "http://127.0.0.1:1")
    return DaemonTool()


def test_list_sessions_passes_through_system_info(tool, monkeypatch):
    """list_sessions 的 stdout 必须包含网关返回的 system_info。"""
    system_info = {
        "hostname": "test-host",
        "os_name": "Ubuntu",
        "os_version": "24.04",
        "arch": "amd64",
        "cpu_count": 8,
        "mem_total_kb": 16000000,
        "user": "tester",
    }
    gateway_response = {
        "success": True,
        "data": {
            "success": True,
            "sessions": [
                {
                    "session_id": "sess-1",
                    "client_id": "daemon-test-host-1",
                    "node_id": "daemon-test-host-1",
                    "hostname": "test-host",
                    "platform": "Ubuntu",
                    "system_info": system_info,
                    "daemon_version": "0.0.1",
                    "capabilities": [],
                    "connected_at": 1.0,
                }
            ],
        },
    }
    monkeypatch.setattr(tool, "_request_gateway", lambda *a, **kw: gateway_response)

    result = tool.execute(action="list_sessions")
    assert result["success"] is True
    payload = json.loads(result["stdout"])
    assert len(payload) == 1
    assert payload[0]["system_info"] == system_info
    assert payload[0]["session_id"] == "sess-1"


def test_list_sessions_empty_returns_hint(tool, monkeypatch):
    """无会话时返回提示文本，不报错。"""
    monkeypatch.setattr(
        tool,
        "_request_gateway",
        lambda *a, **kw: {"success": True, "data": {"success": True, "sessions": []}},
    )
    result = tool.execute(action="list_sessions")
    assert result["success"] is True
    assert "没有在线的守护进程会话" in result["stdout"]
