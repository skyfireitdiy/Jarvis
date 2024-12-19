from typing import Dict, Any, Type, TypeVar
from functools import wraps

T = TypeVar('T', bound='Tool')

def tool(tool_id: str = None, name: str = None):
    """Decorator for tool classes"""
    def decorator(cls: Type[T]) -> Type[T]:
        if tool_id:
            cls.tool_id = tool_id
        if name:
            cls.name = name
        return cls
    return decorator

class Tool:
    """Tool class for agent to use"""
    
    def __init__(self, tool_id: str, name: str, description: str, parameters: Dict[str, str], examples: Dict[str, str] = None):
        """Initialize tool"""
        self.tool_id = tool_id
        self.name = name
        self.description = description
        self.parameters = parameters
        self.examples = examples or {}
    
    def get_description(self) -> str:
        """Get tool description"""
        # Basic description and parameters
        desc = [f"Tool: {self.tool_id}",
               f"Description: {self.description}",
               "\nParameters:"]
        
        for param, param_desc in self.parameters.items():
            desc.append(f"  - {param}: {param_desc}")
        
        # Add examples if available
        if self.examples:
            desc.append("\nExamples:")
            for name, example in self.examples.items():
                desc.append(f"  - {name}: {example}")
        
        return "\n".join(desc)
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute tool with parameters"""
        raise NotImplementedError("Tool must implement execute method")