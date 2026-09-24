# -*- coding: utf-8 -*-
"""原生工具调用「已确认支持则不再降级」行为测试（openai / claude）。

核心行为：
- 模型曾被确认支持原生工具调用（_native_confirmed=True）时，原生请求失败必须
  向上抛出，不得静默降级为纯文本协议；
- 未确认支持的模型保持既有容错行为：异常被渲染层吞掉时返回空结果，不抛错。

说明：流式异常默认会被渲染管线（_chat_with_*_output）捕获并返回已收集内容，
因此 openai/claude 的 chat_native_once 的降级 except 分支在默认情况下并不触发。
本测试通过 raise_on_error 链路验证「已确认支持」时异常确实向上抛出。
"""

import threading
from unittest.mock import MagicMock

import pytest

from jarvis.jarvis_platform.claude import ClaudeModel
from jarvis.jarvis_platform.openai import OpenAIModel

TOOLS = [{"name": "add", "description": "求和", "input_schema": {"type": "object"}}]


def _make_openai_model():
    m = object.__new__(OpenAIModel)
    m.messages = []
    m._native_disabled = False
    m._native_confirmed = False
    m.api_keys = []
    m._api_key_index = 0
    m.model_name = "openai-test"
    m.agent = None
    m.suppress_output = True
    m._panel_lock = threading.RLock()
    m.temperature = None
    m.top_p = None
    m.max_tokens = None
    m.reasoning_effort = None
    m.extra_body = None
    m.client = MagicMock()
    return m


def _make_claude_model():
    m = object.__new__(ClaudeModel)
    m.messages = []
    m._native_disabled = False
    m._native_confirmed = False
    m.api_keys = []
    m._api_key_index = 0
    m.model_name = "claude-test"
    m.agent = None
    m.suppress_output = True
    m._panel_lock = threading.RLock()
    m.client = MagicMock()
    return m


class _BoomStream:
    """上下文管理器：进入后 text_stream 迭代即抛错，模拟端点不支持 tools。"""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def text_stream(self):
        raise RuntimeError("tools unsupported")


def test_openai_confirmed_raises_instead_of_fallback(monkeypatch):
    m = _make_openai_model()
    m._native_confirmed = True
    fallback_called = []
    monkeypatch.setattr(
        OpenAIModel,
        "_native_fallback_text",
        lambda self, message, append_user: (
            fallback_called.append(True) or ("fallback", None)
        ),
    )
    m.client.chat.completions.create.side_effect = RuntimeError("tools unsupported")

    with pytest.raises(Exception):
        m.chat_native_once("hi", TOOLS)
    # 未降级：既不置 _native_disabled，也不走文本回退
    assert m._native_disabled is False
    assert fallback_called == []


def test_openai_unconfirmed_does_not_raise(monkeypatch):
    """未确认支持的模型：失败不向上抛出，而是降级到文本协议。"""
    m = _make_openai_model()
    m._native_confirmed = False
    fallback_called = []
    monkeypatch.setattr(
        OpenAIModel,
        "_native_fallback_text",
        lambda self, message, append_user: (
            fallback_called.append(True) or ("fallback", None)
        ),
    )
    m.client.chat.completions.create.side_effect = RuntimeError("tools unsupported")

    content, calls = m.chat_native_once("hi", TOOLS)
    assert content == "fallback"
    assert calls is None
    assert fallback_called == [True]


def test_claude_confirmed_raises_instead_of_fallback(monkeypatch):
    m = _make_claude_model()
    m._native_confirmed = True
    fallback_called = []
    monkeypatch.setattr(
        ClaudeModel,
        "_claude_fallback_text",
        lambda self, message, append_user: (
            fallback_called.append(True) or ("fallback", None)
        ),
    )
    m.client.messages.stream.side_effect = lambda **kwargs: _BoomStream()

    with pytest.raises(Exception):
        m.chat_native_once("hi", TOOLS)
    assert m._native_disabled is False
    assert fallback_called == []


def test_claude_unconfirmed_does_not_raise(monkeypatch):
    """未确认支持的模型：失败不向上抛出（保持既有容错行为）。"""
    m = _make_claude_model()
    m._native_confirmed = False
    m.client.messages.stream.side_effect = lambda **kwargs: _BoomStream()

    m.chat_native_once("hi", TOOLS)


def test_raise_on_error_propagates_from_render_pipeline():
    """渲染管线在 raise_on_error=True 时不再吞掉流式异常。"""
    from jarvis.jarvis_utils.output import PrettyOutput

    def _boom():
        raise RuntimeError("stream boom")
        yield ("content", "x")  # pragma: no cover

    with pytest.raises(Exception):
        PrettyOutput.stream_chat_simple(
            chat_iterator=_boom(),
            prefix="🤖 模型输出 - test",
            start_time=0.0,
            raise_on_error=True,
        )
