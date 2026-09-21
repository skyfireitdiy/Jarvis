# -*- coding: utf-8 -*-
"""JevPlatform 输入解析与截断的单测。

覆盖两类问题：
1. 消息超长时，基类通用截断会按字符硬切并追加裸换行，产出非法 JSON
   （"Invalid control character" / "Unterminated string"）。JevPlatform 重写
   _truncate_message_if_needed 做 JSON 结构化截断，保证结果仍是合法 JSON。
2. parse_state_and_questions 对裸控制字符的容错（strict=False）。
"""

import json
from unittest.mock import patch

import pytest

from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.jev import JevPlatform


def _make_platform():
    """构造一个未联网的 JevPlatform 实例（仅用于调用纯逻辑方法）。"""
    p = JevPlatform.__new__(JevPlatform)
    p.platform_type = "eval"
    p.messages = []
    p.suppress_output = True
    p._llm_config = {}
    return p


def _big_payload(state_len: int = 2000) -> str:
    return json.dumps(
        {
            "state": "任务描述：" + ("x" * state_len),
            "questions": {"q1": {"type": "noul", "instructions": "是否相关？"}},
        },
        ensure_ascii=False,
    )


# --------------------------------------------------------------------------
# 截断：修复前基类产出非法 JSON，修复后 JEV 产出合法 JSON
# --------------------------------------------------------------------------


def test_base_truncation_breaks_json():
    """记录基类截断会破坏 JSON（回归护栏：说明为何需要重写）。"""
    raw = _big_payload()
    p = _make_platform()
    with (
        patch.object(JevPlatform, "get_remaining_token_count", return_value=300),
        patch.object(
            JevPlatform, "_get_platform_max_input_token_count", return_value=10000
        ),
    ):
        broken = BasePlatform._truncate_message_if_needed(p, raw)

    with pytest.raises(Exception):
        json.loads(broken)


def test_jev_truncation_keeps_valid_json():
    raw = _big_payload()
    p = _make_platform()
    with (
        patch.object(JevPlatform, "get_remaining_token_count", return_value=300),
        patch.object(
            JevPlatform, "_get_platform_max_input_token_count", return_value=10000
        ),
    ):
        truncated = JevPlatform._truncate_message_if_needed(p, raw)

    # 截断结果必须是合法 JSON，且 questions 完整保留
    payload = json.loads(truncated)
    assert "q1" in payload["questions"]
    assert "已截断" in payload["state"]
    assert len(truncated) < len(raw)


def test_jev_truncation_result_parses():
    """端到端：截断结果可直接被 parse_state_and_questions 消费。"""
    raw = _big_payload()
    p = _make_platform()
    with (
        patch.object(JevPlatform, "get_remaining_token_count", return_value=300),
        patch.object(
            JevPlatform, "_get_platform_max_input_token_count", return_value=10000
        ),
    ):
        truncated = JevPlatform._truncate_message_if_needed(p, raw)

    state, questions = JevPlatform.parse_state_and_questions(truncated)
    assert "q1" in questions
    assert state.endswith("已截断以避免超出上下文限制)")


def test_jev_truncation_noop_when_fits():
    """消息未超限时原样返回，不做任何改写。"""
    raw = _big_payload(state_len=10)
    p = _make_platform()
    with (
        patch.object(JevPlatform, "get_remaining_token_count", return_value=100000),
        patch.object(
            JevPlatform, "_get_platform_max_input_token_count", return_value=100000
        ),
    ):
        assert JevPlatform._truncate_message_if_needed(p, raw) == raw


def test_jev_truncation_keeps_non_string_state():
    """state 非字符串（如对象）时不做截断，避免破坏结构。"""
    raw = json.dumps(
        {
            "state": {"nested": "x" * 2000},
            "questions": {"q1": {"type": "noul", "instructions": "是否相关？"}},
        },
        ensure_ascii=False,
    )
    p = _make_platform()
    with (
        patch.object(JevPlatform, "get_remaining_token_count", return_value=300),
        patch.object(
            JevPlatform, "_get_platform_max_input_token_count", return_value=10000
        ),
    ):
        assert JevPlatform._truncate_message_if_needed(p, raw) == raw


def test_jev_truncation_keeps_invalid_json_as_is():
    """输入不是合法 JSON 时不擅自改写，交上层处理。"""
    raw = "这不是 JSON" + "x" * 5000
    p = _make_platform()
    with (
        patch.object(JevPlatform, "get_remaining_token_count", return_value=300),
        patch.object(
            JevPlatform, "_get_platform_max_input_token_count", return_value=10000
        ),
    ):
        assert JevPlatform._truncate_message_if_needed(p, raw) == raw


# --------------------------------------------------------------------------
# 解析：裸控制字符容错
# --------------------------------------------------------------------------


def test_parse_accepts_raw_newline_in_string():
    payload = {
        "state": "任务描述：第一行\n第二行",
        "questions": {"q1": {"type": "noul", "instructions": "是否相关？"}},
    }
    raw = json.dumps(payload, ensure_ascii=False).replace("\\n", "\n")

    # 默认 strict=True 应当拒绝
    with pytest.raises(Exception):
        json.loads(raw)

    state, questions = JevPlatform.parse_state_and_questions(raw)
    assert "第一行" in state and "第二行" in state
    assert "q1" in questions


def test_parse_accepts_raw_tab_in_string():
    payload = {
        "state": "任务描述：A\tB",
        "questions": {"q1": {"type": "noul", "instructions": "是否相关？"}},
    }
    raw = json.dumps(payload, ensure_ascii=False).replace("\\t", "\t")

    state, questions = JevPlatform.parse_state_and_questions(raw)
    assert "\t" in state
    assert "q1" in questions


def test_parse_invalid_json_raises_value_error():
    with pytest.raises(ValueError) as exc:
        JevPlatform.parse_state_and_questions("这不是 JSON")
    assert "JSON" in str(exc.value)


def test_parse_missing_state_raises():
    with pytest.raises(ValueError) as exc:
        JevPlatform.parse_state_and_questions('{"questions": {}}')
    assert "state" in str(exc.value)


def test_parse_accepts_dict_input():
    state, questions = JevPlatform.parse_state_and_questions(
        {
            "state": "内容",
            "questions": {"q1": {"type": "noul", "instructions": "是否相关？"}},
        }
    )
    assert state == "内容"
    assert "q1" in questions
