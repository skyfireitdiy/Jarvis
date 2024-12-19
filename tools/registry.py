from typing import Dict, Optional, List
from .base import Tool

class ToolRegistry:
    """Tool registry for managing available tools"""
    
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
    
    def register(self, tool: Tool):
        """Register a tool"""
        self.tools[tool.tool_id] = tool
    
    def get_tool(self, tool_id: str) -> Optional[Tool]:
        """Get tool by ID"""
        return self.tools.get(tool_id)
    
    def list_tools(self) -> List[str]:
        """List all registered tool IDs"""
        return list(self.tools.keys())
    
    def get_tools_description(self) -> str:
        """Get description of all registered tools"""
        descriptions = []
        for tool in self.tools.values():
            desc = tool.get_description()
            if desc:
                descriptions.append(desc)
        return "\n".join(descriptions) if descriptions else "No tools available" 