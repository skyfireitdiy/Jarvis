"""插件管理器

提供插件的发现、加载、卸载和生命周期管理功能。
"""

import importlib
import importlib.util
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from jarvis.jarvis_plugin.plugin_base import PluginBase, PluginMeta


class PluginState(Enum):
    """插件状态枚举"""

    DISCOVERED = "discovered"
    LOADED = "loaded"
    INITIALIZED = "initialized"
    STARTED = "started"
    STOPPED = "stopped"
    UNLOADED = "unloaded"
    ERROR = "error"


class PluginError(Exception):
    """插件错误基类"""

    pass


class PluginLoadError(PluginError):
    """插件加载错误"""

    pass


class PluginUnloadError(PluginError):
    """插件卸载错误"""

    pass


@dataclass
class PluginInfo:
    """插件信息"""

    meta: PluginMeta
    state: PluginState = PluginState.DISCOVERED
    instance: PluginBase | None = None
    module_path: str = ""
    error_message: str = ""
    load_order: int = 0


class PluginManager:
    """插件管理器"""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginInfo] = {}
        self._plugin_dirs: list[Path] = []
        self._load_counter = 0

    @property
    def plugins(self) -> dict[str, PluginInfo]:
        return self._plugins.copy()

    def get_plugin(self, name: str) -> PluginInfo | None:
        return self._plugins.get(name)

    def get_plugin_instance(self, name: str) -> PluginBase | None:
        info = self._plugins.get(name)
        return info.instance if info else None

    def discover_plugins(self, plugin_dir: str | Path) -> list[str]:
        plugin_path = Path(plugin_dir)
        if not plugin_path.exists():
            return []

        if plugin_path not in self._plugin_dirs:
            self._plugin_dirs.append(plugin_path)

        discovered = []
        for py_file in plugin_path.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                plugin_names = self._discover_from_file(py_file)
                discovered.extend(plugin_names)
            except Exception:
                continue

        return discovered

    def _discover_from_file(self, file_path: Path) -> list[str]:
        discovered = []
        module_name = f"_plugin_discovery_{file_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return []

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception:
            return []

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, PluginBase)
                and attr is not PluginBase
            ):
                try:
                    meta = attr.get_meta()
                    if meta.name not in self._plugins:
                        self._plugins[meta.name] = PluginInfo(
                            meta=meta,
                            state=PluginState.DISCOVERED,
                            module_path=str(file_path),
                        )
                        discovered.append(meta.name)
                except Exception:
                    continue

        return discovered

    def load_plugin(
        self, name: str, config: dict[str, Any] | None = None
    ) -> PluginInfo:
        info = self._plugins.get(name)
        if info is None:
            raise PluginLoadError(f"Plugin '{name}' not found")

        if info.state in (
            PluginState.LOADED,
            PluginState.INITIALIZED,
            PluginState.STARTED,
        ):
            return info

        self._check_dependencies(info.meta)

        try:
            module_path = Path(info.module_path)
            module_name = f"_plugin_{module_path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                raise PluginLoadError(f"Cannot load module from {module_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, PluginBase)
                    and attr is not PluginBase
                ):
                    meta = attr.get_meta()
                    if meta.name == name:
                        plugin_class = attr
                        break

            if plugin_class is None:
                raise PluginLoadError(f"Plugin class for '{name}' not found")

            instance = plugin_class(config)
            self._load_counter += 1

            info.instance = instance
            info.state = PluginState.LOADED
            info.load_order = self._load_counter
            info.error_message = ""

            return info

        except PluginLoadError:
            raise
        except Exception as e:
            info.state = PluginState.ERROR
            info.error_message = str(e)
            raise PluginLoadError(f"Failed to load plugin '{name}': {e}") from e

    def _check_dependencies(self, meta: PluginMeta) -> None:
        for dep_name in meta.dependencies:
            dep_info = self._plugins.get(dep_name)
            if dep_info is None:
                raise PluginLoadError(
                    f"Dependency '{dep_name}' not found for plugin '{meta.name}'"
                )
            if dep_info.state not in (
                PluginState.LOADED,
                PluginState.INITIALIZED,
                PluginState.STARTED,
            ):
                raise PluginLoadError(
                    f"Dependency '{dep_name}' not loaded for plugin '{meta.name}'"
                )

    def unload_plugin(self, name: str) -> None:
        info = self._plugins.get(name)
        if info is None:
            raise PluginUnloadError(f"Plugin '{name}' not found")

        if info.state == PluginState.UNLOADED:
            return

        for other_name, other_info in self._plugins.items():
            if other_name == name:
                continue
            if name in other_info.meta.dependencies and other_info.state in (
                PluginState.LOADED,
                PluginState.INITIALIZED,
                PluginState.STARTED,
            ):
                raise PluginUnloadError(
                    f"Cannot unload '{name}': plugin '{other_name}' depends on it"
                )

        try:
            if info.state == PluginState.STARTED and info.instance:
                info.instance.stop()

            if info.instance:
                info.instance.cleanup()

            info.instance = None
            info.state = PluginState.UNLOADED
            info.error_message = ""

        except Exception as e:
            info.state = PluginState.ERROR
            info.error_message = str(e)
            raise PluginUnloadError(f"Failed to unload plugin '{name}': {e}") from e

    def initialize_plugin(self, name: str) -> None:
        info = self._plugins.get(name)
        if info is None:
            raise PluginError(f"Plugin '{name}' not found")

        if info.state == PluginState.INITIALIZED:
            return

        if info.state != PluginState.LOADED:
            raise PluginError(f"Plugin '{name}' must be loaded before initialization")

        if info.instance is None:
            raise PluginError(f"Plugin '{name}' has no instance")

        try:
            info.instance.initialize()
            info.state = PluginState.INITIALIZED
        except Exception as e:
            info.state = PluginState.ERROR
            info.error_message = str(e)
            raise PluginError(f"Failed to initialize plugin '{name}': {e}") from e

    def start_plugin(self, name: str) -> None:
        info = self._plugins.get(name)
        if info is None:
            raise PluginError(f"Plugin '{name}' not found")

        if info.state == PluginState.STARTED:
            return

        if info.state != PluginState.INITIALIZED:
            raise PluginError(f"Plugin '{name}' must be initialized before starting")

        if info.instance is None:
            raise PluginError(f"Plugin '{name}' has no instance")

        try:
            info.instance.start()
            info.state = PluginState.STARTED
        except Exception as e:
            info.state = PluginState.ERROR
            info.error_message = str(e)
            raise PluginError(f"Failed to start plugin '{name}': {e}") from e

    def stop_plugin(self, name: str) -> None:
        info = self._plugins.get(name)
        if info is None:
            raise PluginError(f"Plugin '{name}' not found")

        if info.state == PluginState.STOPPED:
            return

        if info.state != PluginState.STARTED:
            return

        if info.instance is None:
            raise PluginError(f"Plugin '{name}' has no instance")

        try:
            info.instance.stop()
            info.state = PluginState.STOPPED
        except Exception as e:
            info.state = PluginState.ERROR
            info.error_message = str(e)
            raise PluginError(f"Failed to stop plugin '{name}': {e}") from e

    def load_all(self, config: dict[str, dict[str, Any]] | None = None) -> list[str]:
        config = config or {}
        loaded = []

        sorted_plugins = sorted(
            self._plugins.values(),
            key=lambda p: p.meta.priority,
        )

        for info in sorted_plugins:
            if info.state != PluginState.DISCOVERED:
                continue
            try:
                self.load_plugin(info.meta.name, config.get(info.meta.name))
                loaded.append(info.meta.name)
            except PluginLoadError:
                continue

        return loaded

    def start_all(self) -> list[str]:
        started = []

        sorted_plugins = sorted(
            [p for p in self._plugins.values() if p.instance is not None],
            key=lambda p: p.load_order,
        )

        for info in sorted_plugins:
            try:
                if info.state == PluginState.LOADED:
                    self.initialize_plugin(info.meta.name)
                if info.state == PluginState.INITIALIZED:
                    self.start_plugin(info.meta.name)
                    started.append(info.meta.name)
            except PluginError:
                continue

        return started

    def stop_all(self) -> list[str]:
        stopped = []

        sorted_plugins = sorted(
            [p for p in self._plugins.values() if p.state == PluginState.STARTED],
            key=lambda p: p.load_order,
            reverse=True,
        )

        for info in sorted_plugins:
            try:
                self.stop_plugin(info.meta.name)
                stopped.append(info.meta.name)
            except PluginError:
                continue

        return stopped

    def unload_all(self) -> list[str]:
        unloaded = []
        self.stop_all()

        sorted_plugins = sorted(
            [p for p in self._plugins.values() if p.instance is not None],
            key=lambda p: p.load_order,
            reverse=True,
        )

        for info in sorted_plugins:
            try:
                self.unload_plugin(info.meta.name)
                unloaded.append(info.meta.name)
            except PluginUnloadError:
                continue

        return unloaded

    def get_status(self) -> dict[str, Any]:
        return {
            "total_plugins": len(self._plugins),
            "plugin_dirs": [str(p) for p in self._plugin_dirs],
            "plugins": {
                name: {
                    "state": info.state.value,
                    "version": info.meta.version,
                    "dependencies": info.meta.dependencies,
                    "error": info.error_message,
                }
                for name, info in self._plugins.items()
            },
        }

    def reload_plugin(
        self, name: str, config: dict[str, Any] | None = None
    ) -> PluginInfo:
        info = self._plugins.get(name)
        if info is None:
            raise PluginError(f"Plugin '{name}' not found")

        was_started = info.state == PluginState.STARTED

        if info.state in (
            PluginState.LOADED,
            PluginState.INITIALIZED,
            PluginState.STARTED,
        ):
            self.unload_plugin(name)

        info.state = PluginState.DISCOVERED
        self.load_plugin(name, config)

        if was_started:
            self.initialize_plugin(name)
            self.start_plugin(name)

        return self._plugins[name]
