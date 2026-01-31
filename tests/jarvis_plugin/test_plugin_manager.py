"""插件管理器测试"""

import tempfile
from pathlib import Path

import pytest

from jarvis.jarvis_plugin import (
    PluginBase,
    PluginError,
    PluginLoadError,
    PluginManager,
    PluginMeta,
    PluginState,
    PluginUnloadError,
)


# 测试用插件
class SamplePlugin(PluginBase):
    """示例插件"""

    @classmethod
    def get_meta(cls) -> PluginMeta:
        return PluginMeta(
            name="sample_plugin",
            version="1.0.0",
            description="A sample plugin for testing",
        )

    def initialize(self) -> None:
        super().initialize()
        self.data = "initialized"

    def start(self) -> None:
        super().start()
        self.data = "started"

    def stop(self) -> None:
        super().stop()
        self.data = "stopped"


class TestPluginMeta:
    """PluginMeta测试"""

    def test_default_values(self) -> None:
        meta = PluginMeta(name="test")
        assert meta.name == "test"
        assert meta.version == "1.0.0"
        assert meta.description == ""
        assert meta.dependencies == []
        assert meta.priority == 100

    def test_custom_values(self) -> None:
        meta = PluginMeta(
            name="custom",
            version="2.0.0",
            description="Custom plugin",
            dependencies=["dep1", "dep2"],
            priority=50,
        )
        assert meta.name == "custom"
        assert meta.version == "2.0.0"
        assert meta.dependencies == ["dep1", "dep2"]
        assert meta.priority == 50


class TestPluginBase:
    """PluginBase测试"""

    def test_init_default_config(self) -> None:
        plugin = SamplePlugin()
        assert plugin.config == {}
        assert not plugin.is_initialized
        assert not plugin.is_started

    def test_init_with_config(self) -> None:
        config = {"key": "value"}
        plugin = SamplePlugin(config)
        assert plugin.config == config

    def test_lifecycle(self) -> None:
        plugin = SamplePlugin()
        assert not plugin.is_initialized
        assert not plugin.is_started

        plugin.initialize()
        assert plugin.is_initialized
        assert not plugin.is_started
        assert plugin.data == "initialized"

        plugin.start()
        assert plugin.is_started
        assert plugin.data == "started"

        plugin.stop()
        assert not plugin.is_started
        assert plugin.data == "stopped"

        plugin.cleanup()
        assert not plugin.is_initialized

    def test_start_without_init_raises(self) -> None:
        plugin = SamplePlugin()
        with pytest.raises(RuntimeError, match="must be initialized"):
            plugin.start()

    def test_get_status(self) -> None:
        plugin = SamplePlugin()
        status = plugin.get_status()
        assert status["name"] == "sample_plugin"
        assert status["version"] == "1.0.0"
        assert status["initialized"] is False
        assert status["started"] is False


class TestPluginManager:
    """PluginManager测试"""

    def test_init(self) -> None:
        manager = PluginManager()
        assert manager.plugins == {}

    def test_get_plugin_not_found(self) -> None:
        manager = PluginManager()
        assert manager.get_plugin("nonexistent") is None

    def test_get_plugin_instance_not_found(self) -> None:
        manager = PluginManager()
        assert manager.get_plugin_instance("nonexistent") is None

    def test_discover_nonexistent_dir(self) -> None:
        manager = PluginManager()
        result = manager.discover_plugins("/nonexistent/path")
        assert result == []

    def test_discover_plugins(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "my_plugin.py"
            plugin_file.write_text(
                """
from jarvis.jarvis_plugin import PluginBase, PluginMeta

class MyPlugin(PluginBase):
    @classmethod
    def get_meta(cls) -> PluginMeta:
        return PluginMeta(name="my_plugin", version="1.0.0")
"""
            )

            manager = PluginManager()
            discovered = manager.discover_plugins(tmpdir)
            assert "my_plugin" in discovered
            assert "my_plugin" in manager.plugins

    def test_discover_skips_private_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            private_file = Path(tmpdir) / "_private.py"
            private_file.write_text("# private file")

            manager = PluginManager()
            discovered = manager.discover_plugins(tmpdir)
            assert discovered == []

    def test_load_plugin_not_found(self) -> None:
        manager = PluginManager()
        with pytest.raises(PluginLoadError, match="not found"):
            manager.load_plugin("nonexistent")

    def test_load_and_unload_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "loadable.py"
            plugin_file.write_text(
                """
from jarvis.jarvis_plugin import PluginBase, PluginMeta

class LoadablePlugin(PluginBase):
    @classmethod
    def get_meta(cls) -> PluginMeta:
        return PluginMeta(name="loadable", version="1.0.0")
"""
            )

            manager = PluginManager()
            manager.discover_plugins(tmpdir)
            info = manager.load_plugin("loadable")

            assert info.state == PluginState.LOADED
            assert info.instance is not None

            manager.unload_plugin("loadable")
            assert manager.get_plugin("loadable").state == PluginState.UNLOADED

    def test_unload_plugin_not_found(self) -> None:
        manager = PluginManager()
        with pytest.raises(PluginUnloadError, match="not found"):
            manager.unload_plugin("nonexistent")

    def test_initialize_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "init_test.py"
            plugin_file.write_text(
                """
from jarvis.jarvis_plugin import PluginBase, PluginMeta

class InitTestPlugin(PluginBase):
    @classmethod
    def get_meta(cls) -> PluginMeta:
        return PluginMeta(name="init_test", version="1.0.0")
"""
            )

            manager = PluginManager()
            manager.discover_plugins(tmpdir)
            manager.load_plugin("init_test")
            manager.initialize_plugin("init_test")

            info = manager.get_plugin("init_test")
            assert info.state == PluginState.INITIALIZED

    def test_initialize_plugin_not_found(self) -> None:
        manager = PluginManager()
        with pytest.raises(PluginError, match="not found"):
            manager.initialize_plugin("nonexistent")

    def test_start_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "start_test.py"
            plugin_file.write_text(
                """
from jarvis.jarvis_plugin import PluginBase, PluginMeta

class StartTestPlugin(PluginBase):
    @classmethod
    def get_meta(cls) -> PluginMeta:
        return PluginMeta(name="start_test", version="1.0.0")
"""
            )

            manager = PluginManager()
            manager.discover_plugins(tmpdir)
            manager.load_plugin("start_test")
            manager.initialize_plugin("start_test")
            manager.start_plugin("start_test")

            info = manager.get_plugin("start_test")
            assert info.state == PluginState.STARTED

    def test_start_plugin_not_found(self) -> None:
        manager = PluginManager()
        with pytest.raises(PluginError, match="not found"):
            manager.start_plugin("nonexistent")

    def test_stop_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "stop_test.py"
            plugin_file.write_text(
                """
from jarvis.jarvis_plugin import PluginBase, PluginMeta

class StopTestPlugin(PluginBase):
    @classmethod
    def get_meta(cls) -> PluginMeta:
        return PluginMeta(name="stop_test", version="1.0.0")
"""
            )

            manager = PluginManager()
            manager.discover_plugins(tmpdir)
            manager.load_plugin("stop_test")
            manager.initialize_plugin("stop_test")
            manager.start_plugin("stop_test")
            manager.stop_plugin("stop_test")

            info = manager.get_plugin("stop_test")
            assert info.state == PluginState.STOPPED

    def test_stop_plugin_not_found(self) -> None:
        manager = PluginManager()
        with pytest.raises(PluginError, match="not found"):
            manager.stop_plugin("nonexistent")

    def test_load_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                plugin_file = Path(tmpdir) / f"plugin_{i}.py"
                plugin_file.write_text(
                    f"""
from jarvis.jarvis_plugin import PluginBase, PluginMeta

class Plugin{i}(PluginBase):
    @classmethod
    def get_meta(cls) -> PluginMeta:
        return PluginMeta(name="plugin_{i}", version="1.0.0", priority={i})
"""
                )

            manager = PluginManager()
            manager.discover_plugins(tmpdir)
            loaded = manager.load_all()

            assert len(loaded) == 3

    def test_start_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "start_all_test.py"
            plugin_file.write_text(
                """
from jarvis.jarvis_plugin import PluginBase, PluginMeta

class StartAllPlugin(PluginBase):
    @classmethod
    def get_meta(cls) -> PluginMeta:
        return PluginMeta(name="start_all_test", version="1.0.0")
"""
            )

            manager = PluginManager()
            manager.discover_plugins(tmpdir)
            manager.load_all()
            started = manager.start_all()

            assert "start_all_test" in started

    def test_stop_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "stop_all_test.py"
            plugin_file.write_text(
                """
from jarvis.jarvis_plugin import PluginBase, PluginMeta

class StopAllPlugin(PluginBase):
    @classmethod
    def get_meta(cls) -> PluginMeta:
        return PluginMeta(name="stop_all_test", version="1.0.0")
"""
            )

            manager = PluginManager()
            manager.discover_plugins(tmpdir)
            manager.load_all()
            manager.start_all()
            stopped = manager.stop_all()

            assert "stop_all_test" in stopped

    def test_unload_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "unload_all_test.py"
            plugin_file.write_text(
                """
from jarvis.jarvis_plugin import PluginBase, PluginMeta

class UnloadAllPlugin(PluginBase):
    @classmethod
    def get_meta(cls) -> PluginMeta:
        return PluginMeta(name="unload_all_test", version="1.0.0")
"""
            )

            manager = PluginManager()
            manager.discover_plugins(tmpdir)
            manager.load_all()
            unloaded = manager.unload_all()

            assert "unload_all_test" in unloaded

    def test_get_status(self) -> None:
        manager = PluginManager()
        status = manager.get_status()
        assert status["total_plugins"] == 0
        assert status["plugin_dirs"] == []
        assert status["plugins"] == {}

    def test_reload_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "reload_test.py"
            plugin_file.write_text(
                """
from jarvis.jarvis_plugin import PluginBase, PluginMeta

class ReloadPlugin(PluginBase):
    @classmethod
    def get_meta(cls) -> PluginMeta:
        return PluginMeta(name="reload_test", version="1.0.0")
"""
            )

            manager = PluginManager()
            manager.discover_plugins(tmpdir)
            manager.load_plugin("reload_test")
            manager.initialize_plugin("reload_test")
            manager.start_plugin("reload_test")

            info = manager.reload_plugin("reload_test")
            assert info.state == PluginState.STARTED

    def test_reload_plugin_not_found(self) -> None:
        manager = PluginManager()
        with pytest.raises(PluginError, match="not found"):
            manager.reload_plugin("nonexistent")

    def test_dependency_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dep_file = Path(tmpdir) / "dependency.py"
            dep_file.write_text(
                """
from jarvis.jarvis_plugin import PluginBase, PluginMeta

class DependencyPlugin(PluginBase):
    @classmethod
    def get_meta(cls) -> PluginMeta:
        return PluginMeta(name="dependency", version="1.0.0")
"""
            )

            dependent_file = Path(tmpdir) / "dependent.py"
            dependent_file.write_text(
                """
from jarvis.jarvis_plugin import PluginBase, PluginMeta

class DependentPlugin(PluginBase):
    @classmethod
    def get_meta(cls) -> PluginMeta:
        return PluginMeta(
            name="dependent",
            version="1.0.0",
            dependencies=["dependency"]
        )
"""
            )

            manager = PluginManager()
            manager.discover_plugins(tmpdir)

            # 先加载依赖
            manager.load_plugin("dependency")
            # 再加载依赖者
            manager.load_plugin("dependent")

            assert manager.get_plugin("dependent").state == PluginState.LOADED

    def test_dependency_not_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dependent_file = Path(tmpdir) / "dependent_only.py"
            dependent_file.write_text(
                """
from jarvis.jarvis_plugin import PluginBase, PluginMeta

class DependentOnlyPlugin(PluginBase):
    @classmethod
    def get_meta(cls) -> PluginMeta:
        return PluginMeta(
            name="dependent_only",
            version="1.0.0",
            dependencies=["missing_dep"]
        )
"""
            )

            manager = PluginManager()
            manager.discover_plugins(tmpdir)

            with pytest.raises(PluginLoadError, match="not found"):
                manager.load_plugin("dependent_only")

    def test_unload_with_dependents(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dep_file = Path(tmpdir) / "base_dep.py"
            dep_file.write_text(
                """
from jarvis.jarvis_plugin import PluginBase, PluginMeta

class BaseDepPlugin(PluginBase):
    @classmethod
    def get_meta(cls) -> PluginMeta:
        return PluginMeta(name="base_dep", version="1.0.0")
"""
            )

            dependent_file = Path(tmpdir) / "uses_base.py"
            dependent_file.write_text(
                """
from jarvis.jarvis_plugin import PluginBase, PluginMeta

class UsesBasePlugin(PluginBase):
    @classmethod
    def get_meta(cls) -> PluginMeta:
        return PluginMeta(
            name="uses_base",
            version="1.0.0",
            dependencies=["base_dep"]
        )
"""
            )

            manager = PluginManager()
            manager.discover_plugins(tmpdir)
            manager.load_plugin("base_dep")
            manager.load_plugin("uses_base")

            with pytest.raises(PluginUnloadError, match="depends on it"):
                manager.unload_plugin("base_dep")
