import os
import statistics
from typing import Any, Dict
from jarvis.jarvis_platform.registry import PlatformRegistry


class SearchWebTool:
    name = "search_web"
    description = "搜索互联网上的信息"
    labels = ['web', 'search', 'information']
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "具体的问题"}
        }
    }

    def __init__(self):
        if os.getenv("YUANBAO_COOKIES", "") != "" and os.getenv("YUANBAO_AGENT_ID", "") != "":
            self.platform = "yuanbao"
            self.model = "deep_seek"
        elif os.getenv("KIMI_API_KEY", "") != "":
            self.platform = "kimi"
            self.model = "k1"
        else:
            self.platform = ""


    @staticmethod
    def check() -> bool:
        return os.getenv("YUANBAO_COOKIES", "") != "" and os.getenv("YUANBAO_AGENT_ID", "") != "" or os.getenv("KIMI_API_KEY", "") != ""

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]: # type: ignore
        query = args.get("query")
        model = PlatformRegistry().create_platform(self.platform)
        model.set_suppress_output(False) # type: ignore
        model.set_model_name(self.model) # type: ignore
        return {
            "stdout": model.chat_until_success(query), # type: ignore
            "stderr": "",
            "success": True,
        }