# -*- coding: utf-8 -*-
"""审计系统测试：可配置、默认关闭、JSONL 写入、敏感脱敏。"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from jarvis.jarvis_audit.audit import AuditLogger
from jarvis.jarvis_audit.audit import _redact
from jarvis.jarvis_audit.audit import log_event
from jarvis.jarvis_utils.config import set_global_config_data


@pytest.fixture(autouse=True)
def _reset_config():
    """每个用例前重置全局配置，保证默认关闭。"""
    set_global_config_data({})
    yield
    set_global_config_data({})


def _audit_dir(tmp_path: Path) -> Path:
    return tmp_path / "audit"


def _read_lines(tmp_path: Path) -> list:
    audit_dir = _audit_dir(tmp_path)
    files = list(audit_dir.glob("*.jsonl"))
    records = []
    for f in files:
        for line in f.read_text(encoding="utf-8").strip().splitlines():
            if line:
                records.append(json.loads(line))
    return records


def test_log_event_disabled_writes_nothing(tmp_path, monkeypatch):
    """默认关闭时 log_event 不写任何日志文件。"""
    # 强制默认关闭，并注入指向临时目录的 logger
    monkeypatch.setattr("jarvis.jarvis_audit.audit.is_enable_audit", lambda: False)
    monkeypatch.setattr("jarvis.jarvis_audit.audit._logger", AuditLogger(str(tmp_path)))
    log_event("user_input", user_input="hello")
    assert not _audit_dir(tmp_path).exists() or not list(
        _audit_dir(tmp_path).glob("*.jsonl")
    )


def test_log_event_enabled_writes_jsonl(tmp_path, monkeypatch):
    """开启后 log_event 写入 JSONL 且字段完整。"""
    monkeypatch.setattr("jarvis.jarvis_audit.audit.is_enable_audit", lambda: True)
    monkeypatch.setattr("jarvis.jarvis_audit.audit._logger", AuditLogger(str(tmp_path)))
    log_event("user_input", user_input="帮我写代码")
    records = _read_lines(tmp_path)
    assert len(records) == 1
    rec = records[0]
    assert rec["event_type"] == "user_input"
    assert "timestamp" in rec
    assert rec["data"]["user_input"] == "帮我写代码"


def test_redact_sensitive_fields(tmp_path, monkeypatch):
    """敏感字段值被打码为 ***。"""
    monkeypatch.setattr("jarvis.jarvis_audit.audit.is_enable_audit", lambda: True)
    logger = AuditLogger(str(tmp_path))
    logger.log(
        "tool_call",
        tool_name="execute_script",
        arguments={"password": "secret123", "token": "abc", "cmd": "ls"},
    )
    records = _read_lines(tmp_path)
    data = records[0]["data"]["arguments"]
    assert data["password"] == "***"
    assert data["token"] == "***"
    assert data["cmd"] == "ls"


def test_redact_nested_dict():
    """递归脱敏：敏感键的整个值（含嵌套字典）被打码为 ***。"""
    result = _redact(
        {
            "auth": {"api_key": "k1"},
            "args": {"username": "u", "secret": "s"},
            "safe": "ok",
        }
    )
    # auth 是敏感键，整个值（含嵌套 api_key）打码
    assert result["auth"] == "***"
    assert result["args"]["secret"] == "***"
    assert result["args"]["username"] == "u"
    assert result["safe"] == "ok"


def test_event_types_all_recorded(tmp_path, monkeypatch):
    """user_input / tool_call / task_completed 三类事件均可记录。"""
    monkeypatch.setattr("jarvis.jarvis_audit.audit.is_enable_audit", lambda: True)
    logger = AuditLogger(str(tmp_path))
    logger.log("user_input", user_input="hi")
    logger.log("tool_call", tool_name="read_code")
    logger.log("task_completed", auto_completed=True, result="done")
    types = [r["event_type"] for r in _read_lines(tmp_path)]
    assert types == ["user_input", "tool_call", "task_completed"]


def test_daily_file_partition(tmp_path, monkeypatch):
    """按天分文件：文件名为 YYYY-MM-DD.jsonl。"""
    monkeypatch.setattr("jarvis.jarvis_audit.audit.is_enable_audit", lambda: True)
    logger = AuditLogger(str(tmp_path))
    logger.log("user_input", user_input="x")
    expected = f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    files = list(_audit_dir(tmp_path).glob("*.jsonl"))
    assert [f.name for f in files] == [expected]


def test_redact_compound_sensitive_keys():
    """子串匹配：api_key / access_token / secret_key 等复合敏感键也被打码。"""
    result = _redact(
        {
            "api_key": "k1",
            "access_token": "t1",
            "secret_key": "s1",
            "client_secret": "c1",
            "auth_token": "a1",
            "username": "u1",
            "api_base": "https://x",
        }
    )
    assert result["api_key"] == "***"
    assert result["access_token"] == "***"
    assert result["secret_key"] == "***"
    assert result["client_secret"] == "***"
    assert result["auth_token"] == "***"
    assert result["username"] == "u1"
    assert result["api_base"] == "https://x"


def test_redact_compound_nested_dict():
    """嵌套字典中的复合敏感键同样被打码。"""
    result = _redact({"args": {"api_key": "k", "model": "gpt"}})
    assert result["args"]["api_key"] == "***"
    assert result["args"]["model"] == "gpt"


def test_call_tools_audit_no_leak(tmp_path, monkeypatch):
    """文本协议 tool_call 审计：不记录原始 response，arguments 脱敏后无敏感明文。"""
    from jarvis.jarvis_agent import Agent
    import jarvis.jarvis_audit.audit as audit_mod
    from jarvis.jarvis_audit.audit import AuditLogger

    # 控制 _is_audit_enabled（读 config）与 log_event（读 audit）两处开关
    monkeypatch.setattr("jarvis.jarvis_utils.config.is_enable_audit", lambda: True)
    monkeypatch.setattr("jarvis.jarvis_audit.audit.is_enable_audit", lambda: True)
    monkeypatch.setattr(
        "jarvis.jarvis_agent.execute_tool_call", lambda *a, **k: (True, "ok")
    )
    audit_mod._logger = AuditLogger(str(tmp_path))

    agent = object.__new__(Agent)
    resp = '{"name": "execute_script", "arguments": {"api_key": "sk-123", "cmd": "ls"}}'
    agent._call_tools(resp)

    records = _read_lines(tmp_path)
    assert len(records) == 1
    data = records[0]["data"]
    # 不记录原始 response 字符串，避免泄露敏感明文
    assert "response" not in data
    assert data["tool_name"] == "execute_script"
    assert data["arguments"]["api_key"] == "***"
    assert data["arguments"]["cmd"] == "ls"
    # 整个审计记录序列化后不得出现敏感明文
    assert "sk-123" not in json.dumps(records)


def test_call_tools_disabled_no_parse(tmp_path, monkeypatch):
    """默认关闭时 _call_tools 不解析 response，保持零开销。"""
    from jarvis.jarvis_agent import Agent

    monkeypatch.setattr("jarvis.jarvis_utils.config.is_enable_audit", lambda: False)
    monkeypatch.setattr("jarvis.jarvis_audit.audit.is_enable_audit", lambda: False)
    monkeypatch.setattr(
        "jarvis.jarvis_agent.execute_tool_call", lambda *a, **k: (True, "ok")
    )

    agent = object.__new__(Agent)
    # 若关闭时仍调用 _extract_tool_arguments 会因 response 非法 JSON 抛错，这里验证不触发
    agent._call_tools("not valid json {{{")
    assert not _audit_dir(tmp_path).exists() or not list(
        _audit_dir(tmp_path).glob("*.jsonl")
    )
