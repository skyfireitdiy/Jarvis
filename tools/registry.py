from typing import Dict, Optional, List
import os
import importlib
import inspect
from .base import Tool

class ToolRegistry:
    """Tool registry with auto-discovery capabilities"""
    
    def __init__(self, tools_dir: str = None):
        self.tools: Dict[str, Tool] = {}
        self.tools_dir = tools_dir
        self._discover_and_register()
    
    def _discover_and_register(self):
        """Discover and register all available tools"""
        if self.tools_dir is None:
            self.tools_dir = os.path.dirname(os.path.abspath(__file__))
        
        print(f"Scanning directory for tools: {self.tools_dir}")
        
        # Get all .py files in the tools directory
        for filename in os.listdir(self.tools_dir):
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
                            try:
                                # Create instance and register
                                tool = obj()
                                self.register(tool)
                                print(f"Registered tool: {tool.tool_id} from {filename}")
                            except Exception as e:
                                print(f"Error registering tool {name}: {e}")
                            
                except Exception as e:
                    print(f"Error loading tool module {filename}: {e}")
                    import traceback
                    traceback.print_exc()
    
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