# -*- coding: utf-8 -*-
"""文本协议路径下模型 API 异常必须向上抛出（不得被流式渲染层静默吞掉）

背景（根因）：
    `_chat` 调用 `_chat_with_pretty_output` / `_chat_with_simple_output` /
    `_chat_with_suppressed_output` 时未传 raise_on_error，渲染层默认
    raise_on_error=False，会把模型 API 的真实异常（鉴权/参数/网络错误等）
    静默吞掉并返回空字符串。

    上层 `chat_until_success` 的 while_true/while_success 无法区分
    “模型返回空” 与 “API 调用失败”，会无意义重试 6 次，最后抛出误导性的
    ValueError("返回结果为空")，真实错误被完全掩盖，导致线上问题无法定位。

修复：
    `_chat` 三条渲染路径统一传 raise_on_error=True，使真实异常向上抛出，
    由 while_success 重试并在耗尽后携带真实原因传播。
"""

import threading
from unittest.mock import MagicMock

import pytest

from jarvis.jarvis_platform.openai import OpenAIModel


def _make_model(fake_create):
    """构造一个绕过 __init__ 的最小 OpenAIModel，仅替换 client。"""
    m = OpenAIModel.__new__(OpenAIModel)
    m.suppress_output = False
    m._panel_lock = threading.RLock()
    m._session_history_file = None
    m.platform_type = "normal"
    m.agent = None
    m.model_name = "test-model"
    m._native_disabled = False
    m._native_confirmed = True
    m._llm_config = {}
    m._supports_multimodal = False
    m.messages = [{"role": "system", "content": "sys"}]
    m.system_message = "sys"
    m.api_key = "k"
    m.api_keys = []
    m._api_key_index = 0
    m._streaming_disabled = None
    m.temperature = 0.7
    m.top_p = None
    m.max_tokens = None
    m.reasoning_effort = None
    m.extra_body = None
    client = MagicMock()
    client.chat.completions.create = fake_create
    m.client = client
    return m


def test_chat_propagates_api_exception(monkeypatch):
    """API 抛异常时，_chat 应向上抛出真实异常，而非返回空字符串。"""

    def fake_create(**kwargs):
        raise RuntimeError("400 Bad Request: invalid message format")

    m = _make_model(fake_create)
    # 走 pretty 输出路径（默认路径）
    monkeypatch.setattr(
        "jarvis.jarvis_platform.base.get_pretty_output", lambda: True
    )

    with pytest.raises(Exception) as exc_info:
        m._chat("hello")

    # 真实错误信息必须可见（openai.chat 会包装为 "Chat failed: ..."）
    assert "400 Bad Request" in str(exc_info.value)


def test_chat_propagates_empty_response_as_exception(monkeypatch):
    """模型返回空 content 时，_chat 应抛出 "No response from model"，而非静默返回空串。"""

    class _EmptyChunk:
        def __init__(self):
            self.choices = [
                MagicMock(
                    delta=MagicMock(content=None, reasoning_content=None, tool_calls=None)
                )
            ]

    class _EmptyResp:
        def __init__(self):
            self.choices = [
                MagicMock(message=MagicMock(content=None, reasoning_content=None))
            ]

    def fake_create(**kwargs):
        if kwargs.get("stream"):
            return iter([_EmptyChunk()])
        return _EmptyResp()

    m = _make_model(fake_create)
    monkeypatch.setattr(
        "jarvis.jarvis_platform.base.get_pretty_output", lambda: True
    )

    with pytest.raises(Exception) as exc_info:
        m._chat("hello")

    assert "No response from model" in str(exc_info.value)


def test_chat_simple_path_propagates_exception(monkeypatch):
    """非 pretty 输出路径（stream_chat_simple）同样必须抛出真实异常。"""

    def fake_create(**kwargs):
        raise RuntimeError("401 Unauthorized: invalid api key")

    m = _make_model(fake_create)
    monkeypatch.setattr(
        "jarvis.jarvis_platform.base.get_pretty_output", lambda: False
    )

    with pytest.raises(Exception) as exc_info:
        m._chat("hello")

    assert "401 Unauthorized" in str(exc_info.value)


def test_chat_suppressed_path_propagates_exception():
    """suppress_output 路径同样必须抛出真实异常。"""

    def fake_create(**kwargs):
        raise RuntimeError("500 Internal Server Error")

    m = _make_model(fake_create)
    m.suppress_output = True

    with pytest.raises(Exception) as exc_info:
        m._chat("hello")

    assert "500 Internal Server Error" in str(exc_info.value)
