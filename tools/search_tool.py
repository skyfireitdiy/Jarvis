import os
import time
from typing import Dict, Any, Optional
from datetime import datetime
from tavily import TavilyClient
from .base import Tool, tool

@tool(tool_id="search", name="Search Tool")
class SearchTool(Tool):
    """Tavily search tool"""
    
    def __init__(self):
        examples = {
            "Weather search": 'query: "beijing weather today"',
            "News search": 'query: "latest news about AI"',
            "Real-time info": 'query: "current bitcoin price"',
            "With limit": 'query: "shanghai air quality", limit: 3'
        }
        
        super().__init__(
            tool_id="search",
            name="Search Tool",
            description=(
                "PREFERRED TOOL for getting real-time information from the internet. "
                "Use this tool FIRST when you need:"
                "\n- Current weather conditions"
                "\n- Latest news and events"
                "\n- Real-time data (prices, scores, etc.)"
                "\n- Up-to-date facts and information"
                "\n- Public data and statistics"
                "\nProvides rich search results using Tavily API including:"
                "\n- Direct answers to questions"
                "\n- Context and key insights"
                "\n- News and real-time information"
                "\n- Images and visual content"
                "\n- Source credibility scores"
                "\n- Topic analysis and categorization"
            ),
            parameters={
                "query": "Search query string (required)",
                "limit": "Maximum number of results to return (optional, default: 5)"
            },
            examples=examples
        )
        
        # Get API key from environment variable
        api_key = os.getenv('TAVILY_API_KEY')
        if not api_key:
            raise ValueError("TAVILY_API_KEY environment variable is not set")
        
        # Initialize Tavily client
        self.client = TavilyClient(api_key=api_key)
    
    def process_result(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single search result to extract all available information"""
        result = {
            # Basic information
            "title": item.get('title', ''),
            "url": item.get('url', ''),
            "content": item.get('content', ''),
            
            # Source information
            "source": {
                "domain": item.get('domain', ''),
                "published_date": item.get('published_date', ''),
                "author": item.get('author', ''),
                "language": item.get('language', '')
            },
            
            # Relevance and credibility
            "relevance": {
                "score": item.get('score', 0),
                "relevance_score": item.get('relevance_score', 0),
                "credibility_score": item.get('credibility_score', 0)
            }
        }
        
        # Add rich content if available
        rich_content = {}
        
        # Images
        if item.get('image_url'):
            rich_content['images'] = [{
                "url": item['image_url'],
                "alt_text": item.get('image_alt_text', ''),
                "caption": item.get('image_caption', '')
            }]
            
        # Videos
        if item.get('video_url'):
            rich_content['videos'] = [{
                "url": item['video_url'],
                "title": item.get('video_title', ''),
                "duration": item.get('video_duration', '')
            }]
            
        # Tables or structured data
        if item.get('structured_data'):
            rich_content['structured_data'] = item['structured_data']
            
        # Keywords and topics
        if item.get('keywords'):
            rich_content['keywords'] = item['keywords']
            
        if item.get('topics'):
            rich_content['topics'] = item['topics']
            
        # Add rich content if any was found
        if rich_content:
            result['rich_content'] = rich_content
            
        return result
    
    def format_search_output(self, search_data: Dict[str, Any]) -> str:
        """Format search data into a readable string output"""
        output = []
        
        # Add insights if available
        if search_data.get('insights'):
            insights = search_data['insights']
            if insights.get('answer'):
                output.append(f"Answer: {insights['answer']}")
            if insights.get('context'):
                output.append(f"Context: {insights['context']}")
        
        # If no direct answer, try to construct one from the first result
        if not output and search_data.get('results'):
            first_result = search_data['results'][0]
            output.append(f"Answer: {first_result['content'][:500]}")
        
        # If still no output, indicate no answer found
        if not output:
            output.append("No direct answer found for the query.")
        
        return "\n".join(output)
    
    def execute(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Execute search query"""
        if not query.strip():
            error_msg = "Empty query received"
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
                # Add random delay between retries
                if attempt > 0:
                    delay = retry_delay * attempt
                    time.sleep(delay)
                
                # Make API request
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
                    raise Exception("No results found")
                
                # Process results
                results = []
                for idx, item in enumerate(response['results'][:limit], 1):
                    result = self.process_result(item)
                    result['position'] = idx
                    results.append(result)
                
                if results:
                    # Prepare search insights
                    insights = {
                        "answer": response.get('answer', ''),
                        "context": response.get('context', ''),
                        "topics": response.get('topics', []),
                        "keywords": response.get('keywords', []),
                        "sentiment": response.get('sentiment', {}),
                        "key_insights": response.get('key_insights', []),
                        "suggested_queries": response.get('suggested_queries', [])
                    }
                    
                    # Prepare complete search data
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
                    
                    # Format the output for stdout
                    formatted_output = self.format_search_output(search_data)
                    
                    return {
                        "success": True,
                        "result": {
                            "stdout": formatted_output,
                            "stderr": "",
                            "returncode": 0,
                            "command": f"search query='{query}' limit={limit}",
                            "search_data": search_data  # Preserve all search data
                        }
                    }
                
                raise Exception("No valid results found")
                
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