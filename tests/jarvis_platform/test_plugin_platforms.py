# -*- coding: utf-8 -*-
"""插件 platforms 扩展点单元测试（Issue #294）。

验证插件声明的平台目录能被 PlatformRegistry 加载、注册，并在卸载时精确撤销。
"""

import os
import shutil
import tempfile

import pytest

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.plugin_registry import PluginRegistry

PLATFORM_CODE = '''
from jarvis.jarvis_platform.base import BasePlatform

class DemoPlatform(BasePlatform):
    def chat(self, message: str):
        return "demo reply"

    def name(self) -> str:
        return "Demo"

    def delete_chat(self) -> bool:
        return True

    def set_system_prompt(self, message: str):
        pass

    def set_model_name(self, model_name: str):
        pass

    def get_model_list(self):
        return [("demo-model", "Demo Model")]

    def upload_files(self, file_list):
        return True

    @classmethod
    def platform_name(cls) -> str:
        return "demo_platform"
'''


@pytest.fixture()
def plugin_platform_dir():
    """创建临时插件平台目录（形如 <tmp>/plugins/<name>/platforms）。"""
    tmp = tempfile.mkdtemp()
    platforms_dir = os.path.join(tmp, "plugins", "demo_plugin", "platforms")
    os.makedirs(platforms_dir, exist_ok=True)
    open(os.path.join(platforms_dir, "__init__.py"), "w").close()
    with open(os.path.join(platforms_dir, "demo_platform.py"), "w") as f:
        f.write(PLATFORM_CODE)
    yield platforms_dir
    shutil.rmtree(tmp)


@pytest.fixture()
def clean_registry():
    """隔离测试：清空 PluginRegistry 登记，测试后恢复。"""
    registry = PluginRegistry.instance()
    registry.clear()
    yield registry
    registry.clear()


def test_infer_source_plugin(plugin_platform_dir):
    """从插件平台目录路径反推来源插件名。"""
    source = PlatformRegistry._infer_source_plugin(plugin_platform_dir)
    assert source == "demo_plugin"


def test_infer_source_plugin_non_plugin_dir():
    """非插件目录路径返回 None。"""
    assert PlatformRegistry._infer_source_plugin("/tmp/foo/bar") is None
    assert PlatformRegistry._infer_source_plugin("") is None


def test_load_plugin_platforms(plugin_platform_dir, clean_registry, monkeypatch):
    """插件平台目录加载并注册到 PlatformRegistry。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {"platforms": [plugin_platform_dir]},
    )
    registry = PlatformRegistry()
    registry._load_plugin_platforms()

    assert "demo_platform" in registry.get_available_platforms()
    assert registry._plugin_platform_sources.get("demo_platform") == "demo_plugin"
    assert clean_registry.get_plugin_platforms("demo_plugin") == ["demo_platform"]


def test_unregister_platforms_by_plugin(plugin_platform_dir, clean_registry, monkeypatch):
    """卸载时精确撤销插件注册的平台。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {"platforms": [plugin_platform_dir]},
    )
    registry = PlatformRegistry()
    registry._load_plugin_platforms()
    assert "demo_platform" in registry.get_available_platforms()

    count = registry.unregister_platforms_by_plugin("demo_plugin")
    assert count == 1
    assert "demo_platform" not in registry.get_available_platforms()
    assert clean_registry.get_plugin_platforms("demo_plugin") == []


def test_reload_plugin_platforms(plugin_platform_dir, clean_registry, monkeypatch):
    """reload_plugin_platforms 先撤销旧平台再按最新配置重载。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {"platforms": [plugin_platform_dir]},
    )
    registry = PlatformRegistry()
    registry._load_plugin_platforms()
    assert "demo_platform" in registry.get_available_platforms()

    # 清空配置后 reload：平台应被撤销
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {"platforms": []},
    )
    registry.reload_plugin_platforms()
    assert "demo_platform" not in registry.get_available_platforms()

    # 恢复配置后 reload：平台重新注册
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {"platforms": [plugin_platform_dir]},
    )
    registry.reload_plugin_platforms()
    assert "demo_platform" in registry.get_available_platforms()
