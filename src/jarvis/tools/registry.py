import importlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Optional

from jarvis.models.registry import PlatformRegistry
from jarvis.tools.base import Tool
from jarvis.utils import OutputType, PrettyOutput, get_max_context_length



def load_tools() -> str:
    """Load tools"""
    PrettyOutput.section("Available tools", OutputType.PLANNING)
    tools = ToolRegistry.get_global_tool_registry().get_all_tools()
    if tools:
        tools_prompt = "Available tools:\n"
        for tool in tools:
            PrettyOutput.print(f"{tool['name']}: {tool['description']}", OutputType.INFO)
            tools_prompt += f"- Name: {tool['name']}\n"
            tools_prompt += f"  Description: {tool['description']}\n"
            tools_prompt += f"  Parameters: {tool['parameters']}\n"
            tools_prompt += f"  Usage Format: <TOOL_CALL>\n"
        tools_prompt += """
Tool Usage Format:

<TOOL_CALL>
name: tool_name
arguments:
    param1: value1
    param2: value2
</TOOL_CALL>
---------------------------------------------
"""
        return tools_prompt
    return ""

class ToolRegistry:
    global_tool_registry = None # type: ignore
    def __init__(self):
        """Initialize tool registry"""
        self.tools: Dict[str, Tool] = {}
        # Load built-in tools and external tools
        self._load_builtin_tools()
        self._load_external_tools()
        # Ensure max_context_length is an integer
        self.max_context_length = int(get_max_context_length() * 0.8)

    def use_tools(self, name: List[str]):
        """Use a tool"""
        tools = self.tools.keys()
        for tool_name in name:
            if tool_name not in tools:
                PrettyOutput.print(f"Tool {tool_name} does not exist, available tools: {', '.join(tools)}", OutputType.WARNING)
        self.tools = {tool_name: self.tools[tool_name] for tool_name in name}

    @staticmethod
    def get_global_tool_registry():
        """Get the global tool registry"""
        if ToolRegistry.global_tool_registry is None:
            ToolRegistry.global_tool_registry = ToolRegistry()
        return ToolRegistry.global_tool_registry

    def _load_builtin_tools(self):
        """Load tools from the built-in tools directory"""
        tools_dir = Path(__file__).parent
        
        # Iterate through all .py files in the directory
        for file_path in tools_dir.glob("*.py"):
            # Skip base.py and __init__.py
            if file_path.name in ["base.py", "__init__.py", "registry.py"]:
                continue
                
            self.register_tool_by_file(str(file_path))

    def _load_external_tools(self):
        """Load external tools from ~/.jarvis/tools"""
        external_tools_dir = Path.home() / '.jarvis/tools'
        if not external_tools_dir.exists():
            return
            
        # Iterate through all .py files in the directory
        for file_path in external_tools_dir.glob("*.py"):
            # Skip __init__.py
            if file_path.name == "__init__.py":
                continue
                
            self.register_tool_by_file(str(file_path))

    def register_tool_by_file(self, file_path: str):
        """Load and register tools from a specified file
        
        Args:
            file_path: The path of the tool file
            
        Returns:
            bool: Whether the tool is loaded successfully
        """
        try:
            p_file_path = Path(file_path).resolve()  # Get the absolute path
            if not p_file_path.exists() or not p_file_path.is_file():
                PrettyOutput.print(f"File does not exist: {p_file_path}", OutputType.ERROR)
                return False
                
            # Dynamically import the module
            module_name = p_file_path.stem
            spec = importlib.util.spec_from_file_location(module_name, p_file_path) # type: ignore
            if not spec or not spec.loader:
                PrettyOutput.print(f"Failed to load module: {p_file_path}", OutputType.ERROR)
                return False
                
            module = importlib.util.module_from_spec(spec) # type: ignore
            sys.modules[module_name] = module  # Add to sys.modules to support relative imports
            spec.loader.exec_module(module)
            
            # Find the tool class in the module
            tool_found = False
            for item_name in dir(module):
                item = getattr(module, item_name)
                # Check if it is a class and has the necessary attributes
                if (isinstance(item, type) and 
                    hasattr(item, 'name') and 
                    hasattr(item, 'description') and 
                    hasattr(item, 'parameters')):
                    
                    # Instantiate the tool class, passing in the model and output processor
                    tool_instance = item()
                    
                    # Register the tool
                    self.register_tool(
                        name=tool_instance.name,
                        description=tool_instance.description,
                        parameters=tool_instance.parameters,
                        func=tool_instance.execute
                    )
                    tool_found = True
                    break
                    
            if not tool_found:
                PrettyOutput.print(f"No valid tool class found in the file: {p_file_path}", OutputType.WARNING)
                return False
                
            return True
            
        except Exception as e:
            PrettyOutput.print(f"Failed to load tool from {p_file_path.name}: {str(e)}", OutputType.ERROR)
            return False

    def register_tool(self, name: str, description: str, parameters: Dict, func: Callable):
        """Register a new tool"""
        self.tools[name] = Tool(name, description, parameters, func)

    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool"""
        return self.tools.get(name)

    def get_all_tools(self) -> List[Dict]:
        """Get all tools in Ollama format definition"""
        return [tool.to_dict() for tool in self.tools.values()]

    def execute_tool(self, name: str, arguments: Dict) -> Dict[str, Any]:
        """Execute a specified tool"""
        tool = self.get_tool(name)
        if tool is None:
            return {"success": False, "stderr": f"Tool {name} does not exist, available tools: {', '.join(self.tools.keys())}", "stdout": ""}
        return tool.execute(arguments)

    def handle_tool_calls(self, tool_calls: List[Dict]) -> str:
        """Handle tool calls, only process the first tool"""
        try:
            if not tool_calls:
                return ""
                
            # Only process the first tool call
            tool_call = tool_calls[0]
            name = tool_call["name"]
            args = tool_call["arguments"]

            tool_call_help = """
Tool Usage Format:

<TOOL_CALL>
name: tool_name
arguments:
    param1: value1
    param2: value2
</TOOL_CALL>
"""
            
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    PrettyOutput.print(f"Invalid tool parameters format: {name} {tool_call_help}", OutputType.ERROR)
                    return ""

            # Display tool call information
            PrettyOutput.section(f"Executing tool: {name}", OutputType.TOOL)
            if isinstance(args, dict):
                for key, value in args.items():
                    PrettyOutput.print(f"Parameter: {key} = {value}", OutputType.DEBUG)
            else:
                PrettyOutput.print(f"Parameter: {args}", OutputType.DEBUG)
            
            # Execute tool call
            result = self.execute_tool(name, args)

            stdout = result["stdout"]
            stderr = result.get("stderr", "")
            output_parts = []
            if stdout:
                output_parts.append(f"Output:\n{stdout}")
            if stderr:
                output_parts.append(f"Error:\n{stderr}")
            output = "\n\n".join(output_parts)
            output = "no output and error" if not output else output
            
            # Process the result
            if result["success"]:
                
                PrettyOutput.section("Execution successful", OutputType.SUCCESS)
                
                # If the output exceeds 4k characters, use a large model to summarize
                if len(output) > self.max_context_length:
                    try:
                        PrettyOutput.print("Output is too long, summarizing...", OutputType.PROGRESS)
                        model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
                        
                        # If the output exceeds the maximum context length, only take the last part
                        max_len = self.max_context_length
                        if len(output) > max_len:
                            output_to_summarize = output[-max_len:]
                            truncation_notice = f"\n(Note: Due to the length of the output, only the last {max_len} characters are summarized)"
                        else:
                            output_to_summarize = output
                            truncation_notice = ""

                        prompt = f"""Please summarize the execution result of the following tool, extracting key information and important results. Note:
1. Keep all important numerical values, paths, error information, etc.
2. Maintain the accuracy of the results
3. Describe the main content in concise language
4. If there is error information, ensure it is included in the summary

Tool name: {name}
Execution result:
{output_to_summarize}

Please provide a summary:"""

                        summary = model.chat_until_success(prompt)
                        output = f"""--- Original output is too long, here is the summary ---{truncation_notice}

{summary}

--- Summary ends ---"""
                        
                    except Exception as e:
                        PrettyOutput.print(f"Summary failed: {str(e)}", OutputType.ERROR)
                        output = f"Output is too long ({len(output)} characters), it is recommended to view the original output.\nPreview of the first 300 characters:\n{output[:300]}..."
            
            else:
                PrettyOutput.section("Execution failed", OutputType.ERROR)
                
            return output
            
        except Exception as e:
            PrettyOutput.print(f"Tool execution failed: {str(e)}", OutputType.ERROR)
            return f"Tool call failed: {str(e)}"
