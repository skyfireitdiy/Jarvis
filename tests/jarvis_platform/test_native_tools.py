# -*- coding: utf-8 -*-
"""native_tools 消息模型与序列化单元测试"""

import json

from jarvis.jarvis_platform.native_tools import (
    build_anthropic_tools,
    build_openai_tools,
    make_tool_call,
    make_tool_call_msg,
    make_tool_result_msg,
    to_anthropic_messages,
    to_openai_messages,
    to_text,
)


class _FakeTool:
    def __init__(self, name, description, parameters):
        self.name = name
        self.description = description
        self.parameters = parameters


class _FakeRegistry:
    def __init__(self, tools):
        self.tools = {t.name: t for t in tools}


def _sample_tool_call_msg():
    return make_tool_call_msg(
        "让我查一下",
        [make_tool_call("call_1", "read_code", {"path": "a.py"})],
    )


class TestMessageModel:
    def test_to_text_tool_call(self):
        text = to_text(_sample_tool_call_msg())
        assert "让我查一下" in text
        assert "read_code" in text
        assert "a.py" in text

    def test_to_text_tool_result(self):
        msg = make_tool_result_msg("call_1", "read_code", "OK content")
        text = to_text(msg)
        assert "read_code" in text and "OK content" in text

    def test_to_text_plain(self):
        assert to_text({"role": "user", "content": "你好"}) == "你好"
        assert to_text({"role": "assistant", "content": None}) == ""


class TestOpenAISerialization:
    def test_tool_call_and_result(self):
        history = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            _sample_tool_call_msg(),
            make_tool_result_msg("call_1", "read_code", "结果"),
        ]
        msgs = to_openai_messages(history)
        assert msgs[0] == {"role": "system", "content": "sys"}
        assert msgs[2]["role"] == "assistant"
        tc = msgs[2]["tool_calls"][0]
        assert tc["id"] == "call_1"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "read_code"
        assert json.loads(tc["function"]["arguments"]) == {"path": "a.py"}
        assert msgs[3]["role"] == "tool"
        assert msgs[3]["tool_call_id"] == "call_1"
        assert msgs[3]["content"] == "结果"


class TestAnthropicSerialization:
    def test_system_extracted_and_tool_use_blocks(self):
        history = [
            {"role": "system", "content": "系统提示"},
            {"role": "user", "content": "hi"},
            _sample_tool_call_msg(),
            make_tool_result_msg("call_1", "read_code", "结果A"),
            make_tool_result_msg("call_2", "search_web", "结果B"),
            {"role": "assistant", "content": "完成"},
        ]
        system, msgs = to_anthropic_messages(history)
        assert system == "系统提示"
        assert all(m["role"] != "system" for m in msgs)
        tool_msg = msgs[1]
        assert tool_msg["role"] == "assistant"
        assert tool_msg["content"][0]["type"] == "text"
        assert tool_msg["content"][1] == {
            "type": "tool_use",
            "id": "call_1",
            "name": "read_code",
            "input": {"path": "a.py"},
        }
        # 两个连续 tool 结果合并为一条 user 消息的两个 tool_result 块
        user_tool = msgs[2]
        assert user_tool["role"] == "user"
        assert len(user_tool["content"]) == 2
        assert user_tool["content"][0]["type"] == "tool_result"
        assert user_tool["content"][0]["tool_use_id"] == "call_1"
        assert user_tool["content"][1]["tool_use_id"] == "call_2"
        assert msgs[3] == {"role": "assistant", "content": "完成"}


class TestSchema:
    def test_build_openai_tools(self):
        reg = _FakeRegistry(
            [
                _FakeTool(
                    "read_code",
                    "读取文件",
                    {"type": "object", "properties": {"path": {"type": "string"}}},
                )
            ]
        )
        tools = build_openai_tools(reg)
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "read_code"
        assert tools[0]["function"]["parameters"]["properties"]["path"]["type"] == "string"

    def test_build_anthropic_tools(self):
        reg = _FakeRegistry(
            [
                _FakeTool(
                    "read_code",
                    "读取文件",
                    {"type": "object", "properties": {"path": {"type": "string"}}},
                )
            ]
        )
        tools = build_anthropic_tools(reg)
        assert tools[0]["name"] == "read_code"
        assert tools[0]["input_schema"]["properties"]["path"]["type"] == "string"

    def test_missing_top_level_type_normalized_to_object(self):
        reg = _FakeRegistry(
            [
                # 像 read_code 那样只写 properties/required、缺顶层 type 的工具
                _FakeTool(
                    "read_code",
                    "读取文件",
                    {
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                )
            ]
        )
        otools = build_openai_tools(reg)
        params = otools[0]["function"]["parameters"]
        assert params.get("type") == "object"
        assert params["properties"]["path"]["type"] == "string"

        atools = build_anthropic_tools(reg)
        assert atools[0]["input_schema"].get("type") == "object"

    def test_empty_parameters_become_object_schema(self):
        reg = _FakeRegistry([_FakeTool("noop", "无参", {})])
        otools = build_openai_tools(reg)
        assert otools[0]["function"]["parameters"]["type"] == "object"

    def test_timer_params_advertised_in_schema(self):
        reg = _FakeRegistry(
            [
                _FakeTool(
                    "read_code",
                    "读取文件",
                    {"type": "object", "properties": {"path": {"type": "string"}}},
                )
            ]
        )
        otools = build_openai_tools(reg)
        props = otools[0]["function"]["parameters"]["properties"]
        assert "after" in props and "loop" in props and "at" in props

        atools = build_anthropic_tools(reg)
        assert "after" in atools[0]["input_schema"]["properties"]
