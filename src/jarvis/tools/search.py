from typing import Dict, Any
from duckduckgo_search import DDGS
from ..utils import PrettyOutput, OutputType

class SearchTool:
    name = "search"
    description = "Search for information using DuckDuckGo search engine"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query string"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 5
            }
        },
        "required": ["query"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """使用DuckDuckGo进行搜索"""
        try:
            # 打印搜索查询
            PrettyOutput.print(f"搜索查询: {args['query']}", OutputType.INFO)
            
            # 获取搜索结果
            with DDGS() as ddgs:
                results = ddgs.text(
                    keywords=args["query"],
                    max_results=args.get("max_results", 5)
                )
            
            
            return {
                "success": True,
                "stdout": results,
                "stderr": ""
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"搜索失败: {str(e)}"
            } 