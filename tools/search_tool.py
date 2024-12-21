import os
import time
from typing import Dict, Any, Optional
from datetime import datetime
from tavily import TavilyClient
from .base import Tool, tool

@tool(tool_id="search", name="Search Tool")
class SearchTool(Tool):
    """Search for real-time information from the internet."""
    
    def __init__(self, tool_id: str = "search"):
        examples = {
            "basic": 'query: "current bitcoin price"'
        }
        
        super().__init__(
            tool_id=tool_id,
            name="Web Search",
            description=(
                "Search for real-time information using Tavily API.\n"
                "\n"
                "Best For:\n"
                "• Current events and news\n"
                "• Real-time data and prices\n"
                "• Latest information\n"
                "• Fact checking\n"
                "\n"
                "Not For:\n"
                "• Historical data\n"
                "• Calculations\n"
                "• Code execution\n"
                "• Local operations"
            ),
            parameters={
                "query": "Search query (required)",
                "limit": "Maximum results (optional, default 5)"
            },
            examples=examples
        )
        
        # Get API key from environment
        api_key = os.getenv('TAVILY_API_KEY')
        if not api_key:
            raise ValueError("TAVILY_API_KEY environment variable not set")
        
        # Initialize Tavily client
        self.client = TavilyClient(api_key=api_key)
    
    def execute(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Execute search query"""
        if not query.strip():
            return {
                "success": False,
                "error": "Empty query",
                "result": {
                    "stdout": "",
                    "stderr": "Empty query",
                    "returncode": -1
                }
            }
        
        # Validate limit
        limit = max(1, min(limit, 100))
        
        try:
            # Make API request
            response = self.client.search(
                query=query,
                max_results=limit,
                include_answer=True,
                include_raw_content=True,
                include_images=True,
                search_depth="advanced",
                get_raw_response=True
            )
            
            if not response.get('results'):
                raise Exception("No results found")
            
            # Format output
            output = self._format_search_output(response)
            
            return {
                "success": True,
                "result": {
                    "stdout": output,
                    "stderr": "",
                    "returncode": 0,
                    "query": query,
                    "limit": limit
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "result": {
                    "stdout": "",
                    "stderr": str(e),
                    "returncode": -1,
                    "query": query,
                    "limit": limit
                }
            }
    
    def _format_search_output(self, response: Dict[str, Any]) -> str:
        """Format search results into readable output"""
        output = []
        
        # Add answer if available
        if response.get('answer'):
            output.append(f"Answer: {response['answer']}")
        
        # Add context if available
        if response.get('context'):
            output.append(f"Context: {response['context']}")
        
        # If no direct answer, use first result
        if not output and response.get('results'):
            first_result = response['results'][0]
            output.append(f"Answer: {first_result['content'][:500]}")
        
        # If still no output, indicate no answer found
        if not output:
            output.append("No direct answer found.")
        
        return "\n".join(output) 