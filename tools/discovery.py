import os
import importlib
import inspect
from typing import List, Type
from .base import Tool

class ToolDiscovery:
    """Tool discovery and auto-registration"""
    
    @staticmethod
    def discover_tools(tools_dir: str = None) -> List[Type[Tool]]:
        """
        Discover all tool classes in the tools directory
        
        Args:
            tools_dir: Directory to scan for tools. If None, uses current directory
        
        Returns:
            List of discovered tool classes
        """
        if tools_dir is None:
            tools_dir = os.path.dirname(os.path.abspath(__file__))
        
        print(f"Scanning directory: {tools_dir}")
        tool_classes = []
        
        # Get all .py files in the tools directory
        for filename in os.listdir(tools_dir):
            if filename.endswith('_tool.py'):
                print(f"Found tool file: {filename}")
                # Convert filename to module name
                module_name = f".{filename[:-3]}"  # Remove .py
                
                try:
                    # Import the module
                    module = importlib.import_module(module_name, package="tools")
                    
                    # Find all classes that inherit from Tool
                    for name, obj in inspect.getmembers(module):
                        if (inspect.isclass(obj) and 
                            issubclass(obj, Tool) and 
                            obj != Tool and
                            not name.startswith('_')):
                            tool_classes.append(obj)
                            print(f"Discovered tool class: {name} from {filename}")
                            
                except Exception as e:
                    print(f"Error loading tool module {filename}: {e}")
                    import traceback
                    traceback.print_exc()
        
        return tool_classes

class AutoRegisteringToolRegistry:
    """Tool registry with auto-discovery capabilities"""
    
    def __init__(self, tools_dir: str = None):
        self.tools = {}
        self.tools_dir = tools_dir
        self._discover_and_register()
    
    def _discover_and_register(self):
        """Discover and register all available tools"""
        tool_classes = ToolDiscovery.discover_tools(self.tools_dir)
        
        for tool_class in tool_classes:
            try:
                # Create instance and register
                tool = tool_class()
                self.register(tool)
            except Exception as e:
                print(f"Error registering tool {tool_class.__name__}: {e}")
    
    def register(self, tool: Tool):
        """Register a tool"""
        self.tools[tool.tool_id] = tool
    
    def get_tool(self, name: str) -> Tool:
        """Get tool by name"""
        return self.tools.get(name)
    
    def get_tools_description(self) -> str:
        """Get description of all registered tools"""
        return "\n".join(tool.get_description() for tool in self.tools.values())
    
    def list_tools(self) -> List[str]:
        """List all registered tool IDs"""
        return list(self.tools.keys()) 