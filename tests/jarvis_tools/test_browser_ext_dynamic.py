# -*- coding: utf-8 -*-
"""browser_ext 三件套（sessions / capabilities / call）测试。

守护目标：工具层拆分为三个独立工具（无 action 参数，工具名即操作）后，
三个工具的正常与错误路径必须正确：
- browser_ext_sessions: 透传网关返回的会话（含 capabilities）
- browser_ext_capabilities: 从会话中读取指定会话的能力清单
- browser_ext_call: 把能力名（name）作为 action 透传给 /api/browser-ext/command，并解析结果信封

隔离：不发起真实网络请求，直接替换 ``_request_gateway`` 返回构造好的网关响应。
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from jarvis.jarvis_tools.browser_ext_sessions import BrowserExtSessionsTool
from jarvis.jarvis_tools.browser_ext_capabilities import BrowserExtCapabilitiesTool
from jarvis.jarvis_tools.browser_ext_call import BrowserExtCallTool


@pytest.fixture
def sessions_tool(monkeypatch):
    """构造 BrowserExtSessionsTool，并绕过 master_url 校验与真实网络请求。"""
    from jarvis.jarvis_tools import browser_ext_sessions as module

    monkeypatch.setattr(module.jglobals, "master_url", "http://127.0.0.1:1")
    return BrowserExtSessionsTool()


@pytest.fixture
def capabilities_tool(monkeypatch):
    """构造 BrowserExtCapabilitiesTool，并绕过 master_url 校验与真实网络请求。"""
    from jarvis.jarvis_tools import browser_ext_capabilities as module

    monkeypatch.setattr(module.jglobals, "master_url", "http://127.0.0.1:1")
    return BrowserExtCapabilitiesTool()


@pytest.fixture
def call_tool(monkeypatch):
    """构造 BrowserExtCallTool，并绕过 master_url 校验与真实网络请求。"""
    from jarvis.jarvis_tools import browser_ext_call as module

    monkeypatch.setattr(module.jglobals, "master_url", "http://127.0.0.1:1")
    return BrowserExtCallTool()


def _sessions_response(sessions):
    return {"success": True, "data": {"success": True, "sessions": sessions}}


# ---------------- browser_ext_sessions ----------------


def test_sessions_passes_through_sessions(sessions_tool, monkeypatch):
    """browser_ext_sessions 的 stdout 必须包含网关返回的会话（含 capabilities）。"""
    capabilities = [
        {
            "name": "tab.list",
            "description": "列出标签页",
            "parameters": {},
            "platform": "browser",
        }
    ]
    gateway_response = _sessions_response(
        [
            {
                "session_id": "sess-1",
                "name": "Chrome 扩展",
                "browser_info": {"name": "Chrome", "version": "120"},
                "capabilities": capabilities,
            }
        ]
    )
    monkeypatch.setattr(
        sessions_tool, "_request_gateway", lambda *a, **kw: gateway_response
    )

    result = sessions_tool.execute()
    assert result["success"] is True
    payload = json.loads(result["stdout"])
    assert len(payload) == 1
    assert payload[0]["session_id"] == "sess-1"
    assert payload[0]["capabilities"] == capabilities


def test_sessions_empty_returns_hint(sessions_tool, monkeypatch):
    """无会话时返回提示文本，不报错。"""
    monkeypatch.setattr(
        sessions_tool, "_request_gateway", lambda *a, **kw: _sessions_response([])
    )
    result = sessions_tool.execute()
    assert result["success"] is True
    assert "没有在线的浏览器扩展会话" in result["stdout"]


# ---------------- browser_ext_capabilities ----------------


def test_capabilities_reads_session_capabilities(capabilities_tool, monkeypatch):
    """browser_ext_capabilities 从会话中读取指定会话的能力清单。"""
    capabilities = [
        {
            "name": "dom.click",
            "description": "点击元素",
            "parameters": {},
            "platform": "browser",
        },
        {
            "name": "tab.create",
            "description": "新建标签页",
            "parameters": {},
            "platform": "browser",
        },
    ]
    monkeypatch.setattr(
        capabilities_tool,
        "_request_gateway",
        lambda *a, **kw: _sessions_response(
            [
                {"session_id": "sess-1", "capabilities": capabilities},
                {"session_id": "sess-2", "capabilities": []},
            ]
        ),
    )
    result = capabilities_tool.execute(session_id="sess-1")
    assert result["success"] is True
    payload = json.loads(result["stdout"])
    assert payload == capabilities


def test_capabilities_session_not_found(capabilities_tool, monkeypatch):
    """指定会话不存在时报错。"""
    monkeypatch.setattr(
        capabilities_tool,
        "_request_gateway",
        lambda *a, **kw: _sessions_response(
            [{"session_id": "sess-1", "capabilities": []}]
        ),
    )
    result = capabilities_tool.execute(session_id="nope")
    assert result["success"] is False
    assert "session not found" in result["stderr"]


def test_capabilities_empty_returns_hint(capabilities_tool, monkeypatch):
    """会话无能力时返回提示，不报错。"""
    monkeypatch.setattr(
        capabilities_tool,
        "_request_gateway",
        lambda *a, **kw: _sessions_response(
            [{"session_id": "sess-1", "capabilities": []}]
        ),
    )
    result = capabilities_tool.execute(session_id="sess-1")
    assert result["success"] is True
    assert "未上报任何能力" in result["stdout"]


def test_capabilities_requires_session_id(capabilities_tool, monkeypatch):
    """缺 session_id 时报错。"""
    result = capabilities_tool.execute()
    assert result["success"] is False
    assert "session_id is required" in result["stderr"]


# ---------------- browser_ext_call ----------------


def test_call_passes_name_and_params(call_tool, monkeypatch):
    """browser_ext_call 把能力名作为 action 透传，并解析结果信封。"""
    captured = {}

    def fake_request_gateway(method, path, json_data=None, **kw):
        captured["method"] = method
        captured["path"] = path
        captured["json_data"] = json_data
        return {
            "success": True,
            "data": {
                "success": True,
                "result": {"success": True, "data": {"title": "示例页"}},
            },
        }

    monkeypatch.setattr(call_tool, "_request_gateway", fake_request_gateway)
    result = call_tool.execute(
        session_id="sess-1",
        name="page.get_info",
        params={"tab_id": 3},
    )
    assert result["success"] is True
    payload = json.loads(result["stdout"])
    assert payload == {"title": "示例页"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/browser-ext/command"
    assert captured["json_data"] == {
        "session_id": "sess-1",
        "action": "page.get_info",
        "params": {"tab_id": 3},
        "timeout": 15.0,
    }


def test_call_requires_name(call_tool, monkeypatch):
    """browser_ext_call 缺 name 时报错。"""
    result = call_tool.execute(session_id="sess-1")
    assert result["success"] is False
    assert "name is required" in result["stderr"]


def test_call_requires_session_id(call_tool, monkeypatch):
    """browser_ext_call 缺 session_id 时报错。"""
    result = call_tool.execute(name="tab.list")
    assert result["success"] is False
    assert "session_id is required" in result["stderr"]


def test_call_params_must_be_object(call_tool, monkeypatch):
    """browser_ext_call 的 params 非对象时报错。"""
    result = call_tool.execute(session_id="sess-1", name="tab.list", params="bad")
    assert result["success"] is False
    assert "params must be an object" in result["stderr"]


def test_call_extension_reports_failure(call_tool, monkeypatch):
    """扩展侧返回失败时透传错误。"""
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
    result = call_tool.execute(session_id="sess-1", name="tab.list")
    assert result["success"] is False
    assert "boom" in result["stderr"]


# ---------------- 工具名/注册契约 ----------------


def test_tool_names_match_modules():
    """三个工具类的 name 必须等于各自模块名（registry 的 item.name == module_name 契约）。"""
    assert BrowserExtSessionsTool.name == "browser_ext_sessions"
    assert BrowserExtCapabilitiesTool.name == "browser_ext_capabilities"
    assert BrowserExtCallTool.name == "browser_ext_call"
