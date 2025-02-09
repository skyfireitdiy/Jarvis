import os
from typing import Dict, Any
from pathlib import Path
from jarvis.models.registry import PlatformRegistry
from jarvis.tools.registry import ToolRegistry
from jarvis.utils import OutputType, PrettyOutput

class ToolGeneratorTool:
    name = "generate_tool"
    description = "Generate new tool code and automatically register it to Jarvis, automatically expanding Jarvis's capabilities"
    parameters = {
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "Name of the tool (in snake_case format)"
            },
            "class_name": {
                "type": "string",
                "description": "Name of the tool class (in PascalCase format)"
            },
            "description": {
                "type": "string",
                "description": "Description of the tool's functionality"
            },
            "parameters": {
                "type": "object",
                "description": "JSON Schema definition of tool parameters"
            }
        },
        "required": ["tool_name", "class_name", "description", "parameters"]
    }

    def __init__(self):
        """初始化工具生成器
        """
        # 设置工具目录
        self.tools_dir = Path.home() / '.jarvis_tools'
        
        # 确保工具目录存在
        self.tools_dir.mkdir(parents=True, exist_ok=True)

    def _generate_tool_code(self, tool_name: str, class_name: str, description: str, parameters: Dict) -> str:
        """使用大模型生成工具代码"""
        model = PlatformRegistry.get_global_platform_registry().get_codegen_platform()

        prompt = f"""Please generate the code for a Python tool class, with the following requirements, and do not output any content except the code:

1. Class name: {class_name}
2. Tool name: {tool_name}
3. Function description: {description}
4. Parameter definition: {parameters}

Strictly follow the following format to generate code (the parameters and return values of each function must be consistent with the example):

```python
from typing import Dict, Any, Protocol, Optional
from jarvis.utils import OutputType, PrettyOutput
from jarvis.models.registry import ModelRegistry

class ExampleTool:
    name = "example_tool"
    description = "Example tool"
    parameters = {{
        "type": "object",
        "properties": {{
            "param1": {{"type": "string"}}
        }},
        "required": ["param1"]
    }}

    def __init__(self):
        self.model = ModelRegistry.get_global_platform_registry().get_normal_platform()

    def execute(self, args: Dict) -> Dict[str, Any]:
        try:
            # Validate parameter example
            if "param1" not in args:
                return {{"success": False, "error": "Missing required parameter: param1"}}
            
            # Record operation example
            PrettyOutput.print(f"Processing parameter: {{args['param1']}}", OutputType.INFO)

            # Use large model example
            response = self.model.chat_until_success("prompt")
            
            # Implement specific functionality
            result = "Processing result"
            
            return {{
                "success": True,
                "stdout": result,
                "stderr": ""
            }}
        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {{
                "success": False,
                "stdout": "",
                "stderr": str(e)
            }}
```"""

        # 调用模型生成代码
        response = model.chat_until_success(prompt)

        # 提取代码块
        code_start = response.find("```python")
        code_end = response.find("```", code_start + 9)
        
        if code_start == -1 or code_end == -1:
            # 如果没有找到代码块标记，假设整个响应都是代码
            return response
        
        # 提取代码块内容（去掉```python和```标记）
        code = response[code_start + 9:code_end].strip()
        return code

    def execute(self, args: Dict) -> Dict[str, Any]:
        """生成工具代码"""
        try:
            tool_name = args["tool_name"]
            class_name = args["class_name"]
            description = args["description"]
            parameters = args["parameters"]

            PrettyOutput.print(f"开始生成工具: {tool_name}", OutputType.INFO)

            # 生成工具代码
            tool_code = self._generate_tool_code(
                tool_name,
                class_name,
                description,
                parameters
            )

            # 获取工具文件路径
            tool_file = self.tools_dir / f"{tool_name}.py"

            # 写入工具文件
            with open(tool_file, "w", encoding="utf-8") as f:
                f.write(tool_code)

            # 创建或更新 __init__.py
            init_file = self.tools_dir / "__init__.py"
            if not init_file.exists():
                with open(init_file, "w", encoding="utf-8") as f:
                    f.write("# Jarvis Tools\n")

            # 注册工具
            success = ToolRegistry.get_global_tool_registry().register_tool_by_file(str(tool_file))
            if not success:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "工具生成成功但注册失败"
                }

            return {
                "success": True,
                "stdout": f"工具已生成并注册到Jarvis\n"
                         f"工具目录: {self.tools_dir}\n"
                         f"工具名称: {tool_name}\n"
                         f"工具描述: {description}\n"
                         f"工具参数: {parameters}",
                "stderr": ""
            }

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"生成工具失败: {str(e)}"
            }
