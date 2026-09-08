# -*- coding: utf-8 -*-
"""claude 原生 function calling 单测（fake Anthropic 流）"""

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

from jarvis.jarvis_platform.claude import ClaudeModel

ANTHROPIC_TOOLS = [
    {"name": "add", "description": "求和", "input_schema": {"type": "object"}}
]


def _make_model(stream):
    m = object.__new__(ClaudeModel)
    m.messages = []
    m._native_disabled = False
    m.api_keys = []
    m._api_key_index = 0
    m.model_name = "claude-test"
    m.agent = None
    # 渲染管线所需实例属性（BasePlatform.__init__ 中定义，object.__new__ 绕过后需补齐）
    m.suppress_output = False
    m._panel_lock = threading.RLock()
    m.client = MagicMock()
    m.client.messages.stream.return_value = stream
    return m


def _text_stream(text_parts, content_blocks, stop_reason="end_turn"):
    stream = MagicMock()
    stream.__enter__.return_value = stream
    stream.text_stream = text_parts
    final = SimpleNamespace(stop_reason=stop_reason, content=content_blocks)
    stream.get_final_message.return_value = final
    return stream


def _tool_use_block(id_, name, input_):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


def test_chat_native_once_tool_use():
    stream = _text_stream(
        ["让我算一下"],
        [_tool_use_block("tu_1", "add", {"a": 1, "b": 2})],
        stop_reason="tool_use",
    )
    m = _make_model(stream)
    content, calls = m.chat_native_once("请计算 1+2", ANTHROPIC_TOOLS)
    assert content == "让我算一下"
    assert calls == [{"id": "tu_1", "name": "add", "arguments": {"a": 1, "b": 2}}]
    # 历史：user + assistant(tool_calls)
    assert [msg["role"] for msg in m.messages] == ["user", "assistant"]
    assert m.messages[1].get("tool_calls") == calls
    # 请求确实带了 tools 与 system 处理
    kwargs = m.client.messages.stream.call_args.kwargs
    assert kwargs["tools"] == ANTHROPIC_TOOLS


def test_tool_round_without_new_user_message():
    # 先模拟上一轮已产生 assistant(tool_use)
    m = object.__new__(ClaudeModel)
    m.messages = []
    m._native_disabled = False
    m.api_keys = []
    m._api_key_index = 0
    m.model_name = "claude-test"
    m.agent = None
    m.suppress_output = False
    m._panel_lock = threading.RLock()
    stream = _text_stream(
        [],
        [_tool_use_block("tu_1", "add", {"a": 1, "b": 2})],
        stop_reason="tool_use",
    )
    m.client = MagicMock()
    m.client.messages.stream.return_value = stream
    _, calls = m.chat_native_once("算一下", ANTHROPIC_TOOLS)
    # 回填 tool 结果
    m.append_native_tool_result("tu_1", "add", "3")

    stream2 = _text_stream(["结果是 3"], [])
    m.client.messages.stream.return_value = stream2
    content, calls2 = m.chat_native_once(None, ANTHROPIC_TOOLS, append_user=False)
    assert content == "结果是 3"
    assert calls2 is None
    # 没有额外 user 消息
    assert m.messages[-1]["role"] == "assistant"
    assert sum(1 for msg in m.messages if msg["role"] == "user") == 1
