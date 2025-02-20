"""
Tool Generator Tool - Automatically creates new tools using LLM
"""
from pathlib import Path
import re
from typing import Dict, Any
from jarvis.jarvis_platform.registry import PlatformRegistry

class ToolGenerator:
    name = "tool_generator"
    description = "Generates new tools using LLM that integrate with the system"
    parameters = {
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "Name of the new tool"
            },
            "description": {
                "type": "string", 
                "description": "Description of the tool's purpose"
            },
            "input_spec": {
                "type": "string",
                "description": "Specification of required inputs and functionality"
            }
        },
        "required": ["tool_name", "description", "input_spec"]
    }
    
    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Generate and save a new tool using LLM"""
        # Get fresh model instance for each execution
        model = PlatformRegistry.get_global_platform_registry().get_codegen_platform()
        
        try:
            tool_name = arguments["tool_name"]
            description = arguments["description"]
            input_spec = arguments["input_spec"]
            
            # Generate tool implementation using LLM
            prompt = self._create_prompt(tool_name, description, input_spec)
            llm_response = model.chat_until_success(prompt)
            
            # Extract implementation with more flexible parsing
            implementation = self._extract_code(llm_response)
            if not implementation:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Could not extract valid Python code from LLM response"
                }
            
            # Validate return value format
            if not self._validate_return_value_format(implementation):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Generated tool does not follow required return value format"
                }
            
            # Save the new tool
            tools_dir = Path.home() / ".jarvis" / "tools"
            tools_dir.mkdir(parents=True, exist_ok=True)
            tool_file = tools_dir / f"{tool_name}.py"
            
            with open(tool_file, "w") as f:
                f.write(implementation)
            
            return {
                "success": True,
                "stdout": f"Tool successfully generated at: {tool_file}",
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Tool generation failed: {str(e)}"
            }
    
    def _create_prompt(self, tool_name: str, description: str, input_spec: str) -> str:
        """Create the LLM prompt for tool generation"""
        example_code = '''
<TOOL>
from typing import Dict, Any
from jarvis.utils import OutputType, PrettyOutput
from jarvis.jarvis_platform.registry import PlatformRegistry

class CustomTool:
    name = "Tool name"              # Tool name used when calling
    description = "Tool description"       # Tool purpose
    parameters = {                # Parameters JSON Schema
        "type": "object",
        "properties": {
            "param1": {
                "type": "string",
                "description": "Parameter description"
            }
        },
        "required": ["param1"]
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the tool functionality
        
        Args:
            args: Parameters passed to the tool
            
        Returns:
            {
                "success": bool,
                "stdout": str,
                "stderr": str,
            }
        """
        try:
            # Implement the tool logic here
            # Use LLM
            # model = PlatformRegistry.get_global_platform_registry().get_codegen_platform() 
            # result = model.chat_until_success(prompt)

            result = "Tool result"
            return {
                "success": True,
                "stdout": result,
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e)
            }
</TOOL>
'''


        return f'''Create a Python tool class that integrates with the Jarvis system. Follow these requirements:
1. Class name: {tool_name.capitalize()}Tool
2. Description: {description}
3. Input specification: {input_spec}
4. Must include these class attributes:
   - name: str (tool identifier)
   - description: str (tool purpose)
   - parameters: dict (JSON schema for inputs)
5. Must implement execute(self, args: Dict) -> Dict method
6. The execute method MUST return a dictionary with these exact fields:
   - success: bool (indicating operation success)
   - stdout: str (primary output/result)
   - stderr: str (error message if any)
7. Must handle errors gracefully
8. Return ONLY the Python implementation code
9. The code should be complete and ready to use.
10. Output the code in the following format:
<TOOL>
{example_code}
</TOOL>

Example:
{example_code}
'''
    
    def _extract_code(self, response: str) -> str:
        """Flexibly extract Python code from LLM response"""
        # Find the first occurrence of <TOOL> and </TOOL>
        sm = re.search(r'<TOOL>(.*?)</TOOL>', response, re.DOTALL)
        if sm:
            return sm.group(1)
        return ""
    
    def _validate_return_value_format(self, code: str) -> bool:
        """Validate that execute method returns correct format"""
        required_fields = ["success", "stdout", "stderr"]
        # Look for execute method
        if "def execute(self, args: Dict) -> Dict:" not in code and \
           "def execute(self, args: Dict) -> Dict[str, Any]:" not in code:
            return False
        
        # Check for required fields in return statement
        return all(field in code for field in required_fields)
