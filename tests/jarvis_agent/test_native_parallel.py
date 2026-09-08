# -*- coding: utf-8 -*-
"""Agent._execute_native_batch 并行/串行分发单元测试"""

from jarvis.jarvis_agent import Agent


class _FakeReg:
    def __init__(self, interactive_names=()):
        self.interactive_names = set(interactive_names)

    def get_tool(self, name):
        if name in self.interactive_names:
            return type("T", (), {"interactive": True})()
        return None

    def execute_native_tool_call(self, name, arguments, agent, record=True):
        return f"res:{name}"


def _make():
    a = object.__new__(Agent)
    a.execute_tool_confirm = False
    store = {"__executed_tools__": []}
    a.get_user_data = lambda k: store.get(k)
    a.set_user_data = lambda k, v: store.__setitem__(k, v)
    a.get_tool_registry = lambda: _FakeReg()
    a.confirm_callback = lambda *x, **k: True
    return a, store


def test_parallel_read_calls_run_and_record():
    a, store = _make()
    calls = [
        {"id": "1", "name": "read_code", "arguments": {"path": "a"}},
        {"id": "2", "name": "search_web", "arguments": {"q": "x"}},
    ]
    out = a._execute_native_batch(calls)
    assert out == ["res:read_code", "res:search_web"]
    assert store["__executed_tools__"] == ["read_code", "search_web"]
    assert store["__last_executed_tool__"] == "search_web"


def test_interactive_tool_forces_sequential():
    a, store = _make()
    calls = [
        {"id": "1", "name": "read_code", "arguments": {}},
        {"id": "2", "name": "execute_script", "arguments": {}},
    ]
    out = a._execute_native_batch(calls)
    assert out == ["res:read_code", "res:execute_script"]


def test_confirm_deny_returns_rejection():
    a, store = _make()
    a.execute_tool_confirm = True
    a.confirm_callback = lambda *x, **k: False
    out = a._execute_native_batch(
        [{"id": "1", "name": "read_code", "arguments": {}}]
    )
    assert "拒绝" in out[0]


def test_user_tool_marked_interactive_forces_serial():
    a, store = _make()
    # 用户自定义工具声明 interactive=True（不在内置名单），也应整批串行执行
    a.get_tool_registry = lambda: _FakeReg(interactive_names={"my_custom"})
    calls = [
        {"id": "1", "name": "read_code", "arguments": {}},
        {"id": "2", "name": "my_custom", "arguments": {}},
    ]
    out = a._execute_native_batch(calls)
    assert out == ["res:read_code", "res:my_custom"]
