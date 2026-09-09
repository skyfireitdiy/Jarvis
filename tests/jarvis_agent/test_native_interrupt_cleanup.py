# -*- coding: utf-8 -*-
"""原生工具调用路径：Ctrl+C 中断后清理待调用工具（_pending_native_tool_calls）"""

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_utils.globals import set_interrupt, get_interrupt


class _FakeSession:
    addon_prompt = ""
    prompt = ""


def _make_agent(pending_calls):
    """构造一个最小 Agent 实例，仅暴露 _handle_run_interrupt 所需属性。"""
    a = object.__new__(Agent)
    a._pending_native_tool_calls = pending_calls
    a.non_interactive = False
    a.set_non_interactive = lambda v: None
    a.run_input_handlers_next_turn = False
    a.return_control_on_auto_complete = False
    a.session = _FakeSession()
    a._last_handler_returned = False
    a.output_handler = []
    a.confirm_callback = lambda *x, **k: False
    a._process_input = lambda s: s
    # 中断后用户输入为空 -> 走 _complete_task 分支
    a._multiline_input = lambda *x, **k: ""
    a._complete_task = lambda auto_completed=False: "COMPLETED"
    # event_bus.emit 需可调用
    a.event_bus = type("Bus", (), {"emit": lambda self, *a, **k: None})()
    return a


def test_interrupt_clears_pending_native_calls():
    set_interrupt(False)
    a = _make_agent([{"id": "1", "name": "read_code", "arguments": {"path": "a"}}])
    # 模拟用户 Ctrl+C：设置中断标志
    set_interrupt(True)
    assert get_interrupt() > 0
    assert a._pending_native_tool_calls is not None

    result = a._handle_run_interrupt("")

    # 中断后待调用工具被清理，避免 run_loop 主循环误执行
    assert a._pending_native_tool_calls is None
    assert result == "COMPLETED"
    # 中断标志已被消费
    assert get_interrupt() == 0


def test_no_interrupt_keeps_pending_native_calls():
    set_interrupt(False)
    a = _make_agent([{"id": "1", "name": "read_code", "arguments": {"path": "a"}}])
    # 无中断：_handle_run_interrupt 直接返回 None，不清 pending
    result = a._handle_run_interrupt("")
    assert result is None
    assert a._pending_native_tool_calls is not None
    assert len(a._pending_native_tool_calls) == 1
