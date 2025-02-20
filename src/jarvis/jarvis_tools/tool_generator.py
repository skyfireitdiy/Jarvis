"""
Tool Generator Tool - Automatically creates new tools using LLM
"""
import json
from pathlib import Path
from typing import Dict, Any
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.utils import PrettyOutput, OutputType

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
        model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
        
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
        return f"""Create a Python tool class that integrates with the Jarvis system. Follow these requirements:
1. Class name: {tool_name.capitalize()}Tool
2. Description: {description}
3. Input specification: {input_spec}
4. Must extend the Tool class from jarvis.jarvis_tools.base
5. Must include these class attributes:
   - name: str (tool identifier)
   - description: str (tool purpose)
   - parameters: dict (JSON schema for inputs)
6. Must implement execute(self, args: Dict) -> Dict method
7. The execute method MUST return a dictionary with these exact fields:
   - success: bool (indicating operation success)
   - stdout: str (primary output/result)
   - stderr: str (error message if any)
8. Must handle errors gracefully
Return ONLY the Python implementation code
The code should be complete and ready to use."""
    
    def _extract_code(self, response: str) -> str:
        """Flexibly extract Python code from LLM response"""
        # Look for code blocks
        lines = response.split("\n")
        code_blocks = []
        in_code_block = False
        
        for line in lines:
            # Check for code block start
            if line.strip().startswith("```python"):
                in_code_block = True
                continue
            # Check for code block end
            if in_code_block and line.strip().startswith("```"):
                break
            # Collect code lines
            if in_code_block:
                code_blocks.append(line)
        
        # If found code block, return it
        if code_blocks:
            return "\n".join(code_blocks)
        
        # If no code block, try to find class definition
        class_lines = []
        found_class = False
        for line in lines:
            if line.strip().startswith("class "):
                found_class = True
            if found_class:
                class_lines.append(line)
                if line.strip().endswith(":"):
                    break
        
        if class_lines:
            # Try to find the rest of the implementation
            for line in lines[lines.index(class_lines[-1]) + 1:]:
                class_lines.append(line)
            return "\n".join(class_lines)
        
        # If all else fails, return the whole response
        return response
    
    def _validate_return_value_format(self, code: str) -> bool:
        """Validate that execute method returns correct format"""
        required_fields = ["success", "stdout", "stderr"]
        # Look for execute method
        if "def execute(self, args: Dict) -> Dict:" not in code and \
           "def execute(self, args: Dict) -> Dict[str, Any]:" not in code:
            return False
        
        # Check for required fields in return statement
        return all(field in code for field in required_fields)
