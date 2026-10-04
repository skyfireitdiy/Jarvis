# -*- coding: utf-8 -*-
"""registry.execute_tool 对独立类工具（browser_ext_* / daemon_*）的调用回归测试。

守护目标：
registry.execute_tool 的 v1.0 分支以「位置参数」调用 tool.execute(args_to_call)，
而 browser_ext_sessions / daemon_sessions 的 execute(self, **kwargs) 只接受关键字
参数，会触发 ``execute() takes 1 positional argument but 2 were given``；
browser_ext_capabilities / daemon_capabilities / browser_ext_call / daemon_call 的
execute(self, session_id=None, ...) 则会把整个 dict 误赋给 session_id，导致参数错位。

修复后 v1.0 分支优先以关键字参数调用（tool.execute(**args_to_call)），TypeError 时
回退位置参数调用（兼容 Tool 基类 execute(self, arguments) 风格）。

本测试不发起真实网络请求，直接替换工具实例的 _request_gateway。
"""

import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_tools.base import Tool
from jarvis.jarvis_tools.browser_ext_sessions import BrowserExtSessionsTool
from jarvis.jarvis_tools.browser_ext_capabilities import BrowserExtCapabilitiesTool
from jarvis.jarvis_tools.browser_ext_call import BrowserExtCallTool
from jarvis.jarvis_tools.daemon_sessions import DaemonSessionsTool
from jarvis.jarvis_tools.daemon_capabilities import DaemonCapabilitiesTool
from jarvis.jarvis_tools.daemon_call import DaemonCallTool


@pytest.fixture
def registry(monkeypatch):
    """构造一个空 registry，手动塞入待测工具实例。"""
    import jarvis.jarvis_utils.globals as jglobals

    monkeypatch.setattr(jglobals, "master_url", "http://127.0.0.1:1")
    reg = ToolRegistry()
    reg.tools.clear()
    reg._all_tools = {}
    return reg


def _install(reg, tool):
    """按真实注册路径把工具注册进 registry。

    真实路径（registry.register_tool_by_file）会把独立类工具的 execute 方法包装成
    Tool 基类实例（func=tool.execute），_all_tools 里存的是 Tool 实例而非工具类实例。
    这里同样包装，确保走 base.Tool.execute 的兼容分支。
    """
    wrapped = Tool(
        name=tool.name,
        description=tool.description,
        parameters=tool.parameters,
        func=tool.execute,
        protocol_version=getattr(tool, "protocol_version", "1.0"),
        interactive=getattr(tool, "interactive", False),
    )
    reg.tools[tool.name] = wrapped
    reg._all_tools[tool.name] = wrapped


def _sessions_gw_response(sessions):
    return {"success": True, "data": {"success": True, "sessions": sessions}}


def test_browser_ext_sessions_via_registry(registry, monkeypatch):
    """registry 调度层调用 browser_ext_sessions 不再报 TypeError，且透传会话。"""
    tool = BrowserExtSessionsTool()
    monkeypatch.setattr(
        tool,
        "_request_gateway",
        lambda *a, **kw: _sessions_gw_response(
            [{"session_id": "s1", "name": "SF-PC", "extension_version": "1.2.3"}]
        ),
    )
    _install(registry, tool)
    result = registry.execute_tool("browser_ext_sessions", {})
    assert result["success"] is True
    payload = json.loads(result["stdout"])
    assert payload[0]["session_id"] == "s1"


def test_daemon_sessions_via_registry(registry, monkeypatch):
    """registry 调度层调用 daemon_sessions 不再报 TypeError，且透传会话。"""
    tool = DaemonSessionsTool()
    monkeypatch.setattr(
        tool,
        "_request_gateway",
        lambda *a, **kw: _sessions_gw_response(
            [{"session_id": "d1", "hostname": "host-a", "daemon_version": "0.1.0"}]
        ),
    )
    _install(registry, tool)
    result = registry.execute_tool("daemon_sessions", {})
    assert result["success"] is True
    payload = json.loads(result["stdout"])
    assert payload[0]["session_id"] == "d1"


def test_browser_ext_capabilities_session_id_matches(registry, monkeypatch):
    """capabilities 的 session_id 必须正确匹配，而不是被整个 dict 覆盖。"""
    tool = BrowserExtCapabilitiesTool()
    captured = {}

    def fake_gw(method, path, json_data=None, **kw):
        captured["json_data"] = json_data
        return {
            "success": True,
            "data": {
                "success": True,
                "sessions": [
                    {
                        "session_id": "s1",
                        "capabilities": [{"name": "tab.list", "description": "x"}],
                    }
                ],
            },
        }

    monkeypatch.setattr(tool, "_request_gateway", fake_gw)
    _install(registry, tool)
    result = registry.execute_tool("browser_ext_capabilities", {"session_id": "s1"})
    assert result["success"] is True
    payload = json.loads(result["stdout"])
    assert payload[0]["name"] == "tab.list"


def test_daemon_call_session_id_matches(registry, monkeypatch):
    """daemon_call 的 session_id/name 必须正确匹配并透传。"""
    tool = DaemonCallTool()
    captured = {}

    def fake_gw(method, path, json_data=None, **kw):
        captured["json_data"] = json_data
        return {
            "success": True,
            "data": {
                "success": True,
                "result": {"success": True, "data": {"content": "hello"}},
            },
        }

    monkeypatch.setattr(tool, "_request_gateway", fake_gw)
    _install(registry, tool)
    result = registry.execute_tool(
        "daemon_call", {"session_id": "d1", "name": "fs.read"}
    )
    assert result["success"] is True
    assert captured["json_data"]["session_id"] == "d1"
    assert captured["json_data"]["name"] == "fs.read"


def test_tool_base_class_still_works(registry):
    """Tool 基类（execute(self, arguments) 位置参数风格）仍正常调用。"""
    calls = []

    def tool_func(args):
        calls.append(args)
        return {"success": True, "stdout": "ok", "stderr": ""}

    base_tool = Tool(
        name="base_tool",
        description="base",
        parameters={"type": "object"},
        func=tool_func,
    )
    _install(registry, base_tool)
    result = registry.execute_tool("base_tool", {"k": "v"})
    assert result["success"] is True
    assert calls and calls[0]["k"] == "v"


def test_tool_names_match_modules():
    """六个独立类工具的 name 契约保持不变。"""
    assert BrowserExtSessionsTool.name == "browser_ext_sessions"
    assert BrowserExtCapabilitiesTool.name == "browser_ext_capabilities"
    assert BrowserExtCallTool.name == "browser_ext_call"
    assert DaemonSessionsTool.name == "daemon_sessions"
    assert DaemonCapabilitiesTool.name == "daemon_capabilities"
    assert DaemonCallTool.name == "daemon_call"
