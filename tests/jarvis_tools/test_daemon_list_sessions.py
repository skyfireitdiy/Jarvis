# -*- coding: utf-8 -*-
"""daemon 三件套（sessions / capabilities / call）测试。

守护目标：
1. daemon_sessions 透传网关返回的会话（含 system_info）——这是 Agent 判断
   「后台服务所在机器环境、可调用哪些能力」的依据，不得被字段裁剪掉。
2. daemon_capabilities 从 /api/daemon/capability/list 读取指定会话的能力清单。
3. daemon_call 把能力名透传给 /api/daemon/capability/call，并解析结果信封。

隔离：不发起真实网络请求，直接替换 ``_request_gateway`` 返回构造好的网关响应。
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from jarvis.jarvis_tools.daemon_sessions import DaemonSessionsTool
from jarvis.jarvis_tools.daemon_capabilities import DaemonCapabilitiesTool
from jarvis.jarvis_tools.daemon_call import DaemonCallTool


@pytest.fixture
def sessions_tool(monkeypatch):
    """构造 DaemonSessionsTool，并绕过 master_url 校验与真实网络请求。"""
    from jarvis.jarvis_tools import daemon_sessions as module

    monkeypatch.setattr(module.jglobals, "master_url", "http://127.0.0.1:1")
    return DaemonSessionsTool()


@pytest.fixture
def capabilities_tool(monkeypatch):
    """构造 DaemonCapabilitiesTool，并绕过 master_url 校验与真实网络请求。"""
    from jarvis.jarvis_tools import daemon_capabilities as module

    monkeypatch.setattr(module.jglobals, "master_url", "http://127.0.0.1:1")
    return DaemonCapabilitiesTool()


@pytest.fixture
def call_tool(monkeypatch):
    """构造 DaemonCallTool，并绕过 master_url 校验与真实网络请求。"""
    from jarvis.jarvis_tools import daemon_call as module

    monkeypatch.setattr(module.jglobals, "master_url", "http://127.0.0.1:1")
    return DaemonCallTool()


# ---------------- daemon_sessions ----------------


def test_sessions_passes_through_system_info(sessions_tool, monkeypatch):
    """daemon_sessions 的 stdout 必须包含网关返回的 system_info。"""
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
    monkeypatch.setattr(
        sessions_tool, "_request_gateway", lambda *a, **kw: gateway_response
    )

    result = sessions_tool.execute()
    assert result["success"] is True
    payload = json.loads(result["stdout"])
    assert len(payload) == 1
    assert payload[0]["system_info"] == system_info
    assert payload[0]["session_id"] == "sess-1"


def test_sessions_empty_returns_hint(sessions_tool, monkeypatch):
    """无会话时返回提示文本，不报错。"""
    monkeypatch.setattr(
        sessions_tool,
        "_request_gateway",
        lambda *a, **kw: {"success": True, "data": {"success": True, "sessions": []}},
    )
    result = sessions_tool.execute()
    assert result["success"] is True
    assert "没有在线的守护进程会话" in result["stdout"]


# ---------------- daemon_capabilities ----------------


def test_capabilities_reads_session_capabilities(capabilities_tool, monkeypatch):
    """daemon_capabilities 从 /api/daemon/capability/list 读取指定会话的能力清单。"""
    capabilities = [
        {
            "name": "fs.read",
            "description": "读取文件",
            "parameters": {},
            "platform": "windows",
        },
        {
            "name": "system.info",
            "description": "系统信息",
            "parameters": {},
            "platform": "windows",
        },
    ]
    captured = {}

    def fake_request_gateway(method, path, json_data=None, **kw):
        captured["method"] = method
        captured["path"] = path
        captured["json_data"] = json_data
        return {
            "success": True,
            "data": {
                "success": True,
                "result": {"success": True, "capabilities": capabilities},
            },
        }

    monkeypatch.setattr(capabilities_tool, "_request_gateway", fake_request_gateway)
    result = capabilities_tool.execute(session_id="sess-1")
    assert result["success"] is True
    payload = json.loads(result["stdout"])
    assert payload == capabilities
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/daemon/capability/list"
    assert captured["json_data"]["session_id"] == "sess-1"


def test_capabilities_empty_returns_hint(capabilities_tool, monkeypatch):
    """会话无能力时返回提示，不报错。"""
    monkeypatch.setattr(
        capabilities_tool,
        "_request_gateway",
        lambda *a, **kw: {
            "success": True,
            "data": {"success": True, "result": {"success": True, "capabilities": []}},
        },
    )
    result = capabilities_tool.execute(session_id="sess-1")
    assert result["success"] is True
    assert "未注册任何能力" in result["stdout"]


def test_capabilities_requires_session_id(capabilities_tool, monkeypatch):
    """缺 session_id 时报错。"""
    result = capabilities_tool.execute()
    assert result["success"] is False
    assert "session_id is required" in result["stderr"]


# ---------------- daemon_call ----------------


def test_call_passes_name_and_params(call_tool, monkeypatch):
    """daemon_call 把能力名透传给 /api/daemon/capability/call，并解析结果信封。"""
    captured = {}

    def fake_request_gateway(method, path, json_data=None, **kw):
        captured["method"] = method
        captured["path"] = path
        captured["json_data"] = json_data
        return {
            "success": True,
            "data": {
                "success": True,
                "result": {"success": True, "data": {"content": "hello"}},
            },
        }

    monkeypatch.setattr(call_tool, "_request_gateway", fake_request_gateway)
    result = call_tool.execute(
        session_id="sess-1",
        name="fs.read",
        params={"path": "/tmp/a.txt"},
    )
    assert result["success"] is True
    payload = json.loads(result["stdout"])
    assert payload == {"content": "hello"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/daemon/capability/call"
    assert captured["json_data"] == {
        "session_id": "sess-1",
        "name": "fs.read",
        "params": {"path": "/tmp/a.txt"},
        "timeout": 30.0,
    }


def test_call_requires_name(call_tool, monkeypatch):
    """daemon_call 缺 name 时报错。"""
    result = call_tool.execute(session_id="sess-1")
    assert result["success"] is False
    assert "name is required" in result["stderr"]


def test_call_requires_session_id(call_tool, monkeypatch):
    """daemon_call 缺 session_id 时报错。"""
    result = call_tool.execute(name="fs.read")
    assert result["success"] is False
    assert "session_id is required" in result["stderr"]


def test_call_params_must_be_object(call_tool, monkeypatch):
    """daemon_call 的 params 非对象时报错。"""
    result = call_tool.execute(session_id="sess-1", name="fs.read", params="bad")
    assert result["success"] is False
    assert "params must be an object" in result["stderr"]


def test_call_daemon_reports_failure(call_tool, monkeypatch):
    """守护进程侧返回失败时透传错误。"""
    monkeypatch.setattr(
        call_tool,
        "_request_gateway",
        lambda *a, **kw: {
            "success": True,
            "data": {
                "success": True,
                "result": {"success": False, "error": "EXEC_ERROR: boom"},
            },
        },
    )
    result = call_tool.execute(session_id="sess-1", name="fs.read")
    assert result["success"] is False
    assert "boom" in result["stderr"]


# ---------------- 工具名/注册契约 ----------------


def test_tool_names_match_modules():
    """三个工具类的 name 必须等于各自模块名（registry 的 item.name == module_name 契约）。"""
    assert DaemonSessionsTool.name == "daemon_sessions"
    assert DaemonCapabilitiesTool.name == "daemon_capabilities"
    assert DaemonCallTool.name == "daemon_call"
