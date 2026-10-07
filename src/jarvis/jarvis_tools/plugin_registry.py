# -*- coding: utf-8 -*-
"""插件资源注册追踪器（可逆效应的事实来源）。

借鉴 Cordis 的 reversible effects 理念：插件在加载时显式登记它注册了哪些
资源（工具、规则等），卸载时按登记精确撤销，实现 register/unregister 完全对称。

PluginRegistry 是进程内全局单例，被 ToolRegistry / RulesManager 在加载插件
资源时写入，被 uninstall_plugin 在卸载时读取并撤销。它是插件可逆效应的唯一
事实来源，不依赖路径反推，而是显式登记。
"""

from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Set


class PluginRegistry:
    """插件资源注册追踪器。

    维护「插件名 -> 该插件注册的工具名/规则名集合」的映射，提供登记、查询与
    整体撤销接口。卸载插件时调用 revoke_plugin 即可精确撤销该插件注册的
    全部资源。

    同时持有全局撤销器（由 ToolRegistry / RulesManager 实例注册），
    revoke_plugin 据此实际执行卸载。
    """

    _instance: Optional["PluginRegistry"] = None

    def __init__(self) -> None:
        self._plugin_tools: Dict[str, Set[str]] = {}
        self._plugin_rules: Dict[str, Set[str]] = {}
        self._tool_revoker: Optional[Callable[[str], int]] = None
        self._rules_revoker: Optional[Callable[[str], int]] = None

    @classmethod
    def instance(cls) -> "PluginRegistry":
        """获取全局单例。"""
        if cls._instance is None:
            cls._instance = PluginRegistry()
        return cls._instance

    # ------------------------------------------------------------------
    # 撤销器注册
    # ------------------------------------------------------------------
    def set_tool_revoker(self, revoker: Optional[Callable[[str], int]]) -> None:
        """注册/清除全局工具撤销器（由 ToolRegistry 实例注册）。

        撤销器签名：revoker(plugin_name) -> 被撤销的工具数量。
        """
        self._tool_revoker = revoker

    def set_rules_revoker(self, revoker: Optional[Callable[[str], int]]) -> None:
        """注册/清除全局规则撤销器（由 RulesManager 实例注册）。

        撤销器签名：revoker(plugin_name) -> 被撤销的规则数量。
        """
        self._rules_revoker = revoker

    # ------------------------------------------------------------------
    # 登记
    # ------------------------------------------------------------------
    def register_tool(self, plugin_name: str, tool_name: str) -> None:
        """登记插件注册的单个工具。"""
        self._plugin_tools.setdefault(plugin_name, set()).add(tool_name)

    def register_tools(self, plugin_name: str, tool_names: List[str]) -> None:
        """登记插件注册的一批工具。"""
        if not tool_names:
            return
        self._plugin_tools.setdefault(plugin_name, set()).update(tool_names)

    def register_rule(self, plugin_name: str, rule_name: str) -> None:
        """登记插件注册的单个规则。"""
        self._plugin_rules.setdefault(plugin_name, set()).add(rule_name)

    def register_rules(self, plugin_name: str, rule_names: List[str]) -> None:
        """登记插件注册的一批规则。"""
        if not rule_names:
            return
        self._plugin_rules.setdefault(plugin_name, set()).update(rule_names)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def get_plugin_tools(self, plugin_name: str) -> List[str]:
        """返回插件注册的工具名列表。"""
        return sorted(self._plugin_tools.get(plugin_name, set()))

    def get_plugin_rules(self, plugin_name: str) -> List[str]:
        """返回插件注册的规则名列表。"""
        return sorted(self._plugin_rules.get(plugin_name, set()))

    def registered_plugins(self) -> List[str]:
        """返回已登记资源的插件名列表。"""
        return sorted(set(self._plugin_tools.keys()) | set(self._plugin_rules.keys()))

    # ------------------------------------------------------------------
    # 撤销
    # ------------------------------------------------------------------
    def unregister_plugin(self, plugin_name: str) -> Dict[str, List[str]]:
        """撤销指定插件注册的全部资源，并返回被撤销的内容。

        返回:
            {"tools": [...], "rules": [...]}：该插件登记的工具名与规则名。
            调用方需据此实际执行卸载（从 ToolRegistry / RulesManager 移除）。
        """
        tools = list(self._plugin_tools.pop(plugin_name, set()))
        rules = list(self._plugin_rules.pop(plugin_name, set()))
        return {"tools": tools, "rules": rules}

    def clear_tools(self, plugin_name: str) -> None:
        """仅清理指定插件的工具登记（不影响规则登记）。"""
        self._plugin_tools.pop(plugin_name, None)

    def clear_rules(self, plugin_name: str) -> None:
        """仅清理指定插件的规则登记（不影响工具登记）。"""
        self._plugin_rules.pop(plugin_name, None)

    def revoke_plugin(self, plugin_name: str) -> Dict[str, int]:
        """撤销指定插件注册的全部资源并实际执行卸载。

        通过已注册的全局撤销器（ToolRegistry / RulesManager 实例）实际移除
        该插件注册的工具与规则，并清理登记。

        返回:
            {"tools": int, "rules": int}：被撤销的工具数与规则数。
        """
        tools = self.get_plugin_tools(plugin_name)
        rules = self.get_plugin_rules(plugin_name)
        revoked_tools = 0
        revoked_rules = 0
        if tools and self._tool_revoker is not None:
            try:
                revoked_tools = int(self._tool_revoker(plugin_name))
            except Exception:
                revoked_tools = 0
        if rules and self._rules_revoker is not None:
            try:
                revoked_rules = int(self._rules_revoker(plugin_name))
            except Exception:
                revoked_rules = 0
        # 清理登记（撤销器内部也会清理，这里兜底）
        self.unregister_plugin(plugin_name)
        return {"tools": revoked_tools, "rules": revoked_rules}

    def has_plugin(self, plugin_name: str) -> bool:
        """判断插件是否已登记资源。"""
        return plugin_name in self._plugin_tools or plugin_name in self._plugin_rules

    def clear(self) -> None:
        """清空全部登记与撤销器（主要用于测试隔离）。"""
        self._plugin_tools.clear()
        self._plugin_rules.clear()
        self._tool_revoker = None
        self._rules_revoker = None


__all__ = ["PluginRegistry"]
