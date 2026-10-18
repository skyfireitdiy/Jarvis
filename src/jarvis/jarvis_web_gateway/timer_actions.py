# -*- coding: utf-8 -*-
"""插件定时任务动作注册表（timer_actions 扩展点）。

插件 config.yaml 通过 ``timer_actions`` 字段声明自带的定时动作实现目录，
目录内 .py 文件导出 ``timer_action(name, params)`` 函数，安装后自动注册到
``TimerActionRegistry``，定时任务创建时 ``timer_action_type`` 即可选用插件
注册的动作类型，到点后由插件实现执行逻辑。

与 platforms 扩展点一样遵循可逆效应：加载时登记到 PluginRegistry，卸载时
精确撤销。
"""

from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional


@dataclass
class TimerAction:
    """插件注册的定时任务动作定义。"""

    name: str
    description: str
    plugin: Optional[str]
    function: Callable[[str, Dict[str, Any]], Any]


class TimerActionRegistry:
    """插件定时任务动作注册表（进程内全局单例）。

    维护「动作名 -> TimerAction」映射，提供注册、查询、撤销与目录加载接口。
    动作执行上下文在 gateway 进程内，由 TimerManager 到点触发。
    """

    _instance: Optional["TimerActionRegistry"] = None

    def __init__(self) -> None:
        self._actions: Dict[str, TimerAction] = {}
        # 插件动作来源追踪：动作名 -> 来源插件名（可逆效应，供卸载撤销）
        self._plugin_action_sources: Dict[str, str] = {}

    @classmethod
    def instance(cls) -> "TimerActionRegistry":
        """获取全局单例。"""
        if cls._instance is None:
            cls._instance = TimerActionRegistry()
        return cls._instance

    # ------------------------------------------------------------------
    # 注册 / 撤销
    # ------------------------------------------------------------------
    def register(
        self,
        name: str,
        function: Callable[[str, Dict[str, Any]], Any],
        description: str = "",
        plugin: Optional[str] = None,
    ) -> None:
        """注册单个定时动作。

        参数:
            name: 动作名（定时任务 timer_action_type 使用）
            function: 动作执行函数，签名 ``timer_action(name, params)``
            description: 动作描述
            plugin: 来源插件名（可逆效应来源追踪）
        """
        self._actions[name] = TimerAction(
            name=name,
            description=description,
            plugin=plugin,
            function=function,
        )
        if plugin:
            self._plugin_action_sources[name] = plugin

    def unregister(self, name: str) -> bool:
        """撤销单个定时动作。"""
        if name not in self._actions:
            return False
        del self._actions[name]
        self._plugin_action_sources.pop(name, None)
        return True

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def get(self, name: str) -> Optional[TimerAction]:
        """按动作名查询。"""
        return self._actions.get(name)

    def list_actions(self) -> List[Dict[str, Any]]:
        """列出全部已注册动作的可序列化信息。"""
        return [
            {
                "name": action.name,
                "description": action.description,
                "plugin": action.plugin,
            }
            for action in sorted(self._actions.values(), key=lambda a: a.name)
        ]

    def get_plugin_actions(self, plugin: str) -> List[str]:
        """返回指定插件注册的动作名列表。"""
        return sorted(
            name for name, src in self._plugin_action_sources.items() if src == plugin
        )

    # ------------------------------------------------------------------
    # 目录加载（timer_actions 扩展点）
    # ------------------------------------------------------------------
    @staticmethod
    def _infer_source_plugin(directory: str) -> Optional[str]:
        """从动作目录路径反推来源插件名（可逆效应来源追踪）。

        当目录路径形如 <...>/plugins/<plugin_name>/timer_actions 时返回插件名，
        否则返回 None（表示非插件来源的动作目录）。
        """
        try:
            normalized = directory.replace("\\", "/")
            marker = "/plugins/"
            if marker in normalized:
                return normalized.split(marker, 1)[1].split("/", 1)[0]
        except Exception:
            pass
        return None

    def load_plugin_actions(self) -> None:
        """从插件声明的动作目录加载定时动作（timer_actions 扩展点）。

        目录内每个 .py 文件（跳过 __init__.py）按以下约定注册：
        - 模块级函数 ``timer_action(name, params)``：动作执行函数
        - 模块级 ``TIMER_ACTION_NAME``：动作名（缺省用文件名）
        - 模块级 ``TIMER_ACTION_DESCRIPTION``：动作描述（可选）
        - 可选 ``register_timer_actions()`` 工厂：返回 ``(name, function,
          description)`` 或 ``(name, function)`` 元组列表，用于单文件注册多个动作

        加载成功后登记到 PluginRegistry（可逆效应），供卸载时精确撤销。
        """
        from jarvis.jarvis_utils.config import get_plugin_timer_action_dirs
        from jarvis.jarvis_tools.plugin_registry import PluginRegistry
        from jarvis.jarvis_utils.output import PrettyOutput

        registry = PluginRegistry.instance()
        for directory in get_plugin_timer_action_dirs():
            if not directory or not os.path.exists(directory) or not os.path.isdir(directory):
                continue
            source_plugin = self._infer_source_plugin(directory)
            if directory not in sys.path:
                sys.path.insert(0, directory)
            for filename in sorted(os.listdir(directory)):
                if not filename.endswith(".py") or filename.startswith("__"):
                    continue
                module_name = filename[:-3]
                try:
                    module = importlib.import_module(module_name)
                    registered = self._register_from_module(
                        module, module_name, source_plugin
                    )
                    for name in registered:
                        if source_plugin:
                            registry.register_timer_action(source_plugin, name)
                except Exception as e:
                    PrettyOutput.auto_print(
                        f"⚠️ 加载定时动作 {module_name} 失败: {e}"
                    )

    def _register_from_module(
        self,
        module: Any,
        module_name: str,
        source_plugin: Optional[str],
    ) -> List[str]:
        """从单个模块注册定时动作，返回注册的动作名列表。"""
        from jarvis.jarvis_utils.output import PrettyOutput

        registered: List[str] = []
        # 工厂方法：register_timer_actions() 返回 (name, function[, description]) 列表
        factory = getattr(module, "register_timer_actions", None)
        if callable(factory):
            try:
                for entry in factory() or []:
                    name, function, description = self._normalize_factory_entry(entry)
                    if name and callable(function):
                        self.register(
                            name,
                            function,
                            description=description,
                            plugin=source_plugin,
                        )
                        registered.append(name)
            except Exception as e:
                PrettyOutput.auto_print(
                    f"⚠️ 定时动作工厂 {module_name}.register_timer_actions 失败: {e}"
                )
            return registered

        # 单动作：timer_action(name, params) 函数 + 模块级常量
        function = getattr(module, "timer_action", None)
        if not callable(function):
            PrettyOutput.auto_print(
                f"⚠️ 定时动作模块 {module_name} 缺少 timer_action 函数或 register_timer_actions 工厂，已跳过"
            )
            return registered
        name = getattr(module, "TIMER_ACTION_NAME", None) or module_name
        description = getattr(module, "TIMER_ACTION_DESCRIPTION", "") or ""
        self.register(name, function, description=description, plugin=source_plugin)
        registered.append(name)
        return registered

    @staticmethod
    def _normalize_factory_entry(entry: Any):
        """规范化工厂返回的单个条目 (name, function[, description])。"""
        if not isinstance(entry, (tuple, list)) or len(entry) < 2:
            return None, None, ""
        name = entry[0]
        function = entry[1]
        description = entry[2] if len(entry) > 2 else ""
        return name, function, description

    # ------------------------------------------------------------------
    # 插件变更重载
    # ------------------------------------------------------------------
    def unregister_actions_by_plugin(self, plugin: str) -> int:
        """撤销指定插件注册的全部定时动作（可逆效应）。

        返回被撤销的动作数量。
        """
        from jarvis.jarvis_tools.plugin_registry import PluginRegistry

        registry = PluginRegistry.instance()
        names = self.get_plugin_actions(plugin)
        count = 0
        for name in names:
            if self.unregister(name):
                count += 1
        registry.clear_timer_actions(plugin)
        return count

    def reload_plugin_actions(self) -> None:
        """插件变更后免重启重载插件定时动作（timer_actions 扩展点）。

        先撤销当前已注册的全部插件动作，再按最新配置重新加载，使插件安装/
        卸载/升级后的动作声明立即生效。失败仅告警，不阻断调用方。
        """
        from jarvis.jarvis_tools.plugin_registry import PluginRegistry
        from jarvis.jarvis_utils.output import PrettyOutput

        registry = PluginRegistry.instance()
        # 撤销当前已注册的全部插件动作（按来源插件名逐个撤销）
        for plugin_name in list(registry.registered_plugins()):
            if registry.get_plugin_timer_actions(plugin_name):
                try:
                    self.unregister_actions_by_plugin(plugin_name)
                except Exception as e:
                    PrettyOutput.auto_print(
                        f"⚠️ 撤销插件 '{plugin_name}' 定时动作失败: {e}"
                    )
        # 重新加载插件动作
        try:
            self.load_plugin_actions()
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 重载插件定时动作失败: {e}")

    def clear(self) -> None:
        """清空全部登记（主要用于测试隔离）。"""
        self._actions.clear()
        self._plugin_action_sources.clear()


__all__ = ["TimerActionRegistry", "TimerAction"]
