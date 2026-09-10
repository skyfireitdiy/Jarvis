# -*- coding: utf-8 -*-
"""openai 原生工具调用：流式 tool_calls 累积/解析单元测试"""

from types import SimpleNamespace

from jarvis.jarvis_platform.openai import _accumulate_openai_stream


def _chunk(content=None, tool_calls=None):
    delta = SimpleNamespace(content=content)
    delta.tool_calls = tool_calls
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def _tool_call(index, id_, name=None, arguments=None):
    fn = None
    if name is not None or arguments is not None:
        fn = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(index=index, id=id_, function=fn)


def test_content_only_stream():
    stream = [_chunk("你"), _chunk("好"), _chunk("。")]
    content, calls = _accumulate_openai_stream(stream)
    assert content == "你好。"
    assert calls is None


def test_tool_calls_split_arguments_merged():
    # 同一 index 的 arguments 分片拼接
    stream = [
        _chunk(tool_calls=[_tool_call(0, "call_x", "add", '{"a": ')]),
        _chunk(tool_calls=[_tool_call(0, None, None, "17, ")]),
        _chunk(tool_calls=[_tool_call(0, None, None, '"b": 25}')]),
    ]
    content, calls = _accumulate_openai_stream(stream)
    assert content is None
    assert len(calls) == 1
    assert calls[0]["id"] == "call_x"
    assert calls[0]["name"] == "add"
    assert calls[0]["arguments"] == {"a": 17, "b": 25}


def test_multiple_parallel_tool_calls():
    stream = [
        _chunk(
            tool_calls=[
                _tool_call(0, "id_1", "read_code", '{"path": "a.py"}'),
                _tool_call(1, "id_2", "search_web", '{"q": "x"}'),
            ]
        )
    ]
    content, calls = _accumulate_openai_stream(stream)
    assert calls[0]["name"] == "read_code"
    assert calls[1]["name"] == "search_web"
    assert calls[0]["arguments"] == {"path": "a.py"}


def test_malformed_arguments_not_crash():
    stream = [_chunk(tool_calls=[_tool_call(0, "id", "t", "{not json}")])]
    content, calls = _accumulate_openai_stream(stream)
    # 非法 JSON 不再包装为 raw_arguments，而是传空参数由工具层报缺失
    assert calls[0]["arguments"] == {}


def test_raw_arguments_not_special_cased():
    # raw_arguments 不再被特殊处理：它就是普通参数名，原样透传
    import json

    inner = json.dumps({"files": [{"file_path": "a.py"}]})
    wrapped = json.dumps({"raw_arguments": inner})
    stream = [_chunk(tool_calls=[_tool_call(0, "id", "edit_file", wrapped)])]
    content, calls = _accumulate_openai_stream(stream)
    assert calls[0]["arguments"] == {"raw_arguments": inner}
