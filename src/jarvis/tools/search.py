import os
from typing import Dict, Any, List
from ..utils import PrettyOutput, OutputType
from .webpage import WebpageTool
from .bing_search import bing_search

class SearchTool:
    name = "search"
    description = "使用Bing搜索引擎搜索信息，并根据问题提取关键信息"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词"
            },
            "question": {
                "type": "string",
                "description": "需要回答的具体问题，用于从搜索结果中提取相关信息"
            },
            "max_results": {
                "type": "integer",
                "description": "最大搜索结果数量",
                "default": 3
            }
        },
        "required": ["query", "question"]
    }

    def __init__(self, model):
        """初始化搜索工具，需要传入语言模型用于信息提取"""
        self.model = model
        self.webpage_tool = WebpageTool()

    def _search(self, query: str, max_results: int) -> List[Dict]:
        """执行搜索请求"""
        try:
            results = bing_search(query)
            if not results:
                return []
            
            # 格式化搜索结果
            formatted_results = []
            for result in results[:max_results]:
                formatted_results.append({
                    "title": result.get("title", ""),
                    "href": result.get("href", ""),
                    "body": result.get("abstract", "")
                })
            return formatted_results
        except Exception as e:
            PrettyOutput.print(f"搜索请求失败: {str(e)}", OutputType.ERROR)
            return []

    def _extract_info(self, contents: List[str], question: str) -> str:
        """使用语言模型从网页内容中提取关键信息"""
        prompt = {
            "role": "user",
            "content": f"""请根据以下搜索结果内容，回答问题：{question}

搜索结果内容：
{'-' * 40}
{''.join(contents)}
{'-' * 40}

请提供一个简洁、准确的答案，重点关注与问题直接相关的信息。如果搜索结果中没有相关信息，请明确说明。
回答时注意：
1. 保持客观性，只基于搜索结果提供信息
2. 如果不同来源有冲突，请指出差异
3. 适当引用信息来源
4. 如果信息不完整或不确定，请说明"""
        }

        try:
            response = self.model.chat([prompt])
            return response
        except Exception as e:
            return f"信息提取失败: {str(e)}"

    def execute(self, args: Dict) -> Dict[str, Any]:
        """执行搜索并提取信息"""
        try:
            query = args["query"]
            question = args["question"]
            max_results = args.get("max_results", 3)
            
            # 打印搜索信息
            PrettyOutput.print(f"搜索查询: {query}", OutputType.INFO)
            PrettyOutput.print(f"相关问题: {question}", OutputType.INFO)
            
            # 获取搜索结果
            results = self._search(query, max_results)
            if not results:
                return {
                    "success": False,
                    "error": "未能获取任何搜索结果"
                }
            
            # 收集网页内容
            contents = []
            for i, result in enumerate(results, 1):
                try:
                    PrettyOutput.print(f"正在读取第 {i}/{len(results)} 个结果... {result['title']} - {result['href']}", OutputType.PROGRESS)
                    webpage_result = self.webpage_tool.execute({"url": result["href"]})
                    if webpage_result["success"]:
                        contents.append(f"\n来源 {i}：{result['href']}\n")
                        contents.append(webpage_result["stdout"])
                except Exception as e:
                    PrettyOutput.print(f"读取结果 {i} 失败: {str(e)}", OutputType.WARNING)
                    continue
            
            if not contents:
                return {
                    "success": False,
                    "error": "未能获取任何有效的搜索结果"
                }
            
            # 提取信息
            PrettyOutput.print("正在分析搜索结果...", OutputType.PROGRESS)
            analysis = self._extract_info(contents, question)
            
            return {
                "success": True,
                "stdout": f"搜索分析结果：\n\n{analysis}",
                "stderr": ""
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"搜索失败: {str(e)}"
            } 