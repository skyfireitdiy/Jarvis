# -*- coding: utf-8 -*-
"""Agent._execute_native_batch 并行/串行分发单元测试"""

from jarvis.jarvis_agent import Agent


class _FakeReg:
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
