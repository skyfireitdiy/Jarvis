# -*- coding: utf-8 -*-
"""插件 timer_actions 扩展点单元测试（Issue #295）。

验证插件声明的定时动作目录能被 TimerActionRegistry 加载、注册，并在卸载时
精确撤销。
"""

import os
import shutil
import tempfile

import pytest

from jarvis.jarvis_tools.plugin_registry import PluginRegistry
from jarvis.jarvis_web_gateway.timer_actions import TimerActionRegistry

SINGLE_ACTION_CODE = '''
TIMER_ACTION_NAME = "plugin_sync"
TIMER_ACTION_DESCRIPTION = "定时执行插件同步动作"

def timer_action(name, params):
    return "synced"
'''

MULTI_ACTION_CODE = '''
def register_timer_actions():
    return [
        ("plugin_sync2", lambda name, params: "ok", "第二个动作"),
        ("plugin_sync3", lambda name, params: "ok"),
    ]
'''


@pytest.fixture()
def plugin_timer_action_dir():
    """创建临时插件定时动作目录（形如 <tmp>/plugins/<name>/timer_actions）。"""
    tmp = tempfile.mkdtemp()
    actions_dir = os.path.join(tmp, "plugins", "demo_plugin", "timer_actions")
    os.makedirs(actions_dir, exist_ok=True)
    open(os.path.join(actions_dir, "__init__.py"), "w").close()
    with open(os.path.join(actions_dir, "sync_action.py"), "w") as f:
        f.write(SINGLE_ACTION_CODE)
    with open(os.path.join(actions_dir, "multi_actions.py"), "w") as f:
        f.write(MULTI_ACTION_CODE)
    yield actions_dir
    shutil.rmtree(tmp)


@pytest.fixture()
def clean_registry():
    """隔离测试：清空 PluginRegistry 与 TimerActionRegistry 登记，测试后恢复。"""
    registry = PluginRegistry.instance()
    timer_registry = TimerActionRegistry.instance()
    registry.clear()
    timer_registry.clear()
    yield registry
    registry.clear()
    timer_registry.clear()


def test_infer_source_plugin(plugin_timer_action_dir):
    """从插件定时动作目录路径反推来源插件名。"""
    source = TimerActionRegistry._infer_source_plugin(plugin_timer_action_dir)
    assert source == "demo_plugin"


def test_infer_source_plugin_non_plugin_dir():
    """非插件目录路径返回 None。"""
    assert TimerActionRegistry._infer_source_plugin("/tmp/foo/bar") is None
    assert TimerActionRegistry._infer_source_plugin("") is None


def test_load_plugin_actions(plugin_timer_action_dir, clean_registry, monkeypatch):
    """插件定时动作目录加载并注册到 TimerActionRegistry。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {"timer_actions": [plugin_timer_action_dir]},
    )
    timer_registry = TimerActionRegistry.instance()
    timer_registry.load_plugin_actions()

    names = sorted(a["name"] for a in timer_registry.list_actions())
    assert names == ["plugin_sync", "plugin_sync2", "plugin_sync3"]
    sync_action = timer_registry.get("plugin_sync")
    assert sync_action is not None
    assert sync_action.description == "定时执行插件同步动作"
    assert sync_action.plugin == "demo_plugin"
    assert clean_registry.get_plugin_timer_actions("demo_plugin") == [
        "plugin_sync",
        "plugin_sync2",
        "plugin_sync3",
    ]


def test_unregister_actions_by_plugin(
    plugin_timer_action_dir, clean_registry, monkeypatch
):
    """卸载时精确撤销插件注册的定时动作。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {"timer_actions": [plugin_timer_action_dir]},
    )
    timer_registry = TimerActionRegistry.instance()
    timer_registry.load_plugin_actions()
    assert len(timer_registry.list_actions()) == 3

    count = timer_registry.unregister_actions_by_plugin("demo_plugin")
    assert count == 3
    assert timer_registry.list_actions() == []
    assert clean_registry.get_plugin_timer_actions("demo_plugin") == []


def test_reload_plugin_actions(plugin_timer_action_dir, clean_registry, monkeypatch):
    """reload_plugin_actions 先撤销旧动作再按最新配置重载。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {"timer_actions": [plugin_timer_action_dir]},
    )
    timer_registry = TimerActionRegistry.instance()
    timer_registry.load_plugin_actions()
    assert len(timer_registry.list_actions()) == 3

    # 清空配置后 reload：动作应被撤销
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {"timer_actions": []},
    )
    timer_registry.reload_plugin_actions()
    assert timer_registry.list_actions() == []

    # 恢复配置后 reload：动作重新注册
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {"timer_actions": [plugin_timer_action_dir]},
    )
    timer_registry.reload_plugin_actions()
    assert len(timer_registry.list_actions()) == 3


def test_register_and_execute():
    """直接注册的动作可查询并可执行。"""
    timer_registry = TimerActionRegistry.instance()
    timer_registry.clear()
    executed = {}

    def my_action(name, params):
        executed["name"] = name
        executed["params"] = params
        return "ok"

    timer_registry.register(
        "my_action", my_action, description="desc", plugin="demo_plugin"
    )
    action = timer_registry.get("my_action")
    assert action is not None
    assert action.plugin == "demo_plugin"
    assert action.function("my_action", {"a": 1}) == "ok"
    assert executed == {"name": "my_action", "params": {"a": 1}}

    assert timer_registry.unregister("my_action") is True
    assert timer_registry.get("my_action") is None
    timer_registry.clear()
