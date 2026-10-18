# -*- coding: utf-8 -*-
"""插件自定义消息类型注册表（message_types 扩展点）。

插件 config.yaml 通过 ``message_types`` 字段声明自带的自定义网关消息类型
实现目录，目录内 .py 文件导出 ``message_handler(message)`` 函数，安装后
自动注册到 ``MessageTypeRegistry``。网关收到该类型消息时，分发到插件注册的
处理函数执行，实现插件对网关协议（node_protocol）的横向扩展。

与 platforms / timer_actions / audit 扩展点一样遵循可逆效应：加载时登记到
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
class MessageType:
    """插件注册的自定义网关消息类型定义。"""

    name: str
    description: str
    plugin: Optional[str]
    function: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]


class MessageTypeRegistry:
    """插件自定义消息类型注册表（进程内全局单例）。

    维护「消息类型名 -> MessageType」映射，提供注册、查询、撤销与目录加载接口。
    消息处理上下文在 gateway 进程内，由 node_manager 收到对应类型消息时分发到
    插件的处理函数。
    """

    _instance: Optional["MessageTypeRegistry"] = None

    def __init__(self) -> None:
        self._message_types: Dict[str, MessageType] = {}
        # 插件消息类型来源追踪：消息类型名 -> 来源插件名（可逆效应，供卸载撤销）
        self._plugin_message_type_sources: Dict[str, str] = {}

    @classmethod
    def instance(cls) -> "MessageTypeRegistry":
        """获取全局单例。"""
        if cls._instance is None:
            cls._instance = MessageTypeRegistry()
        return cls._instance

    # ------------------------------------------------------------------
    # 注册 / 撤销
    # ------------------------------------------------------------------
    def register(
        self,
        name: str,
        function: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
        description: str = "",
        plugin: Optional[str] = None,
    ) -> None:
        """注册单个自定义消息类型。

        参数:
            name: 消息类型名（node_protocol 消息的 type 字段使用）
            function: 消息处理函数，签名 ``message_handler(message)``
            description: 消息类型描述
            plugin: 来源插件名（可逆效应来源追踪）
        """
        self._message_types[name] = MessageType(
            name=name,
            description=description,
            plugin=plugin,
            function=function,
        )
        if plugin:
            self._plugin_message_type_sources[name] = plugin

    def unregister(self, name: str) -> bool:
        """撤销单个自定义消息类型。"""
        if name not in self._message_types:
            return False
        del self._message_types[name]
        self._plugin_message_type_sources.pop(name, None)
        return True

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def get(self, name: str) -> Optional[MessageType]:
        """按消息类型名查询。"""
        return self._message_types.get(name)

    def list_message_types(self) -> List[Dict[str, Any]]:
        """列出全部已注册消息类型的可序列化信息。"""
        return [
            {
                "name": message_type.name,
                "description": message_type.description,
                "plugin": message_type.plugin,
            }
            for message_type in sorted(
                self._message_types.values(), key=lambda m: m.name
            )
        ]

    def get_plugin_message_types(self, plugin: str) -> List[str]:
        """返回指定插件注册的消息类型名列表。"""
        return sorted(
            name
            for name, src in self._plugin_message_type_sources.items()
            if src == plugin
        )

    # ------------------------------------------------------------------
    # 目录加载（message_types 扩展点）
    # ------------------------------------------------------------------
    @staticmethod
    def _infer_source_plugin(directory: str) -> Optional[str]:
        """从消息类型目录路径反推来源插件名（可逆效应来源追踪）。

        当目录路径形如 <...>/plugins/<plugin_name>/message_types 时返回插件名，
        否则返回 None（表示非插件来源的消息类型目录）。
        """
        try:
            normalized = directory.replace("\\", "/")
            marker = "/plugins/"
            if marker in normalized:
                return normalized.split(marker, 1)[1].split("/", 1)[0]
        except Exception:
            pass
        return None

    def load_plugin_message_types(self) -> None:
        """从插件声明的消息类型目录加载自定义消息类型（message_types 扩展点）。

        目录内每个 .py 文件（跳过 __init__.py）按以下约定注册：
        - 模块级函数 ``message_handler(message)``：消息处理函数
        - 模块级 ``MESSAGE_TYPE_NAME``：消息类型名（缺省用文件名）
        - 模块级 ``MESSAGE_TYPE_DESCRIPTION``：消息类型描述（可选）
        - 可选 ``register_message_types()`` 工厂：返回 ``(name, function,
          description)`` 或 ``(name, function)`` 元组列表，用于单文件注册多个类型

        加载成功后登记到 PluginRegistry（可逆效应），供卸载时精确撤销。
        """
        from jarvis.jarvis_utils.config import get_plugin_message_type_dirs
        from jarvis.jarvis_tools.plugin_registry import PluginRegistry
        from jarvis.jarvis_utils.output import PrettyOutput

        registry = PluginRegistry.instance()
        for directory in get_plugin_message_type_dirs():
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
                            registry.register_message_type(source_plugin, name)
                except Exception as e:
                    PrettyOutput.auto_print(
                        f"⚠️ 加载消息类型 {module_name} 失败: {e}"
                    )

    def _register_from_module(
        self,
        module: Any,
        module_name: str,
        source_plugin: Optional[str],
    ) -> List[str]:
        """从单个模块注册消息类型，返回注册的消息类型名列表。"""
        from jarvis.jarvis_utils.output import PrettyOutput

        registered: List[str] = []
        # 工厂方法：register_message_types() 返回 (name, function[, description]) 列表
        factory = getattr(module, "register_message_types", None)
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
                    f"⚠️ 消息类型工厂 {module_name}.register_message_types 失败: {e}"
                )
            return registered

        # 单消息类型：message_handler(message) 函数 + 模块级常量
        function = getattr(module, "message_handler", None)
        if not callable(function):
            PrettyOutput.auto_print(
                f"⚠️ 消息类型模块 {module_name} 缺少 message_handler 函数或 "
                f"register_message_types 工厂，已跳过"
            )
            return registered
        name = getattr(module, "MESSAGE_TYPE_NAME", None) or module_name
        description = getattr(module, "MESSAGE_TYPE_DESCRIPTION", "") or ""
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
        """撤销指定插件注册的全部自定义消息类型（可逆效应）。

        返回被撤销的消息类型数量。
        """
        from jarvis.jarvis_tools.plugin_registry import PluginRegistry

        registry = PluginRegistry.instance()
        names = self.get_plugin_message_types(plugin)
        count = 0
        for name in names:
            if self.unregister(name):
                count += 1
        registry.clear_message_types(plugin)
        return count

    def reload_plugin_message_types(self) -> None:
        """插件变更后免重启重载插件自定义消息类型（message_types 扩展点）。

        先撤销当前已注册的全部插件消息类型，再按最新配置重新加载，使插件安装/
        卸载/升级后的消息类型声明立即生效。失败仅告警，不阻断调用方。
        """
        from jarvis.jarvis_tools.plugin_registry import PluginRegistry
        from jarvis.jarvis_utils.output import PrettyOutput

        registry = PluginRegistry.instance()
        # 撤销当前已注册的全部插件消息类型（按来源插件名逐个撤销）
        for plugin_name in list(registry.registered_plugins()):
            if registry.get_plugin_message_types(plugin_name):
                try:
                    self.unregister_by_plugin(plugin_name)
                except Exception as e:
                    PrettyOutput.auto_print(
                        f"⚠️ 撤销插件 '{plugin_name}' 消息类型失败: {e}"
                    )
        # 重新加载插件消息类型
        try:
            self.load_plugin_message_types()
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 重载插件消息类型失败: {e}")

    def clear(self) -> None:
        """清空全部登记（主要用于测试隔离）。"""
        self._message_types.clear()
        self._plugin_message_type_sources.clear()


__all__ = ["MessageTypeRegistry", "MessageType"]
