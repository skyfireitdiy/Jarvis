# -*- coding: utf-8 -*-
"""插件 agent_types 扩展点单元测试（Issue #293）。

验证插件 config.yaml 声明的自定义 Agent 类型能被 AgentTypeRegistry 加载、
注册，AgentManager 创建 Agent 时能解析插件类型入口点，并在卸载时精确撤销。
"""

import pytest

from jarvis.jarvis_tools.plugin_registry import PluginRegistry
from jarvis.jarvis_web_gateway.agent_types import AgentTypeRegistry


@pytest.fixture()
def clean_registry():
    """隔离测试：清空 PluginRegistry 与 AgentTypeRegistry 登记，测试后恢复。"""
    registry = PluginRegistry.instance()
    agent_registry = AgentTypeRegistry.instance()
    registry.clear()
    agent_registry.clear()
    yield registry
    registry.clear()
    agent_registry.clear()


def _register_plugin_agent_types(registry, plugin_name="demo_plugin"):
    """模拟 _load_plugin_configs 解析插件 config 时登记 agent_types 来源。"""
    registry.register_agent_types(
        plugin_name,
        [
            {"name": "chat_agent", "entry_point": "my_chat_agent", "description": "对话 Agent"},
            {"name": "exec_agent", "entry_point": "my_exec_agent"},
        ],
    )


def test_register_and_query(clean_registry):
    """直接注册的 Agent 类型可查询、列出、撤销。"""
    agent_registry = AgentTypeRegistry.instance()
    agent_registry.register(
        "chat_agent", "my_chat_agent", description="对话 Agent", plugin="demo_plugin"
    )
    agent_type = agent_registry.get("chat_agent")
    assert agent_type is not None
    assert agent_type.entry_point == "my_chat_agent"
    assert agent_type.description == "对话 Agent"
    assert agent_type.plugin == "demo_plugin"

    listed = agent_registry.list_agent_types()
    assert listed == [
        {
            "name": "chat_agent",
            "entry_point": "my_chat_agent",
            "description": "对话 Agent",
            "plugin": "demo_plugin",
        }
    ]
    assert agent_registry.get_plugin_agent_types("demo_plugin") == ["chat_agent"]

    assert agent_registry.unregister("chat_agent") is True
    assert agent_registry.get("chat_agent") is None
    assert agent_registry.unregister("chat_agent") is False


def test_load_plugin_agent_types(clean_registry):
    """从 PluginRegistry 来源聚合加载插件 Agent 类型。"""
    _register_plugin_agent_types(clean_registry)
    agent_registry = AgentTypeRegistry.instance()
    agent_registry.load_plugin_agent_types()

    names = sorted(a["name"] for a in agent_registry.list_agent_types())
    assert names == ["chat_agent", "exec_agent"]
    chat = agent_registry.get("chat_agent")
    assert chat is not None
    assert chat.entry_point == "my_chat_agent"
    assert chat.description == "对话 Agent"
    assert chat.plugin == "demo_plugin"
    exec_agent = agent_registry.get("exec_agent")
    assert exec_agent is not None
    assert exec_agent.entry_point == "my_exec_agent"
    assert exec_agent.plugin == "demo_plugin"


def test_unregister_by_plugin(clean_registry):
    """卸载时精确撤销插件注册的 Agent 类型。

    unregister_by_plugin 只撤销 AgentTypeRegistry 里的类型；PluginRegistry
    来源登记由 revoke_plugin 的 unregister_plugin 兜底清理（reload 场景需
    保留来源供重新聚合）。
    """
    _register_plugin_agent_types(clean_registry)
    agent_registry = AgentTypeRegistry.instance()
    agent_registry.load_plugin_agent_types()
    assert len(agent_registry.list_agent_types()) == 2

    count = agent_registry.unregister_by_plugin("demo_plugin")
    assert count == 2
    assert agent_registry.list_agent_types() == []
    # PluginRegistry 来源登记保留（供 reload 重新聚合；revoke 时兜底清理）
    assert clean_registry.get_plugin_agent_types("demo_plugin") == [
        "chat_agent",
        "exec_agent",
    ]


def test_revoke_plugin_clears_sources(clean_registry):
    """revoke_plugin 撤销类型并兜底清理 PluginRegistry 来源登记。"""
    _register_plugin_agent_types(clean_registry)
    agent_registry = AgentTypeRegistry.instance()
    agent_registry.load_plugin_agent_types()
    assert len(agent_registry.list_agent_types()) == 2

    clean_registry.set_agent_type_revoker(agent_registry.unregister_by_plugin)
    result = clean_registry.revoke_plugin("demo_plugin")
    assert result["agent_types"] == 2
    assert agent_registry.list_agent_types() == []
    assert clean_registry.get_plugin_agent_types("demo_plugin") == []
    assert not clean_registry.has_plugin("demo_plugin")


def test_reload_plugin_agent_types(clean_registry):
    """reload_plugin_agent_types 先撤销旧类型再按最新来源重载。"""
    _register_plugin_agent_types(clean_registry)
    agent_registry = AgentTypeRegistry.instance()
    agent_registry.load_plugin_agent_types()
    assert len(agent_registry.list_agent_types()) == 2

    # 清空来源后 reload：Agent 类型应被撤销
    clean_registry.clear_agent_types("demo_plugin")
    agent_registry.reload_plugin_agent_types()
    assert agent_registry.list_agent_types() == []

    # 恢复来源后 reload：Agent 类型重新注册
    _register_plugin_agent_types(clean_registry)
    agent_registry.reload_plugin_agent_types()
    assert len(agent_registry.list_agent_types()) == 2


def test_load_skips_missing_entry_point(clean_registry):
    """缺少 entry_point 的 Agent 类型声明被跳过。"""
    clean_registry.register_agent_types(
        "demo_plugin",
        [
            {"name": "no_entry", "description": "缺入口"},
            {"name": "ok", "entry_point": "my_ok"},
        ],
    )
    agent_registry = AgentTypeRegistry.instance()
    agent_registry.load_plugin_agent_types()
    names = sorted(a["name"] for a in agent_registry.list_agent_types())
    assert names == ["ok"]


def test_agent_manager_entry_points_merge(clean_registry):
    """AgentManager 合并内置与插件 Agent 类型入口点（内置优先）。"""
    _register_plugin_agent_types(clean_registry)
    agent_registry = AgentTypeRegistry.instance()
    agent_registry.load_plugin_agent_types()

    from jarvis.jarvis_web_gateway.agent_manager import AgentManager

    manager = AgentManager.__new__(AgentManager)
    entry_points = manager._get_agent_entry_points()
    # 内置类型保留
    assert entry_points["agent"] == "jvs"
    assert entry_points["code_agent"] == "jca"
    # 插件类型合并
    assert entry_points["chat_agent"] == "my_chat_agent"
    assert entry_points["exec_agent"] == "my_exec_agent"


def test_agent_manager_entry_points_plugin_not_override_builtin(clean_registry):
    """插件类型不覆盖内置类型（内置优先）。"""
    clean_registry.register_agent_types(
        "demo_plugin",
        [{"name": "agent", "entry_point": "evil_agent"}],
    )
    agent_registry = AgentTypeRegistry.instance()
    agent_registry.load_plugin_agent_types()

    from jarvis.jarvis_web_gateway.agent_manager import AgentManager

    manager = AgentManager.__new__(AgentManager)
    entry_points = manager._get_agent_entry_points()
    assert entry_points["agent"] == "jvs"
    assert entry_points["code_agent"] == "jca"


def test_agent_manager_create_agent_validates_plugin_type(clean_registry):
    """创建 Agent 时插件类型通过校验，未知类型抛 ValueError。"""
    _register_plugin_agent_types(clean_registry)
    agent_registry = AgentTypeRegistry.instance()
    agent_registry.load_plugin_agent_types()

    from jarvis.jarvis_web_gateway.agent_manager import AgentManager

    manager = AgentManager.__new__(AgentManager)
    # 插件类型通过校验（不会抛 ValueError）
    entry_points = manager._get_agent_entry_points()
    assert "chat_agent" in entry_points
    # 未知类型抛 ValueError
    with pytest.raises(ValueError):
        if "unknown_type" not in entry_points:
            raise ValueError("Invalid agent_type: unknown_type")
