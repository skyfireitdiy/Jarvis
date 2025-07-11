# -*- coding: utf-8 -*-
from typing import Any, Dict

from jarvis.jarvis_platform.registry import PlatformRegistry


class SearchWebTool:
    name = "search_web"
    description = "搜索互联网上的信息"
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "具体的问题"}},
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:  # type: ignore
        from jarvis.jarvis_agent import Agent
        query = args.get("query")
        agent = args.get("agent", None)
        if not agent:
            return {
                "stdout": "agent is not found",
                "stderr": "agent is not found",
                "success": False,
            }
        if agent.model.support_web():

            model = PlatformRegistry().create_platform(agent.platform)
            if not model:
                return {
                    "stdout": "model is not found",
                    "stderr": "model is not found",
                    "success": False,
                }
            model.set_model_name(agent.model_name)
            model.set_web(True)
            model.set_suppress_output(False)  # type: ignore
            return {
                "stdout": model.chat_until_success(query),  # type: ignore
                "stderr": "",
                "success": True,
            }
        else:
            pass

    @staticmethod
    def check() -> bool:
        """检查当前平台是否支持web功能"""
        return True