# -*- coding: utf-8 -*-
"""Web Gateway 公共端点模块

提供 /rules 和 /tools 接口的公共实现，供不同 Agent 复用。
"""

from typing import Any, Dict


def get_rules_info() -> Dict[str, Any]:
    """获取规则信息（总体的和已加载的）。

    返回:
        Dict[str, Any]: 包含规则列表的字典，格式为 {"rules": [...]}
    """
    try:
        from jarvis.jarvis_utils.globals import (
            global_agents,
            running_agent_stack,
        )

        # 获取根agent（running_agent_stack中第一个，即最早启动的agent）
        if running_agent_stack:
            root_agent_name = running_agent_stack[0]
            root_agent = global_agents.get(root_agent_name)
            if root_agent and hasattr(root_agent, "rules_manager"):
                rules_manager = root_agent.rules_manager
                rules_info = rules_manager.get_all_rules_with_status()
                rules_list = [
                    {
                        "name": name,
                        "preview": preview,
                        "is_loaded": is_loaded,
                        "file_path": file_path,
                    }
                    for name, preview, is_loaded, file_path in rules_info
                ]
                return {"rules": rules_list}
        return {"rules": []}
    except Exception as e:
        return {"rules": [], "error": str(e)}


def get_tools_info() -> Dict[str, Any]:
    """获取工具信息（全量工具和允许使用的工具）。

    返回:
        Dict[str, Any]: 包含工具信息的字典，格式为 {"all_tools": [...], "allowed_tools": [...]}
    """
    try:
        from jarvis.jarvis_utils.globals import (
            global_agents,
            running_agent_stack,
        )

        # 获取根agent（running_agent_stack中第一个，即最早启动的agent）
        if running_agent_stack:
            root_agent_name = running_agent_stack[0]
            root_agent = global_agents.get(root_agent_name)
            if root_agent:
                tool_registry = root_agent.get_tool_registry()
                if tool_registry:
                    all_tools = tool_registry.get_all_tools()
                    allowed_tools = getattr(root_agent, "use_tools", None)
                    return {
                        "all_tools": all_tools,
                        "allowed_tools": allowed_tools,
                    }
        return {"all_tools": [], "allowed_tools": None}
    except Exception as e:
        return {"all_tools": [], "allowed_tools": None, "error": str(e)}
