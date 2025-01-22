from .registry import ToolRegistry
from jarvis.tools.codebase_qa import CodebaseQATool

__all__ = [
    'ToolRegistry',
] 

def register_tools():
    register_tool(CodebaseQATool()) 
