"""
Tool Generator Tool - Automatically creates new tools using LLM
"""
from pathlib import Path
import re
from typing import Dict, Any
from jarvis.jarvis_platform.registry import PlatformRegistry

class ToolGenerator:
    name = "tool_generator"
    description = "使用LLM自动生成与系统集成的新工具"
    parameters = {
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "新工具的名称"
            },
            "description": {
                "type": "string", 
                "description": "工具用途描述"
            },
            "input_spec": {
                "type": "string",
                "description": "所需输入和功能的规范说明"
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
        """创建用于工具生成的LLM提示"""
        example_code = '''
<TOOL>
from typing import Dict, Any
from jarvis.utils import OutputType, PrettyOutput
from jarvis.jarvis_platform.registry import PlatformRegistry

class CustomTool:
    name = "工具名称"              # 调用时使用的工具名称
    description = "工具描述"       # 工具用途
    parameters = {                # 参数JSON Schema
        "type": "object",
        "properties": {
            "param1": {
                "type": "string",
                "description": "参数描述"
            }
        },
        "required": ["param1"]
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具功能
        
        Args:
            args: 传递给工具的参数
            
        Returns:
            {
                "success": bool,
                "stdout": str,
                "stderr": str,
            }
        """
        try:
            # 在此实现工具逻辑
            # 使用LLM
            # model = PlatformRegistry.get_global_platform_registry().get_codegen_platform() 
            # result = model.chat_until_success(prompt)

            result = "工具执行结果"
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

        return f'''创建一个与Jarvis系统集成的Python工具类。请遵循以下要求：
1. 类名: {tool_name.capitalize()}Tool
2. 描述: {description}
3. 输入规范: {input_spec}
4. 必须包含以下类属性：
   - name: str (工具标识符)
   - description: str (工具用途)
   - parameters: dict (输入的JSON schema)
5. 必须实现 execute(self, args: Dict) -> Dict 方法
6. execute方法必须返回包含以下字段的字典：
   - success: bool (指示操作是否成功)
   - stdout: str (主要输出/结果)
   - stderr: str (错误信息，如果有)
7. 必须优雅地处理错误
8. 仅返回Python实现代码
9. 代码应该是完整且可直接使用的
10. 按照以下格式输出代码：
<TOOL>
{example_code}
</TOOL>

示例：
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