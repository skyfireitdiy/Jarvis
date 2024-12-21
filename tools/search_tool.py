import os
import time
from typing import Dict, Any, Optional
from datetime import datetime
from tavily import TavilyClient
from .base import Tool, tool

@tool(tool_id="search", name="Search Tool")
class SearchTool(Tool):
    """互联网搜索工具"""
    
    def __init__(self):
        examples = {
            "天气查询": 'query: "北京今天天气"',
            "新闻搜索": 'query: "人工智能最新新闻"',
            "实时信息": 'query: "比特币当前价格"',
            "限制结果": 'query: "上海空气质量", limit: 3'
        }
        
        super().__init__(
            tool_id="search",
            name="网络搜索",
            description=(
                "首选工具，用于从互联网获取实时信息。\n"
                "\n"
                "适用场景：\n"
                "- 查询当前天气状况\n"
                "- 获取最新新闻事件\n"
                "- 实时数据（价格、比分等）\n"
                "- 最新事实和信息\n"
                "- 公开数据和统计\n"
                "\n"
                "使用规则：\n"
                "1. 查询必须明确具体\n"
                "2. 每次查询有结果数量限制\n"
                "3. 结果按相关性排序\n"
                "4. 支持中英文查询\n"
                "5. 返回结果包含来源信息"
            ),
            parameters={
                "query": "搜索查询字符串（必需）",
                "limit": "返回结果的最大数量（可选，默认：5）"
            },
            examples=examples
        )
        
        # 从环境变量获取API密钥
        api_key = os.getenv('TAVILY_API_KEY')
        if not api_key:
            raise ValueError("未设置 TAVILY_API_KEY 环境变量")
        
        # 初始化 Tavily 客户端
        self.client = TavilyClient(api_key=api_key)
    
    def process_result(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """处理单个搜索结果，提取所有可用信息"""
        result = {
            # 基本信息
            "title": item.get('title', ''),
            "url": item.get('url', ''),
            "content": item.get('content', ''),
            
            # 来源信息
            "source": {
                "domain": item.get('domain', ''),
                "published_date": item.get('published_date', ''),
                "author": item.get('author', ''),
                "language": item.get('language', '')
            },
            
            # 相关性和可信度
            "relevance": {
                "score": item.get('score', 0),
                "relevance_score": item.get('relevance_score', 0),
                "credibility_score": item.get('credibility_score', 0)
            }
        }
        
        return result
    
    def format_search_output(self, search_data: Dict[str, Any]) -> str:
        """将搜索数据格式化为可读的字符串输出"""
        output = []
        
        # 添加见解（如果有）
        if search_data.get('insights'):
            insights = search_data['insights']
            if insights.get('answer'):
                output.append(f"答案：{insights['answer']}")
            if insights.get('context'):
                output.append(f"上下文：{insights['context']}")
        
        # 如果没有直接答案，尝试从第一个结果构建答案
        if not output and search_data.get('results'):
            first_result = search_data['results'][0]
            output.append(f"答案：{first_result['content'][:500]}")
        
        # 如果仍然没有输出，表示未找到答案
        if not output:
            output.append("未找到查询的直接答案。")
        
        return "\n".join(output)
    
    def execute(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """执行搜索查询"""
        if not query.strip():
            error_msg = "收到空查询"
            return {
                "success": False,
                "error": error_msg,
                "result": {
                    "stdout": "",
                    "stderr": error_msg,
                    "returncode": -1,
                    "command": f"search query='{query}' limit={limit}",
                    "search_data": {
                        "query": query,
                        "results": [],
                        "total_results": 0,
                        "search_time": datetime.now().isoformat()
                    }
                }
            }
        
        if limit < 1:
            limit = 1
        elif limit > 100:
            limit = 100
            
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                # 重试之间添加随机延迟
                if attempt > 0:
                    delay = retry_delay * attempt
                    time.sleep(delay)
                
                # 发起API请求
                start_time = time.time()
                response = self.client.search(
                    query=query,
                    max_results=limit,
                    include_answer=True,
                    include_raw_content=True,
                    include_images=True,
                    search_depth="advanced",
                    get_raw_response=True
                )
                response_time = time.time() - start_time
                
                if not response.get('results'):
                    raise Exception("未找到结果")
                
                # 处理结果
                results = []
                for idx, item in enumerate(response['results'][:limit], 1):
                    result = self.process_result(item)
                    result['position'] = idx
                    results.append(result)
                
                if results:
                    # 准备搜索见解
                    insights = {
                        "answer": response.get('answer', ''),
                        "context": response.get('context', ''),
                        "topics": response.get('topics', []),
                        "keywords": response.get('keywords', []),
                        "sentiment": response.get('sentiment', {}),
                        "key_insights": response.get('key_insights', []),
                        "suggested_queries": response.get('suggested_queries', [])
                    }
                    
                    # 准备完整的搜索数据
                    search_data = {
                        "query": query,
                        "results": results,
                        "total_results": len(results),
                        "search_time": datetime.now().isoformat(),
                        "insights": insights,
                        "search_metadata": {
                            "engine": "Tavily",
                            "attempt": attempt + 1,
                            "response_time": response_time,
                            "search_type": response.get('search_type', ''),
                            "search_depth": response.get('search_depth', ''),
                            "raw_response": response if response.get('include_raw_response') else None
                        }
                    }
                    
                    # 格式化输出
                    formatted_output = self.format_search_output(search_data)
                    
                    return {
                        "success": True,
                        "result": {
                            "stdout": formatted_output,
                            "stderr": "",
                            "returncode": 0,
                            "command": f"search query='{query}' limit={limit}",
                            "search_data": search_data  # 保留所有搜索数据
                        }
                    }
                
                raise Exception("未找到有效结果")
                
            except Exception as e:
                if attempt < max_retries - 1:
                    continue
                return {
                    "success": False,
                    "error": str(e),
                    "result": {
                        "stdout": "",
                        "stderr": str(e),
                        "returncode": -1,
                        "command": f"search query='{query}' limit={limit}",
                        "search_data": {
                            "query": query,
                            "results": [],
                            "total_results": 0,
                            "search_time": datetime.now().isoformat(),
                            "search_metadata": {
                                "engine": "Tavily",
                                "attempt": attempt + 1
                            }
                        }
                    }
                } 