# -*- coding: utf-8 -*-
"""插件 message_types 扩展点单元测试（Issue #298）。

验证插件声明的自定义消息类型目录能被 MessageTypeRegistry 加载、注册，网关
收到对应类型消息时分发到插件处理函数，并在卸载时精确撤销。
"""

import os
import shutil
import tempfile

import pytest

from jarvis.jarvis_tools.plugin_registry import PluginRegistry
from jarvis.jarvis_web_gateway.message_types import MessageTypeRegistry

SINGLE_MESSAGE_TYPE_CODE = '''
MESSAGE_TYPE_NAME = "plugin_sync_msg"
MESSAGE_TYPE_DESCRIPTION = "插件同步消息类型"

def message_handler(message):
    return {"handled": True, "echo": message.get("payload", {}).get("data")}
'''

MULTI_MESSAGE_TYPE_CODE = '''
def register_message_types():
    return [
        ("plugin_sync_msg2", lambda message: {"handled": True}, "第二个消息类型"),
        ("plugin_sync_msg3", lambda message: {"handled": True}),
    ]
'''


@pytest.fixture()
def plugin_message_type_dir():
    """创建临时插件消息类型目录（形如 <tmp>/plugins/<name>/message_types）。"""
    tmp = tempfile.mkdtemp()
    types_dir = os.path.join(tmp, "plugins", "demo_plugin", "message_types")
    os.makedirs(types_dir, exist_ok=True)
    open(os.path.join(types_dir, "__init__.py"), "w").close()
    with open(os.path.join(types_dir, "sync_message.py"), "w") as f:
        f.write(SINGLE_MESSAGE_TYPE_CODE)
    with open(os.path.join(types_dir, "multi_messages.py"), "w") as f:
        f.write(MULTI_MESSAGE_TYPE_CODE)
    yield types_dir
    shutil.rmtree(tmp)


@pytest.fixture()
def clean_registry():
    """隔离测试：清空 PluginRegistry 与 MessageTypeRegistry 登记，测试后恢复。"""
    registry = PluginRegistry.instance()
    message_registry = MessageTypeRegistry.instance()
    registry.clear()
    message_registry.clear()
    yield registry
    registry.clear()
    message_registry.clear()


def test_infer_source_plugin(plugin_message_type_dir):
    """从插件消息类型目录路径反推来源插件名。"""
    source = MessageTypeRegistry._infer_source_plugin(plugin_message_type_dir)
    assert source == "demo_plugin"


def test_infer_source_plugin_non_plugin_dir():
    """非插件目录路径返回 None。"""
    assert MessageTypeRegistry._infer_source_plugin("/tmp/foo/bar") is None
    assert MessageTypeRegistry._infer_source_plugin("") is None


def test_load_plugin_message_types(plugin_message_type_dir, clean_registry, monkeypatch):
    """插件消息类型目录加载并注册到 MessageTypeRegistry。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {"message_types": [plugin_message_type_dir]},
    )
    message_registry = MessageTypeRegistry.instance()
    message_registry.load_plugin_message_types()

    names = sorted(m["name"] for m in message_registry.list_message_types())
    assert names == ["plugin_sync_msg", "plugin_sync_msg2", "plugin_sync_msg3"]
    sync_message = message_registry.get("plugin_sync_msg")
    assert sync_message is not None
    assert sync_message.description == "插件同步消息类型"
    assert sync_message.plugin == "demo_plugin"
    assert clean_registry.get_plugin_message_types("demo_plugin") == [
        "plugin_sync_msg",
        "plugin_sync_msg2",
        "plugin_sync_msg3",
    ]


def test_unregister_message_types_by_plugin(
    plugin_message_type_dir, clean_registry, monkeypatch
):
    """卸载时精确撤销插件注册的消息类型。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {"message_types": [plugin_message_type_dir]},
    )
    message_registry = MessageTypeRegistry.instance()
    message_registry.load_plugin_message_types()
    assert len(message_registry.list_message_types()) == 3

    count = message_registry.unregister_by_plugin("demo_plugin")
    assert count == 3
    assert message_registry.list_message_types() == []
    assert clean_registry.get_plugin_message_types("demo_plugin") == []


def test_reload_plugin_message_types(
    plugin_message_type_dir, clean_registry, monkeypatch
):
    """reload_plugin_message_types 先撤销旧类型再按最新配置重载。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {"message_types": [plugin_message_type_dir]},
    )
    message_registry = MessageTypeRegistry.instance()
    message_registry.load_plugin_message_types()
    assert len(message_registry.list_message_types()) == 3

    # 清空配置后 reload：消息类型应被撤销
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {"message_types": []},
    )
    message_registry.reload_plugin_message_types()
    assert message_registry.list_message_types() == []

    # 恢复配置后 reload：消息类型重新注册
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {"message_types": [plugin_message_type_dir]},
    )
    message_registry.reload_plugin_message_types()
    assert len(message_registry.list_message_types()) == 3


def test_register_and_dispatch():
    """直接注册的消息类型可查询并可分发执行。"""
    message_registry = MessageTypeRegistry.instance()
    message_registry.clear()
    executed = {}

    def my_handler(message):
        executed["type"] = message.get("type")
        return {"handled": True}

    message_registry.register(
        "my_custom_type", my_handler, description="desc", plugin="demo_plugin"
    )
    message_type = message_registry.get("my_custom_type")
    assert message_type is not None
    assert message_type.plugin == "demo_plugin"

    # 通过 node_manager 分发
    from jarvis.jarvis_web_gateway.node_manager import NodeConnectionManager

    manager = NodeConnectionManager.__new__(NodeConnectionManager)
    response = manager._dispatch_plugin_message(
        {"type": "my_custom_type", "request_id": "req-1", "payload": {"a": 1}}
    )
    assert response is not None
    assert response["type"] == "my_custom_type"
    assert response["request_id"] == "req-1"
    assert response["payload"] == {"handled": True}
    assert executed == {"type": "my_custom_type"}

    assert message_registry.unregister("my_custom_type") is True
    assert message_registry.get("my_custom_type") is None
    message_registry.clear()


def test_dispatch_unregistered_type_returns_none():
    """未注册的消息类型分发返回 None（走原有 unhandled 逻辑）。"""
    from jarvis.jarvis_web_gateway.node_manager import NodeConnectionManager

    message_registry = MessageTypeRegistry.instance()
    message_registry.clear()
    manager = NodeConnectionManager.__new__(NodeConnectionManager)
    assert (
        manager._dispatch_plugin_message(
            {"type": "unknown_type", "request_id": "req-1"}
        )
        is None
    )
    message_registry.clear()


def test_dispatch_handler_exception_returns_error():
    """处理函数抛异常时返回错误响应，不阻断连接。"""
    from jarvis.jarvis_web_gateway.node_manager import NodeConnectionManager

    message_registry = MessageTypeRegistry.instance()
    message_registry.clear()

    def bad_handler(message):
        raise RuntimeError("boom")

    message_registry.register("bad_type", bad_handler, plugin="demo_plugin")
    manager = NodeConnectionManager.__new__(NodeConnectionManager)
    response = manager._dispatch_plugin_message(
        {"type": "bad_type", "request_id": "req-1"}
    )
    assert response is not None
    assert response["type"] == "error"
    assert response["payload"]["code"] == "PLUGIN_MESSAGE_HANDLER_FAILED"
    message_registry.clear()
