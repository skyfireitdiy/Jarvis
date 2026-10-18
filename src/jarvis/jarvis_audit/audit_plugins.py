# -*- coding: utf-8 -*-
"""插件审计扩展注册表（audit 扩展点）。

插件 config.yaml 通过 ``audit`` 字段声明两类审计扩展：
- ``event_types``：插件自定义的审计事件类型（字符串列表），写入审计日志时
  可作为事件类型使用；
- ``sinks``：插件自定义的审计目标实现目录，目录内 .py 文件导出
  ``audit_sink(event_type, data)`` 函数，安装后自动注册到
  ``AuditSinkRegistry``，审计事件写入本地文件后会同时分发到插件 sink
  （如推送到外部 SIEM / 数据库 / 消息队列）。

与 platforms / timer_actions 扩展点一样遵循可逆效应：加载时登记到
PluginRegistry，卸载时精确撤销。
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
class AuditSink:
    """插件注册的审计 sink 定义。"""

    name: str
    description: str
    plugin: Optional[str]
    function: Callable[[str, Dict[str, Any]], Any]


class AuditSinkRegistry:
    """插件审计扩展注册表（进程内全局单例）。

    维护「sink 名 -> AuditSink」映射与插件自定义事件类型集合，提供注册、查询、
    撤销与目录加载接口。审计事件写入本地文件后由 AuditLogger 分发到各 sink，
    分发失败降级（不影响主审计链路）。
    """

    _instance: Optional["AuditSinkRegistry"] = None

    def __init__(self) -> None:
        self._sinks: Dict[str, AuditSink] = {}
        # 插件 sink 来源追踪：sink 名 -> 来源插件名（可逆效应，供卸载撤销）
        self._plugin_sink_sources: Dict[str, str] = {}
        # 插件自定义事件类型：事件类型 -> 来源插件名（可逆效应，供卸载撤销）
        self._plugin_event_types: Dict[str, str] = {}

    @classmethod
    def instance(cls) -> "AuditSinkRegistry":
        """获取全局单例。"""
        if cls._instance is None:
            cls._instance = AuditSinkRegistry()
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
        """注册单个审计 sink。

        参数:
            name: sink 名
            function: sink 执行函数，签名 ``audit_sink(event_type, data)``
            description: sink 描述
            plugin: 来源插件名（可逆效应来源追踪）
        """
        self._sinks[name] = AuditSink(
            name=name,
            description=description,
            plugin=plugin,
            function=function,
        )
        if plugin:
            self._plugin_sink_sources[name] = plugin

    def register_event_type(self, event_type: str, plugin: Optional[str] = None) -> None:
        """登记插件自定义的单个审计事件类型。"""
        if plugin:
            self._plugin_event_types[event_type] = plugin
        else:
            self._plugin_event_types.setdefault(event_type, "")

    def register_event_types(
        self, event_types: List[str], plugin: Optional[str] = None
    ) -> None:
        """登记插件自定义的一批审计事件类型。"""
        for event_type in event_types:
            self.register_event_type(event_type, plugin)

    def unregister(self, name: str) -> bool:
        """撤销单个审计 sink。"""
        if name not in self._sinks:
            return False
        del self._sinks[name]
        self._plugin_sink_sources.pop(name, None)
        return True

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def get(self, name: str) -> Optional[AuditSink]:
        """按 sink 名查询。"""
        return self._sinks.get(name)

    def list_sinks(self) -> List[Dict[str, Any]]:
        """列出全部已注册 sink 的可序列化信息。"""
        return [
            {
                "name": sink.name,
                "description": sink.description,
                "plugin": sink.plugin,
            }
            for sink in sorted(self._sinks.values(), key=lambda s: s.name)
        ]

    def list_event_types(self) -> List[str]:
        """列出全部已登记的自定义审计事件类型。"""
        return sorted(self._plugin_event_types.keys())

    def get_plugin_sinks(self, plugin: str) -> List[str]:
        """返回指定插件注册的 sink 名列表。"""
        return sorted(
            name for name, src in self._plugin_sink_sources.items() if src == plugin
        )

    def get_plugin_event_types(self, plugin: str) -> List[str]:
        """返回指定插件登记的自定义事件类型列表。"""
        return sorted(
            name for name, src in self._plugin_event_types.items() if src == plugin
        )

    # ------------------------------------------------------------------
    # 目录加载（audit 扩展点）
    # ------------------------------------------------------------------
    @staticmethod
    def _infer_source_plugin(directory: str) -> Optional[str]:
        """从 sink 目录路径反推来源插件名（可逆效应来源追踪）。

        当目录路径形如 <...>/plugins/<plugin_name>/... 时返回插件名，
        否则返回 None（表示非插件来源的目录）。
        """
        try:
            normalized = directory.replace("\\", "/")
            marker = "/plugins/"
            if marker in normalized:
                return normalized.split(marker, 1)[1].split("/", 1)[0]
        except Exception:
            pass
        return None

    def load_plugin_sinks(self) -> None:
        """从插件声明的 sink 目录加载审计扩展（audit 扩展点）。

        目录内每个 .py 文件（跳过 __init__.py）按以下约定注册：
        - 模块级函数 ``audit_sink(event_type, data)``：sink 执行函数
        - 模块级 ``AUDIT_SINK_NAME``：sink 名（缺省用文件名）
        - 模块级 ``AUDIT_SINK_DESCRIPTION``：sink 描述（可选）
        - 可选 ``register_audit_sinks()`` 工厂：返回 ``(name, function,
          description)`` 或 ``(name, function)`` 元组列表，用于单文件注册多个 sink

        同时登记插件自定义事件类型（来自 ``get_plugin_audit_event_types``）。
        加载成功后登记到 PluginRegistry（可逆效应），供卸载时精确撤销。
        """
        from jarvis.jarvis_utils.config import get_plugin_audit_sink_dirs
        from jarvis.jarvis_tools.plugin_registry import PluginRegistry
        from jarvis.jarvis_utils.output import PrettyOutput

        registry = PluginRegistry.instance()
        # 登记插件自定义事件类型（来源在 _load_plugin_configs 解析插件 config 时
        # 已按插件名登记到 PluginRegistry，这里按来源聚合到 AuditSinkRegistry，
        # 供卸载时精确撤销）
        for plugin_name in registry.registered_plugins():
            for event_type in registry.get_plugin_audit_event_types(plugin_name):
                self.register_event_type(event_type, plugin=plugin_name)

        for directory in get_plugin_audit_sink_dirs():
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
                            registry.register_audit_sink(source_plugin, name)
                except Exception as e:
                    PrettyOutput.auto_print(
                        f"⚠️ 加载审计 sink {module_name} 失败: {e}"
                    )

    def _register_from_module(
        self,
        module: Any,
        module_name: str,
        source_plugin: Optional[str],
    ) -> List[str]:
        """从单个模块注册审计 sink，返回注册的 sink 名列表。"""
        from jarvis.jarvis_utils.output import PrettyOutput

        registered: List[str] = []
        # 工厂方法：register_audit_sinks() 返回 (name, function[, description]) 列表
        factory = getattr(module, "register_audit_sinks", None)
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
                    f"⚠️ 审计 sink 工厂 {module_name}.register_audit_sinks 失败: {e}"
                )
            return registered

        # 单 sink：audit_sink(event_type, data) 函数 + 模块级常量
        function = getattr(module, "audit_sink", None)
        if not callable(function):
            PrettyOutput.auto_print(
                f"⚠️ 审计 sink 模块 {module_name} 缺少 audit_sink 函数或 "
                f"register_audit_sinks 工厂，已跳过"
            )
            return registered
        name = getattr(module, "AUDIT_SINK_NAME", None) or module_name
        description = getattr(module, "AUDIT_SINK_DESCRIPTION", "") or ""
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
    def unregister_by_plugin(self, plugin: str) -> int:
        """撤销指定插件注册的全部审计扩展（可逆效应）。

        返回被撤销的 sink 数量。
        """
        from jarvis.jarvis_tools.plugin_registry import PluginRegistry

        registry = PluginRegistry.instance()
        names = self.get_plugin_sinks(plugin)
        count = 0
        for name in names:
            if self.unregister(name):
                count += 1
        # 撤销插件登记的自定义事件类型（AuditSinkRegistry 内部状态）
        for event_type in self.get_plugin_event_types(plugin):
            self._plugin_event_types.pop(event_type, None)
        # 清理 PluginRegistry 的 sink 登记（与 timer_actions 对称）。事件类型
        # 来源登记由 _load_plugin_configs 管理（reload_plugin_configs 时重建），
        # 这里不清：真实卸载由 revoke_plugin 的 unregister_plugin 兜底清理，
        # reload 时则需保留来源供加载阶段按插件名重新聚合。
        registry.clear_audit_sinks(plugin)
        return count

    def reload_plugin_sinks(self) -> None:
        """插件变更后免重启重载插件审计扩展（audit 扩展点）。

        先撤销当前已注册的全部插件审计扩展，再按最新配置重新加载，使插件安装/
        卸载/升级后的审计声明立即生效。失败仅告警，不阻断调用方。
        """
        from jarvis.jarvis_tools.plugin_registry import PluginRegistry
        from jarvis.jarvis_utils.output import PrettyOutput

        registry = PluginRegistry.instance()
        # 撤销当前已注册的全部插件审计扩展（按来源插件名逐个撤销）
        for plugin_name in list(registry.registered_plugins()):
            if registry.get_plugin_audit_sinks(plugin_name) or registry.get_plugin_audit_event_types(plugin_name):
                try:
                    self.unregister_by_plugin(plugin_name)
                except Exception as e:
                    PrettyOutput.auto_print(
                        f"⚠️ 撤销插件 '{plugin_name}' 审计扩展失败: {e}"
                    )
        # 重新加载插件审计扩展
        try:
            self.load_plugin_sinks()
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 重载插件审计扩展失败: {e}")

    def clear(self) -> None:
        """清空全部登记（主要用于测试隔离）。"""
        self._sinks.clear()
        self._plugin_sink_sources.clear()
        self._plugin_event_types.clear()


__all__ = ["AuditSinkRegistry", "AuditSink"]
