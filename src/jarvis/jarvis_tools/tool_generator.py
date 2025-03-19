"""
Tool Generator Tool - Automatically creates new tools using LLM
"""
from pathlib import Path
import re
from typing import Dict, Any

from yaspin import yaspin
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.utils import create_close_tag, create_open_tag

class ToolGenerator:
    """工具生成器类，用于自动创建与Jarvis系统集成的新工具"""
    
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
        """
        执行工具生成过程
        Args:
            arguments: 包含工具生成所需参数的字典
        Returns:
            包含执行结果的字典，包含success、stdout和stderr字段
        """
        # 获取代码生成平台实例
        model = PlatformRegistry.get_global_platform_registry().get_codegen_platform()
        
        try:
            tool_name = arguments["tool_name"]
            description = arguments["description"]
            input_spec = arguments["input_spec"]
            
            # 使用LLM生成工具实现代码
            with yaspin(text="正在生成工具...", color="cyan") as spinner:
                prompt = self._create_prompt(tool_name, description, input_spec)
                llm_response = model.chat_until_success(prompt)
                spinner.text = "工具生成完成"
                spinner.ok("✅")
            
            # 从LLM响应中提取实现代码
            with yaspin(text="正在提取工具实现...", color="cyan") as spinner:
                implementation = self._extract_code(llm_response)
                if not implementation:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "无法从LLM响应中提取有效的Python代码"
                    }
                spinner.text = "工具实现提取完成"
                spinner.ok("✅")
            
            # 验证生成的工具代码是否符合返回值格式要求
            with yaspin(text="正在验证工具返回值格式...", color="cyan") as spinner:
                if not self._validate_return_value_format(implementation):
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "生成的工具不符合要求的返回值格式"
                    }
                spinner.text = "工具返回值格式验证完成"
                spinner.ok("✅")
            
            # 保存生成的新工具
            with yaspin(text="正在保存工具...", color="cyan") as spinner:
                tools_dir = Path.home() / ".jarvis" / "tools"
                tools_dir.mkdir(parents=True, exist_ok=True)
                tool_file = tools_dir / f"{tool_name}.py"
                
                with open(tool_file, "w", errors="ignore") as f:
                    f.write(implementation)
                spinner.text = "工具保存完成"
                spinner.ok("✅")
            
            return {
                "success": True,
                "stdout": f"工具成功生成于: {tool_file}",
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"工具生成失败: {str(e)}"
            }
    
    def _create_prompt(self, tool_name: str, description: str, input_spec: str) -> str:
        """
        创建用于工具生成的LLM提示
        Args:
            tool_name: 工具名称
            description: 工具描述
            input_spec: 输入规范
        Returns:
            格式化后的提示字符串
        """
        example_code = f'''
{create_open_tag("TOOL")}
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
{create_close_tag("TOOL")}
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
{create_open_tag("TOOL")}
{example_code}
{create_close_tag("TOOL")}

示例：
{example_code}
'''
    
    def _extract_code(self, response: str) -> str:
        """
        从LLM响应中提取Python代码
        Args:
            response: LLM的响应字符串
        Returns:
            提取到的Python代码字符串
        """
        sm = re.search(create_open_tag("TOOL")+r'(.*?)'+create_close_tag("TOOL"), response, re.DOTALL)
        if sm:
            return sm.group(1)
        return ""
    
    def _validate_return_value_format(self, code: str) -> bool:
        """
        验证execute方法的返回值格式是否正确
        Args:
            code: 要验证的代码字符串
        Returns:
            布尔值，表示格式是否正确
        """
        required_fields = ["success", "stdout", "stderr"]
        # 检查execute方法是否存在
        if "def execute(self, args: Dict) -> Dict:" not in code and \
           "def execute(self, args: Dict) -> Dict[str, Any]:" not in code:
            return False
        
        # 检查返回值中是否包含所有必需字段
        return all(field in code for field in required_fields)
