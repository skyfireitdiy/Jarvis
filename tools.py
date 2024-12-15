from typing import Dict, Any, Callable

class Tool:
    """Tool class for agent to use"""
    
    def __init__(self, name: str, description: str, parameters: Dict[str, str], execute: Callable):
        """Initialize tool"""
        self.name = name
        self.description = description
        self.parameters = parameters
        self.execute = execute
    
    def get_description(self) -> str:
        """Get tool description"""
        params_desc = "\n  Parameters:\n    " + "\n    ".join(
            f"- {name}: {desc}" for name, desc in self.parameters.items()
        )
        return f"- {self.name}: {self.description}\n{params_desc}"

class ToolRegistry:
    """Tool registry to manage available tools"""
    
    def __init__(self):
        self.tools = {}
    
    def register(self, tool: Tool):
        """Register a tool"""
        self.tools[tool.name] = tool
    
    def get_tool(self, name: str) -> Tool:
        """Get tool by name"""
        return self.tools.get(name)
    
    def get_tools_description(self) -> str:
        """Get description of all registered tools"""
        return "\n".join(tool.get_description() for tool in self.tools.values())
    
    def get_tools_parameters_guide(self) -> str:
        """Get parameter usage guide for all tools"""
        guides = ["Tool parameter requirements:"]
        for name, tool in self.tools.items():
            required_params = [
                param_name for param_name, param in tool.parameters.items()
                if "default" not in param.lower()
            ]
            if required_params:
                guides.append(f"   - {name}: requires {', '.join(required_params)} parameters")
        return "\n".join(guides) 