# -*- coding: utf-8 -*-
"""插件 Agent 类型注册表（agent_types 扩展点）。

插件 config.yaml 通过 ``agent_types`` 字段声明自带的**全新 Agent 类型**
（自定义执行入口/运行逻辑），安装后自动注册到 ``AgentTypeRegistry``，
创建 Agent 时 ``agent_type`` 即可选用插件注册的类型，由插件声明的
``entry_point`` 可执行入口启动：

    agent_types:
      - name: "chat_agent"
        entry_point: "my_plugin_chat_agent"   # 可执行入口
        description: "专用对话 Agent"

与 ``agent_definition_dirs``（定义 Agent 实例）互补：那是「用现有类型配
实例」，这是「造新类型」。与其它扩展点一样遵循可逆效应：加载时登记到
PluginRegistry，卸载时精确撤销。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Dict
from typing import List
from typing import Optional


@dataclass
class AgentType:
    """插件注册的 Agent 类型定义。"""

    name: str
    entry_point: str
    description: str
    plugin: Optional[str]


class AgentTypeRegistry:
    """插件 Agent 类型注册表（进程内全局单例）。

    维护「类型名 -> AgentType」映射，提供注册、查询、撤销与配置加载接口。
    注册的 Agent 类型供 AgentManager 在创建 Agent 时合并到入口点解析
    （内置 agent/code_agent 优先，插件类型不覆盖内置）。
    """

    _instance: Optional["AgentTypeRegistry"] = None

    def __init__(self) -> None:
        self._agent_types: Dict[str, AgentType] = {}
        # 插件类型来源追踪：类型名 -> 来源插件名（可逆效应，供卸载撤销）
        self._plugin_type_sources: Dict[str, str] = {}

    @classmethod
    def instance(cls) -> "AgentTypeRegistry":
        """获取全局单例。"""
        if cls._instance is None:
            cls._instance = AgentTypeRegistry()
        return cls._instance

    # ------------------------------------------------------------------
    # 注册 / 撤销
    # ------------------------------------------------------------------
    def register(
        self,
        name: str,
        entry_point: str,
        description: str = "",
        plugin: Optional[str] = None,
    ) -> None:
        """注册单个 Agent 类型。

        参数:
            name: 类型名（创建 Agent 时 agent_type 使用）
            entry_point: 可执行入口（可执行文件/命令名，由 AgentManager 解析启动）
            description: 类型描述
            plugin: 来源插件名（可逆效应来源追踪）
        """
        self._agent_types[name] = AgentType(
            name=name,
            entry_point=entry_point,
            description=description,
            plugin=plugin,
        )
        if plugin:
            self._plugin_type_sources[name] = plugin

    def unregister(self, name: str) -> bool:
        """撤销单个 Agent 类型。"""
        if name not in self._agent_types:
            return False
        del self._agent_types[name]
        self._plugin_type_sources.pop(name, None)
        return True

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def get(self, name: str) -> Optional[AgentType]:
        """按类型名查询。"""
        return self._agent_types.get(name)

    def list_agent_types(self) -> List[Dict[str, Any]]:
        """列出全部已注册类型的可序列化信息。"""
        return [
            {
                "name": agent_type.name,
                "entry_point": agent_type.entry_point,
                "description": agent_type.description,
                "plugin": agent_type.plugin,
            }
            for agent_type in sorted(
                self._agent_types.values(), key=lambda a: a.name
            )
        ]

    def get_plugin_agent_types(self, plugin: str) -> List[str]:
        """返回指定插件注册的类型名列表。"""
        return sorted(
            name
            for name, src in self._plugin_type_sources.items()
            if src == plugin
        )

    # ------------------------------------------------------------------
    # 配置加载（agent_types 扩展点）
    # ------------------------------------------------------------------
    def load_plugin_agent_types(self) -> None:
        """从插件声明的 agent_types 配置加载 Agent 类型（agent_types 扩展点）。

        插件 config.yaml 通过 ``agent_types`` 字段声明类型列表（对象数组：
        name/entry_point/description），来源在 ``_load_plugin_configs`` 解析
        插件 config 时已按插件名登记到 PluginRegistry，这里按来源聚合到
        AgentTypeRegistry，供卸载时精确撤销。
        """
        from jarvis.jarvis_tools.plugin_registry import PluginRegistry

        registry = PluginRegistry.instance()
        for plugin_name in registry.registered_plugins():
            for type_name in registry.get_plugin_agent_types(plugin_name):
                entry_point = registry.get_plugin_agent_type_entry_point(
                    plugin_name, type_name
                )
                description = registry.get_plugin_agent_type_description(
                    plugin_name, type_name
                )
                if not entry_point:
                    continue
                self.register(
                    type_name,
                    entry_point,
                    description=description,
                    plugin=plugin_name,
                )

    # ------------------------------------------------------------------
    # 插件变更重载
    # ------------------------------------------------------------------
    def unregister_by_plugin(self, plugin: str) -> int:
        """撤销指定插件注册的全部 Agent 类型（可逆效应）。

        返回被撤销的类型数量。
        """
        names = self.get_plugin_agent_types(plugin)
        count = 0
        for name in names:
            if self.unregister(name):
                count += 1
        # 不清 PluginRegistry 来源登记：来源由 _load_plugin_configs 管理
        # （reload_plugin_configs 时重建）；真实卸载由 revoke_plugin 的
        # unregister_plugin 兜底清理，reload 时需保留来源供加载阶段按插件名
        # 重新聚合。
        return count

    def reload_plugin_agent_types(self) -> None:
        """插件变更后免重启重载插件 Agent 类型（agent_types 扩展点）。

        先撤销当前已注册的全部插件 Agent 类型，再按最新配置重新加载，使插件
        安装/卸载/升级后的类型声明立即生效。失败仅告警，不阻断调用方。
        """
        from jarvis.jarvis_utils.output import PrettyOutput

        # 以 AgentTypeRegistry 自身来源追踪为准撤销（不依赖 PluginRegistry
        # 来源登记，来源被清理时也能精确撤销）
        for plugin_name in sorted(
            {src for src in self._plugin_type_sources.values()}
        ):
            try:
                self.unregister_by_plugin(plugin_name)
            except Exception as e:
                PrettyOutput.auto_print(
                    f"⚠️ 撤销插件 '{plugin_name}' Agent 类型失败: {e}"
                )
        # 重新加载插件 Agent 类型
        try:
            self.load_plugin_agent_types()
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 重载插件 Agent 类型失败: {e}")

    def clear(self) -> None:
        """清空全部登记（主要用于测试隔离）。"""
        self._agent_types.clear()
        self._plugin_type_sources.clear()


__all__ = ["AgentTypeRegistry", "AgentType"]
