"""Jarvis Agent SDK 增强模块测试。

验证编排 API（run_agents_parallel / pipeline）、结构化输出（run_structured）、
生命周期回调（on_event）。使用 FakeAgent 隔离 LLM 调用，聚焦 SDK 逻辑本身。
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from jarvis.jarvis_agent.event_bus import EventBus
from jarvis.jarvis_agent.sdk import (
    EVENT_AFTER_SUMMARY,
    EVENT_TASK_COMPLETED,
    _extract_json,
    on_event,
    pipeline,
    run_agents_parallel,
    run_structured,
)


class FakeAgent:
    """模拟 Agent：记录调用，返回预设输出，带 event_bus。"""

    def __init__(self, output: str = "ok", name: str = "fake") -> None:
        self.output = output
        self.name = name
        self.event_bus = EventBus()
        self.calls: list[str] = []

    def run(self, user_input: str) -> str:
        self.calls.append(user_input)
        return self.output


class FailingAgent(FakeAgent):
    def run(self, user_input: str) -> str:
        self.calls.append(user_input)
        raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# run_agents_parallel
# ---------------------------------------------------------------------------


def test_run_agents_parallel_returns_results_in_order():
    a = FakeAgent("A")
    b = FakeAgent("B")
    results = run_agents_parallel([(a, "task1"), (b, "task2")])
    assert results == ["A", "B"]
    assert a.calls == ["task1"]
    assert b.calls == ["task2"]


def test_run_agents_parallel_empty():
    assert run_agents_parallel([]) == []


def test_run_agents_parallel_single_failure_does_not_block_others():
    bad = FailingAgent()
    good = FakeAgent("good")
    results = run_agents_parallel([(bad, "x"), (good, "y")])
    # 失败的位置为 None，其余正常
    assert results[1] == "good"
    assert results[0] is None


def test_run_agents_parallel_rejects_non_string_task():
    a = FakeAgent()
    # 运行时构造非法输入（绕过静态类型检查），验证运行时类型校验
    bad_input = cast(Any, [(a, 123)])
    with pytest.raises(TypeError):
        run_agents_parallel(bad_input)


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------


def test_pipeline_chains_output_as_input():
    a = FakeAgent("step1")
    b = FakeAgent("step2")
    results = pipeline(
        [
            (a, "fixed task"),
            (b, lambda prev: f"got: {prev}"),
        ]
    )
    assert results == ["step1", "step2"]
    assert a.calls == ["fixed task"]
    # 第二个 stage 的输入是第一个的输出
    assert b.calls == ["got: step1"]


def test_pipeline_initial_input_passed_to_first_callable():
    a = FakeAgent("out")
    results = pipeline([(a, lambda prev: f"init:{prev}")], initial_input="seed")
    assert a.calls == ["init:seed"]
    assert results == ["out"]


def test_pipeline_stops_on_failure():
    a = FakeAgent("ok")
    bad = FailingAgent()
    results = pipeline([(a, "t1"), (bad, "t2"), (a, "t3")])
    # 前两个 stage 有结果（第二个为 None），第三个不执行
    assert results == ["ok", None]
    assert len(a.calls) == 1  # 第三个 stage 未执行


# ---------------------------------------------------------------------------
# run_structured
# ---------------------------------------------------------------------------


def test_run_structured_parses_json_output():
    agent = FakeAgent('{"name": "jarvis", "count": 3}')
    result = run_structured(agent, "分析")
    assert result == {"name": "jarvis", "count": 3}


def test_run_structured_handles_markdown_fence():
    agent = FakeAgent('```json\n{"ok": true}\n```')
    result = run_structured(agent, "分析")
    assert result == {"ok": True}


def test_run_structured_handles_extra_text_before_json():
    agent = FakeAgent('分析结果如下：\n{"items": [1, 2, 3]}')
    result = run_structured(agent, "分析")
    assert result == {"items": [1, 2, 3]}


def test_run_structured_with_schema_hint():
    agent = FakeAgent('{"status": "ok"}')
    schema = {"type": "object", "properties": {"status": {"type": "string"}}}
    result = run_structured(agent, "分析", schema=schema)
    assert result == {"status": "ok"}
    # 任务中应包含 schema 内容
    assert "status" in agent.calls[0]


def test_run_structured_raises_on_no_output():
    agent = FakeAgent("")  # 空输出
    with pytest.raises(ValueError):
        run_structured(agent, "分析")


def test_run_structured_raises_on_invalid_json():
    agent = FakeAgent("这不是 JSON")
    with pytest.raises(ValueError):
        run_structured(agent, "分析")


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------


def test_extract_json_plain():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_array():
    assert _extract_json("[1, 2, 3]") == [1, 2, 3]


def test_extract_json_fenced_with_lang():
    assert _extract_json('```json\n{"x": 1}\n```') == {"x": 1}


def test_extract_json_raises_on_garbage():
    with pytest.raises(ValueError):
        _extract_json("nothing here")


# ---------------------------------------------------------------------------
# on_event
# ---------------------------------------------------------------------------


def test_on_event_subscribes_and_fires():
    agent = FakeAgent()
    fired: list[str] = []

    def handler(agent=None, **kwargs):
        if agent is not None:
            fired.append(agent.name)

    on_event(agent, EVENT_TASK_COMPLETED, handler)
    agent.event_bus.emit(EVENT_TASK_COMPLETED, agent=agent)
    assert fired == ["fake"]


def test_on_event_after_summary_payload():
    agent = FakeAgent()
    captured = {}

    def handler(agent=None, summary=None, **kwargs):
        captured["summary"] = summary

    on_event(agent, EVENT_AFTER_SUMMARY, handler)
    agent.event_bus.emit(EVENT_AFTER_SUMMARY, agent=agent, summary="done")
    assert captured["summary"] == "done"


def test_on_event_requires_event_bus():
    class NoBus:
        pass

    with pytest.raises(AttributeError):
        on_event(NoBus(), EVENT_TASK_COMPLETED, lambda **kw: None)


def test_parallel_is_thread_safe():
    """并行执行时各 Agent 独立，不共享调用列表。"""
    agents = [FakeAgent(str(i)) for i in range(5)]
    tasks = [(a, f"task{i}") for i, a in enumerate(agents)]
    results = run_agents_parallel(tasks)
    assert results == ["0", "1", "2", "3", "4"]
    for i, a in enumerate(agents):
        assert a.calls == [f"task{i}"]
