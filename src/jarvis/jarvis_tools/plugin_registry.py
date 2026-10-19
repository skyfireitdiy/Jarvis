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
        # 插件名 -> 是否应用于 code_agent（由插件 config 的 code_agent_tools 字段声明）
        self._plugin_code_agent_tools: Dict[str, bool] = {}
        self._plugin_platforms: Dict[str, Set[str]] = {}
        self._plugin_timer_actions: Dict[str, Set[str]] = {}
        self._plugin_audit_sinks: Dict[str, Set[str]] = {}
        self._plugin_audit_event_types: Dict[str, Set[str]] = {}
        self._plugin_message_types: Dict[str, Set[str]] = {}
        # 插件名 -> {Agent 类型名 -> {"entry_point": str, "description": str}}
        self._plugin_agent_types: Dict[str, Dict[str, Dict[str, str]]] = {}
        # 插件名 -> {路由键("METHOD path") -> {"path": str, "method": str, "handler": str}}
        self._plugin_gateway_routes: Dict[str, Dict[str, Dict[str, str]]] = {}
        # 插件名 -> {中间件名 -> {"handler": str}}
        self._plugin_gateway_middleware: Dict[str, Dict[str, Dict[str, str]]] = {}
        self._tool_revoker: Optional[Callable[[str], int]] = None
        self._rules_revoker: Optional[Callable[[str], int]] = None
        self._platform_revoker: Optional[Callable[[str], int]] = None
        self._timer_action_revoker: Optional[Callable[[str], int]] = None
        self._audit_revoker: Optional[Callable[[str], int]] = None
        self._message_type_revoker: Optional[Callable[[str], int]] = None
        self._agent_type_revoker: Optional[Callable[[str], int]] = None
        self._gateway_revoker: Optional[Callable[[str], int]] = None

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

    def set_platform_revoker(self, revoker: Optional[Callable[[str], int]]) -> None:
        """注册/清除全局平台撤销器（由 PlatformRegistry 实例注册）。

        撤销器签名：revoker(plugin_name) -> 被撤销的平台数量。
        """
        self._platform_revoker = revoker

    def set_timer_action_revoker(
        self, revoker: Optional[Callable[[str], int]]
    ) -> None:
        """注册/清除全局定时动作撤销器（由 TimerActionRegistry 实例注册）。

        撤销器签名：revoker(plugin_name) -> 被撤销的定时动作数量。
        """
        self._timer_action_revoker = revoker

    def set_audit_revoker(self, revoker: Optional[Callable[[str], int]]) -> None:
        """注册/清除全局审计扩展撤销器（由 AuditSinkRegistry 实例注册）。

        撤销器签名：revoker(plugin_name) -> 被撤销的审计 sink 数量。
        """
        self._audit_revoker = revoker

    def set_message_type_revoker(
        self, revoker: Optional[Callable[[str], int]]
    ) -> None:
        """注册/清除全局消息类型撤销器（由 MessageTypeRegistry 实例注册）。

        撤销器签名：revoker(plugin_name) -> 被撤销的消息类型数量。
        """
        self._message_type_revoker = revoker

    def set_agent_type_revoker(
        self, revoker: Optional[Callable[[str], int]]
    ) -> None:
        """注册/清除全局 Agent 类型撤销器（由 AgentTypeRegistry 实例注册）。

        撤销器签名：revoker(plugin_name) -> 被撤销的 Agent 类型数量。
        """
        self._agent_type_revoker = revoker

    def set_gateway_revoker(
        self, revoker: Optional[Callable[[str], int]]
    ) -> None:
        """注册/清除全局网关扩展撤销器（由 GatewayExtensionRegistry 实例注册）。

        撤销器签名：revoker(plugin_name) -> 被撤销的路由+中间件数量。
        """
        self._gateway_revoker = revoker

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

    def register_platform(self, plugin_name: str, platform_name: str) -> None:
        """登记插件注册的单个平台。"""
        self._plugin_platforms.setdefault(plugin_name, set()).add(platform_name)

    def register_platforms(self, plugin_name: str, platform_names: List[str]) -> None:
        """登记插件注册的一批平台。"""
        if not platform_names:
            return
        self._plugin_platforms.setdefault(plugin_name, set()).update(platform_names)

    def register_timer_action(self, plugin_name: str, action_name: str) -> None:
        """登记插件注册的单个定时动作。"""
        self._plugin_timer_actions.setdefault(plugin_name, set()).add(action_name)

    def register_timer_actions(
        self, plugin_name: str, action_names: List[str]
    ) -> None:
        """登记插件注册的一批定时动作。"""
        if not action_names:
            return
        self._plugin_timer_actions.setdefault(plugin_name, set()).update(action_names)

    def register_audit_sink(self, plugin_name: str, sink_name: str) -> None:
        """登记插件注册的单个审计 sink。"""
        self._plugin_audit_sinks.setdefault(plugin_name, set()).add(sink_name)

    def register_audit_sinks(
        self, plugin_name: str, sink_names: List[str]
    ) -> None:
        """登记插件注册的一批审计 sink。"""
        if not sink_names:
            return
        self._plugin_audit_sinks.setdefault(plugin_name, set()).update(sink_names)

    def register_audit_event_type(
        self, plugin_name: str, event_type: str
    ) -> None:
        """登记插件注册的单个自定义审计事件类型。"""
        self._plugin_audit_event_types.setdefault(plugin_name, set()).add(event_type)

    def register_audit_event_types(
        self, plugin_name: str, event_types: List[str]
    ) -> None:
        """登记插件注册的一批自定义审计事件类型。"""
        if not event_types:
            return
        self._plugin_audit_event_types.setdefault(plugin_name, set()).update(
            event_types
        )

    def register_message_type(self, plugin_name: str, message_type: str) -> None:
        """登记插件注册的单个自定义消息类型。"""
        self._plugin_message_types.setdefault(plugin_name, set()).add(message_type)

    def register_message_types(
        self, plugin_name: str, message_types: List[str]
    ) -> None:
        """登记插件注册的一批自定义消息类型。"""
        if not message_types:
            return
        self._plugin_message_types.setdefault(plugin_name, set()).update(
            message_types
        )

    def register_agent_type(
        self,
        plugin_name: str,
        agent_type: str,
        entry_point: str = "",
        description: str = "",
    ) -> None:
        """登记插件注册的单个 Agent 类型（含入口点与描述元数据）。

        参数:
            plugin_name: 来源插件名
            agent_type: Agent 类型名（创建 Agent 时 agent_type 使用）
            entry_point: 可执行入口（可执行文件/命令名）
            description: 类型描述
        """
        self._plugin_agent_types.setdefault(plugin_name, {})[agent_type] = {
            "entry_point": entry_point,
            "description": description,
        }

    def register_agent_types(
        self, plugin_name: str, agent_types: List[Dict[str, str]]
    ) -> None:
        """登记插件注册的一批 Agent 类型。

        参数:
            plugin_name: 来源插件名
            agent_types: 类型声明列表，每项为含 name/entry_point/description 的字典
        """
        if not agent_types:
            return
        for entry in agent_types:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if not name:
                continue
            self.register_agent_type(
                plugin_name,
                str(name),
                entry_point=str(entry.get("entry_point") or ""),
                description=str(entry.get("description") or ""),
            )

    def register_gateway_route(
        self,
        plugin_name: str,
        path: str,
        method: str,
        handler: str = "",
    ) -> None:
        """登记插件注册的单个网关路由（含方法/路径/实现目录元数据）。

        参数:
            plugin_name: 来源插件名
            path: 路由路径
            method: HTTP 方法（大写）
            handler: 实现目录路径
        """
        method = (method or "GET").upper()
        key = f"{method} {path}"
        self._plugin_gateway_routes.setdefault(plugin_name, {})[key] = {
            "path": path,
            "method": method,
            "handler": handler,
        }

    def register_gateway_routes(
        self, plugin_name: str, routes: List[Dict[str, str]]
    ) -> None:
        """登记插件注册的一批网关路由。

        参数:
            plugin_name: 来源插件名
            routes: 路由声明列表，每项为含 path/method/handler 的字典
        """
        if not routes:
            return
        for entry in routes:
            if not isinstance(entry, dict):
                continue
            path = entry.get("path")
            if not path:
                continue
            self.register_gateway_route(
                plugin_name,
                str(path),
                str(entry.get("method") or "GET"),
                handler=str(entry.get("handler") or ""),
            )

    def register_gateway_middleware(
        self,
        plugin_name: str,
        name: str,
        handler: str = "",
    ) -> None:
        """登记插件注册的单个网关中间件（含实现目录元数据）。

        参数:
            plugin_name: 来源插件名
            name: 中间件名
            handler: 实现目录路径
        """
        self._plugin_gateway_middleware.setdefault(plugin_name, {})[name] = {
            "handler": handler,
        }

    def register_gateway_middleware_list(
        self, plugin_name: str, middleware: List[Dict[str, str]]
    ) -> None:
        """登记插件注册的一批网关中间件。

        参数:
            plugin_name: 来源插件名
            middleware: 中间件声明列表，每项为含 name/handler 的字典
        """
        if not middleware:
            return
        for entry in middleware:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if not name:
                continue
            self.register_gateway_middleware(
                plugin_name,
                str(name),
                handler=str(entry.get("handler") or ""),
            )

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def get_plugin_tools(self, plugin_name: str) -> List[str]:
        """返回插件注册的工具名列表。"""
        return sorted(self._plugin_tools.get(plugin_name, set()))

    def get_plugin_rules(self, plugin_name: str) -> List[str]:
        """返回插件注册的规则名列表。"""
        return sorted(self._plugin_rules.get(plugin_name, set()))

    def get_plugin_platforms(self, plugin_name: str) -> List[str]:
        """返回插件注册的平台名列表。"""
        return sorted(self._plugin_platforms.get(plugin_name, set()))

    def get_plugin_timer_actions(self, plugin_name: str) -> List[str]:
        """返回插件注册的定时动作名列表。"""
        return sorted(self._plugin_timer_actions.get(plugin_name, set()))

    def get_plugin_audit_sinks(self, plugin_name: str) -> List[str]:
        """返回插件注册的审计 sink 名列表。"""
        return sorted(self._plugin_audit_sinks.get(plugin_name, set()))

    def get_plugin_audit_event_types(self, plugin_name: str) -> List[str]:
        """返回插件登记的自定义审计事件类型列表。"""
        return sorted(self._plugin_audit_event_types.get(plugin_name, set()))

    def get_plugin_message_types(self, plugin_name: str) -> List[str]:
        """返回插件登记的自定义消息类型列表。"""
        return sorted(self._plugin_message_types.get(plugin_name, set()))

    def get_plugin_agent_types(self, plugin_name: str) -> List[str]:
        """返回插件登记的 Agent 类型名列表。"""
        return sorted(self._plugin_agent_types.get(plugin_name, {}).keys())

    def get_plugin_agent_type_entry_point(
        self, plugin_name: str, agent_type: str
    ) -> str:
        """返回插件登记的 Agent 类型的可执行入口。"""
        return str(
            self._plugin_agent_types.get(plugin_name, {}).get(agent_type, {}).get(
                "entry_point", ""
            )
        )

    def get_plugin_agent_type_description(
        self, plugin_name: str, agent_type: str
    ) -> str:
        """返回插件登记的 Agent 类型的描述。"""
        return str(
            self._plugin_agent_types.get(plugin_name, {}).get(agent_type, {}).get(
                "description", ""
            )
        )

    def get_plugin_gateway_routes(self, plugin_name: str) -> List[str]:
        """返回插件登记的网关路由键列表（"METHOD path"）。"""
        return sorted(self._plugin_gateway_routes.get(plugin_name, {}).keys())

    def get_plugin_gateway_route(self, plugin_name: str, route_key: str) -> Dict[str, str]:
        """返回插件登记的单个网关路由元数据。"""
        return dict(
            self._plugin_gateway_routes.get(plugin_name, {}).get(route_key, {})
        )

    def get_plugin_gateway_middleware(self, plugin_name: str) -> List[str]:
        """返回插件登记的网关中间件名列表。"""
        return sorted(self._plugin_gateway_middleware.get(plugin_name, {}).keys())

    def get_plugin_gateway_middleware_handler(
        self, plugin_name: str, middleware_name: str
    ) -> str:
        """返回插件登记的网关中间件的实现目录。"""
        return str(
            self._plugin_gateway_middleware.get(plugin_name, {}).get(
                middleware_name, {}
            ).get("handler", "")
        )

    def registered_plugins(self) -> List[str]:
        """返回已登记资源的插件名列表。"""
        return sorted(
            set(self._plugin_tools.keys())
            | set(self._plugin_rules.keys())
            | set(self._plugin_platforms.keys())
            | set(self._plugin_timer_actions.keys())
            | set(self._plugin_audit_sinks.keys())
            | set(self._plugin_audit_event_types.keys())
            | set(self._plugin_message_types.keys())
            | set(self._plugin_agent_types.keys())
            | set(self._plugin_gateway_routes.keys())
            | set(self._plugin_gateway_middleware.keys())
        )

    # ------------------------------------------------------------------
    # code_agent 适用性登记
    # ------------------------------------------------------------------
    def set_plugin_code_agent_tools(self, plugin_name: str, enabled: bool) -> None:
        """登记/清除插件是否应用于 code_agent。

        由插件 config 的 code_agent_tools 字段声明（加载插件配置时登记）。
        enabled 为 False 时移除登记，表示该插件不应用于 code_agent。
        """
        if enabled:
            self._plugin_code_agent_tools[plugin_name] = True
        else:
            self._plugin_code_agent_tools.pop(plugin_name, None)

    def get_code_agent_tool_plugins(self) -> List[str]:
        """返回声明了应用于 code_agent 的插件名列表。"""
        return sorted(
            name for name, enabled in self._plugin_code_agent_tools.items() if enabled
        )

    # ------------------------------------------------------------------
    # 撤销
    # ------------------------------------------------------------------
    def unregister_plugin(self, plugin_name: str) -> Dict[str, List[str]]:
        """撤销指定插件注册的全部资源，并返回被撤销的内容。

        返回:
            {"tools": [...], "rules": [...], "platforms": [...],
             "timer_actions": [...], "audit_sinks": [...],
             "audit_event_types": [...], "message_types": [...],
             "agent_types": [...]}：该插件登记的
            工具名、规则名、平台名、定时动作名、审计 sink 名、自定义审计事件
            类型、自定义消息类型与 Agent 类型。调用方需据此实际执行卸载（从
            ToolRegistry / RulesManager / PlatformRegistry / TimerActionRegistry /
            AuditSinkRegistry / MessageTypeRegistry / AgentTypeRegistry 移除）。
        """
        tools = list(self._plugin_tools.pop(plugin_name, set()))
        rules = list(self._plugin_rules.pop(plugin_name, set()))
        platforms = list(self._plugin_platforms.pop(plugin_name, set()))
        timer_actions = list(self._plugin_timer_actions.pop(plugin_name, set()))
        audit_sinks = list(self._plugin_audit_sinks.pop(plugin_name, set()))
        audit_event_types = list(
            self._plugin_audit_event_types.pop(plugin_name, set())
        )
        message_types = list(self._plugin_message_types.pop(plugin_name, set()))
        agent_types = list(self._plugin_agent_types.pop(plugin_name, {}).keys())
        gateway_routes = list(self._plugin_gateway_routes.pop(plugin_name, {}).keys())
        gateway_middleware = list(
            self._plugin_gateway_middleware.pop(plugin_name, {}).keys()
        )
        return {
            "tools": tools,
            "rules": rules,
            "platforms": platforms,
            "timer_actions": timer_actions,
            "audit_sinks": audit_sinks,
            "audit_event_types": audit_event_types,
            "message_types": message_types,
            "agent_types": agent_types,
            "gateway_routes": gateway_routes,
            "gateway_middleware": gateway_middleware,
        }

    def clear_tools(self, plugin_name: str) -> None:
        """仅清理指定插件的工具登记（不影响规则登记）。"""
        self._plugin_tools.pop(plugin_name, None)

    def clear_rules(self, plugin_name: str) -> None:
        """仅清理指定插件的规则登记（不影响工具登记）。"""
        self._plugin_rules.pop(plugin_name, None)

    def clear_platforms(self, plugin_name: str) -> None:
        """仅清理指定插件的平台登记（不影响工具/规则登记）。"""
        self._plugin_platforms.pop(plugin_name, None)

    def clear_timer_actions(self, plugin_name: str) -> None:
        """仅清理指定插件的定时动作登记（不影响工具/规则/平台登记）。"""
        self._plugin_timer_actions.pop(plugin_name, None)

    def clear_audit_sinks(self, plugin_name: str) -> None:
        """仅清理指定插件的审计 sink 登记（不影响其它登记）。"""
        self._plugin_audit_sinks.pop(plugin_name, None)

    def clear_audit_event_types(self, plugin_name: str) -> None:
        """仅清理指定插件的自定义审计事件类型登记（不影响其它登记）。"""
        self._plugin_audit_event_types.pop(plugin_name, None)

    def clear_message_types(self, plugin_name: str) -> None:
        """仅清理指定插件的自定义消息类型登记（不影响其它登记）。"""
        self._plugin_message_types.pop(plugin_name, None)

    def clear_agent_types(self, plugin_name: str) -> None:
        """仅清理指定插件的 Agent 类型登记（不影响其它登记）。"""
        self._plugin_agent_types.pop(plugin_name, None)

    def clear_gateway_routes(self, plugin_name: str) -> None:
        """仅清理指定插件的网关路由登记（不影响其它登记）。"""
        self._plugin_gateway_routes.pop(plugin_name, None)

    def clear_gateway_middleware(self, plugin_name: str) -> None:
        """仅清理指定插件的网关中间件登记（不影响其它登记）。"""
        self._plugin_gateway_middleware.pop(plugin_name, None)

    def revoke_plugin(self, plugin_name: str) -> Dict[str, int]:
        """撤销指定插件注册的全部资源并实际执行卸载。

        通过已注册的全局撤销器（ToolRegistry / RulesManager / PlatformRegistry
        / TimerActionRegistry / AuditSinkRegistry / MessageTypeRegistry /
        AgentTypeRegistry / GatewayExtensionRegistry 实例）
        实际移除该插件注册的工具、规则、平台、定时动作、审计扩展、自定义消息
        类型、Agent 类型与网关路由/中间件，并清理登记。

        返回:
            {"tools": int, "rules": int, "platforms": int,
             "timer_actions": int, "audit_sinks": int,
             "audit_event_types": int, "message_types": int,
             "agent_types": int, "gateway_routes": int,
             "gateway_middleware": int}：被撤销的工具数、
            规则数、平台数、定时动作数、审计 sink 数、自定义审计事件类型数、
            自定义消息类型数、Agent 类型数与网关路由/中间件数。
        """
        tools = self.get_plugin_tools(plugin_name)
        rules = self.get_plugin_rules(plugin_name)
        platforms = self.get_plugin_platforms(plugin_name)
        timer_actions = self.get_plugin_timer_actions(plugin_name)
        audit_sinks = self.get_plugin_audit_sinks(plugin_name)
        audit_event_types = self.get_plugin_audit_event_types(plugin_name)
        message_types = self.get_plugin_message_types(plugin_name)
        agent_types = self.get_plugin_agent_types(plugin_name)
        gateway_routes = self.get_plugin_gateway_routes(plugin_name)
        gateway_middleware = self.get_plugin_gateway_middleware(plugin_name)
        revoked_tools = 0
        revoked_rules = 0
        revoked_platforms = 0
        revoked_timer_actions = 0
        revoked_audit_sinks = 0
        revoked_audit_event_types = 0
        revoked_message_types = 0
        revoked_agent_types = 0
        revoked_gateway_routes = 0
        revoked_gateway_middleware = 0
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
        if platforms and self._platform_revoker is not None:
            try:
                revoked_platforms = int(self._platform_revoker(plugin_name))
            except Exception:
                revoked_platforms = 0
        if timer_actions and self._timer_action_revoker is not None:
            try:
                revoked_timer_actions = int(self._timer_action_revoker(plugin_name))
            except Exception:
                revoked_timer_actions = 0
        if (audit_sinks or audit_event_types) and self._audit_revoker is not None:
            try:
                revoked_audit_sinks = int(self._audit_revoker(plugin_name))
            except Exception:
                revoked_audit_sinks = 0
        if message_types and self._message_type_revoker is not None:
            try:
                revoked_message_types = int(self._message_type_revoker(plugin_name))
            except Exception:
                revoked_message_types = 0
        if agent_types and self._agent_type_revoker is not None:
            try:
                revoked_agent_types = int(self._agent_type_revoker(plugin_name))
            except Exception:
                revoked_agent_types = 0
        if (gateway_routes or gateway_middleware) and self._gateway_revoker is not None:
            try:
                revoked_gateway_routes = int(self._gateway_revoker(plugin_name))
            except Exception:
                revoked_gateway_routes = 0
        # 清理登记（撤销器内部也会清理，这里兜底）
        self.unregister_plugin(plugin_name)
        return {
            "tools": revoked_tools,
            "rules": revoked_rules,
            "platforms": revoked_platforms,
            "timer_actions": revoked_timer_actions,
            "audit_sinks": revoked_audit_sinks,
            "audit_event_types": revoked_audit_event_types,
            "message_types": revoked_message_types,
            "agent_types": revoked_agent_types,
            "gateway_routes": revoked_gateway_routes,
            "gateway_middleware": revoked_gateway_middleware,
        }

    def has_plugin(self, plugin_name: str) -> bool:
        """判断插件是否已登记资源。"""
        return (
            plugin_name in self._plugin_tools
            or plugin_name in self._plugin_rules
            or plugin_name in self._plugin_platforms
            or plugin_name in self._plugin_timer_actions
            or plugin_name in self._plugin_audit_sinks
            or plugin_name in self._plugin_audit_event_types
            or plugin_name in self._plugin_message_types
            or plugin_name in self._plugin_agent_types
            or plugin_name in self._plugin_gateway_routes
            or plugin_name in self._plugin_gateway_middleware
        )

    def clear(self) -> None:
        """清空全部登记与撤销器（主要用于测试隔离）。"""
        self._plugin_tools.clear()
        self._plugin_rules.clear()
        self._plugin_code_agent_tools.clear()
        self._plugin_platforms.clear()
        self._plugin_timer_actions.clear()
        self._plugin_audit_sinks.clear()
        self._plugin_audit_event_types.clear()
        self._plugin_message_types.clear()
        self._plugin_agent_types.clear()
        self._plugin_gateway_routes.clear()
        self._plugin_gateway_middleware.clear()
        self._tool_revoker = None
        self._rules_revoker = None
        self._platform_revoker = None
        self._timer_action_revoker = None
        self._audit_revoker = None
        self._message_type_revoker = None
        self._agent_type_revoker = None
        self._gateway_revoker = None


__all__ = ["PluginRegistry"]
