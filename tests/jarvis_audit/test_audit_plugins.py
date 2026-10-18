# -*- coding: utf-8 -*-
"""插件 audit 扩展点单元测试（Issue #296）。

验证插件声明的审计 sink 目录能被 AuditSinkRegistry 加载、注册，并在卸载时
精确撤销；以及 AuditLogger 写文件后会把脱敏数据分发到插件 sink。
"""

import os
import shutil
import tempfile

import pytest

from jarvis.jarvis_audit.audit import AuditLogger
from jarvis.jarvis_audit.audit_plugins import AuditSinkRegistry
from jarvis.jarvis_tools.plugin_registry import PluginRegistry

SINGLE_SINK_CODE = '''
AUDIT_SINK_NAME = "webhook_sink"
AUDIT_SINK_DESCRIPTION = "推送审计事件到外部 webhook"

def audit_sink(event_type, data):
    return "pushed"
'''

MULTI_SINK_CODE = '''
def register_audit_sinks():
    return [
        ("siem_sink", lambda event_type, data: "ok", "推送审计事件到 SIEM"),
        ("mq_sink", lambda event_type, data: "ok"),
    ]
'''


@pytest.fixture()
def plugin_audit_sink_dir():
    """创建临时插件审计 sink 目录（形如 <tmp>/plugins/<name>/audit_sinks）。"""
    tmp = tempfile.mkdtemp()
    sinks_dir = os.path.join(tmp, "plugins", "demo_plugin", "audit_sinks")
    os.makedirs(sinks_dir, exist_ok=True)
    open(os.path.join(sinks_dir, "__init__.py"), "w").close()
    with open(os.path.join(sinks_dir, "webhook.py"), "w") as f:
        f.write(SINGLE_SINK_CODE)
    with open(os.path.join(sinks_dir, "multi_sinks.py"), "w") as f:
        f.write(MULTI_SINK_CODE)
    yield sinks_dir
    shutil.rmtree(tmp)


@pytest.fixture()
def clean_registry():
    """隔离测试：清空 PluginRegistry 与 AuditSinkRegistry 登记，测试后恢复。"""
    registry = PluginRegistry.instance()
    sink_registry = AuditSinkRegistry.instance()
    registry.clear()
    sink_registry.clear()
    yield registry
    registry.clear()
    sink_registry.clear()


def test_infer_source_plugin(plugin_audit_sink_dir):
    """从插件审计 sink 目录路径反推来源插件名。"""
    source = AuditSinkRegistry._infer_source_plugin(plugin_audit_sink_dir)
    assert source == "demo_plugin"


def test_infer_source_plugin_non_plugin_dir():
    """非插件目录路径返回 None。"""
    assert AuditSinkRegistry._infer_source_plugin("/tmp/foo/bar") is None
    assert AuditSinkRegistry._infer_source_plugin("") is None


def _register_event_type_sources(registry, event_types):
    """模拟 _load_plugin_configs 解析插件 config 时的行为：按插件名把
    audit.event_types 登记到 PluginRegistry（来源追踪的事实来源）。"""
    registry.register_audit_event_types("demo_plugin", event_types)


def test_load_plugin_sinks(plugin_audit_sink_dir, clean_registry, monkeypatch):
    """插件审计 sink 目录加载并注册到 AuditSinkRegistry。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {
            "audit": {
                "sinks": [plugin_audit_sink_dir],
                "event_types": ["plugin_sync", "plugin_deploy"],
            }
        },
    )
    _register_event_type_sources(
        clean_registry, ["plugin_sync", "plugin_deploy"]
    )
    sink_registry = AuditSinkRegistry.instance()
    sink_registry.load_plugin_sinks()

    names = sorted(s["name"] for s in sink_registry.list_sinks())
    assert names == ["mq_sink", "siem_sink", "webhook_sink"]
    webhook = sink_registry.get("webhook_sink")
    assert webhook is not None
    assert webhook.description == "推送审计事件到外部 webhook"
    assert webhook.plugin == "demo_plugin"
    # 自定义事件类型登记（来源从 PluginRegistry 聚合）
    assert sink_registry.list_event_types() == ["plugin_deploy", "plugin_sync"]
    assert clean_registry.get_plugin_audit_sinks("demo_plugin") == [
        "mq_sink",
        "siem_sink",
        "webhook_sink",
    ]
    assert clean_registry.get_plugin_audit_event_types("demo_plugin") == [
        "plugin_deploy",
        "plugin_sync",
    ]


def test_unregister_by_plugin(plugin_audit_sink_dir, clean_registry, monkeypatch):
    """卸载时精确撤销插件注册的审计扩展（含事件类型）。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {
            "audit": {
                "sinks": [plugin_audit_sink_dir],
                "event_types": ["plugin_sync"],
            }
        },
    )
    _register_event_type_sources(clean_registry, ["plugin_sync"])
    sink_registry = AuditSinkRegistry.instance()
    sink_registry.load_plugin_sinks()
    assert len(sink_registry.list_sinks()) == 3
    assert sink_registry.list_event_types() == ["plugin_sync"]

    count = sink_registry.unregister_by_plugin("demo_plugin")
    assert count == 3
    assert sink_registry.list_sinks() == []
    assert sink_registry.list_event_types() == []
    assert clean_registry.get_plugin_audit_sinks("demo_plugin") == []
    # 事件类型来源登记由 revoke_plugin 的 unregister_plugin 兜底清理
    # （模拟真实卸载流程）
    clean_registry.unregister_plugin("demo_plugin")
    assert clean_registry.get_plugin_audit_event_types("demo_plugin") == []


def test_reload_plugin_sinks(plugin_audit_sink_dir, clean_registry, monkeypatch):
    """reload_plugin_sinks 先撤销旧扩展再按最新配置重载。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {
            "audit": {
                "sinks": [plugin_audit_sink_dir],
                "event_types": ["plugin_sync"],
            }
        },
    )
    _register_event_type_sources(clean_registry, ["plugin_sync"])
    sink_registry = AuditSinkRegistry.instance()
    sink_registry.load_plugin_sinks()
    assert len(sink_registry.list_sinks()) == 3
    assert sink_registry.list_event_types() == ["plugin_sync"]

    # 模拟插件卸载/配置移除：_load_plugin_configs 重新扫描后不再登记事件类型，
    # 全局配置也清空 audit 声明
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {"audit": {"sinks": [], "event_types": []}},
    )
    clean_registry.clear_audit_event_types("demo_plugin")
    sink_registry.reload_plugin_sinks()
    assert sink_registry.list_sinks() == []
    assert sink_registry.list_event_types() == []

    # 恢复配置后 reload：sink 与事件类型重新注册
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {
            "audit": {
                "sinks": [plugin_audit_sink_dir],
                "event_types": ["plugin_sync"],
            }
        },
    )
    _register_event_type_sources(clean_registry, ["plugin_sync"])
    sink_registry.reload_plugin_sinks()
    assert len(sink_registry.list_sinks()) == 3
    assert sink_registry.list_event_types() == ["plugin_sync"]


def test_register_and_execute():
    """直接注册的 sink 可查询并可执行。"""
    sink_registry = AuditSinkRegistry.instance()
    sink_registry.clear()
    received = {}

    def my_sink(event_type, data):
        received["event_type"] = event_type
        received["data"] = data
        return "ok"

    sink_registry.register(
        "my_sink", my_sink, description="desc", plugin="demo_plugin"
    )
    sink = sink_registry.get("my_sink")
    assert sink is not None
    assert sink.plugin == "demo_plugin"
    assert sink.function("user_input", {"a": 1}) == "ok"
    assert received == {"event_type": "user_input", "data": {"a": 1}}

    assert sink_registry.unregister("my_sink") is True
    assert sink_registry.get("my_sink") is None
    sink_registry.clear()


def test_audit_logger_dispatches_to_sink(tmp_path, monkeypatch):
    """AuditLogger.log 写文件后把脱敏数据分发到插件 sink。"""
    sink_registry = AuditSinkRegistry.instance()
    sink_registry.clear()
    received = {}

    def my_sink(event_type, data):
        received["event_type"] = event_type
        received["data"] = data

    sink_registry.register("my_sink", my_sink, plugin="demo_plugin")

    logger = AuditLogger(str(tmp_path))
    logger.log(
        "tool_call",
        tool_name="execute_script",
        arguments={"password": "secret123", "cmd": "ls"},
    )

    assert received["event_type"] == "tool_call"
    # sink 收到的是脱敏后的数据
    assert received["data"]["arguments"]["password"] == "***"
    assert received["data"]["arguments"]["cmd"] == "ls"
    sink_registry.clear()


def test_audit_logger_sink_failure_does_not_break(tmp_path, monkeypatch):
    """sink 抛异常不影响主审计链路（文件仍写入）。"""
    import json

    sink_registry = AuditSinkRegistry.instance()
    sink_registry.clear()

    def bad_sink(event_type, data):
        raise RuntimeError("sink broken")

    sink_registry.register("bad_sink", bad_sink, plugin="demo_plugin")

    logger = AuditLogger(str(tmp_path))
    logger.log("user_input", user_input="hello")  # 不应抛异常

    files = list((tmp_path / "audit").glob("*.jsonl"))
    assert len(files) == 1
    records = [
        json.loads(line)
        for line in files[0].read_text(encoding="utf-8").strip().splitlines()
        if line
    ]
    assert records[0]["event_type"] == "user_input"
    sink_registry.clear()
