


from typing import Any, Dict
from jarvis.jarvis_platform.registry import PlatformRegistry


class SearchWebTool:
    name = "search_web"
    description = "搜索互联网上的信息"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "具体的问题"}
        }
    }
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]: # type: ignore
        query = args.get("query")
        model = PlatformRegistry().create_platform("yuanbao")
        model.set_suppress_output(False) # type: ignore
        model.set_model_name("deep_seek") # type: ignore
        return {
            "stdout": model.chat_until_success(query), # type: ignore
            "stderr": "",
            "success": True,
        }