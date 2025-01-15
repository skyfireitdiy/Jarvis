import os
from typing import Dict, Any
from pathlib import Path
from jarvis.models.registry import PlatformRegistry
from jarvis.tools.registry import ToolRegistry
from jarvis.utils import OutputType, PrettyOutput

class ToolGeneratorTool:
    name = "generate_tool"
    description = "生成新的工具代码并自动注册到Jarvis，自动扩充Jarvis的能力"
    parameters = {
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "工具的名称（snake_case格式）"
            },
            "class_name": {
                "type": "string",
                "description": "工具类的名称（PascalCase格式）"
            },
            "description": {
                "type": "string",
                "description": "工具的功能描述"
            },
            "parameters": {
                "type": "object",
                "description": "工具参数的JSON Schema定义"
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
        platform_name = os.getenv("JARVIS_CODEGEN_PLATFORM") or PlatformRegistry.get_global_platform_name()
        model = PlatformRegistry.create_platform(platform_name)
        model_name = os.getenv("JARVIS_CODEGEN_MODEL")
        if model_name:
            model.set_model_name(model_name)

        prompt = f"""请生成一个Python工具类的代码，要求如下，除了代码，不要输出任何内容：

1. 类名: {class_name}
2. 工具名称: {tool_name}
3. 功能描述: {description}
4. 参数定义: {parameters}

严格按照以下格式生成代码(各函数的参数和返回值一定要与示例一致)：

```python
from typing import Dict, Any, Protocol, Optional
from jarvis.utils import OutputType, PrettyOutput
from jarvis.models.registry import ModelRegistry

class ExampleTool:
    name = "example_tool"
    description = "示例工具"
    parameters = {{
        "type": "object",
        "properties": {{
            "param1": {{"type": "string"}}
        }},
        "required": ["param1"]
    }}

    def __init__(self):
        self.model = ModelRegistry.get_global_model()

    def execute(self, args: Dict) -> Dict[str, Any]:
        try:
            # 验证参数示例
            if "param1" not in args:
                return {{"success": False, "error": "缺少必需参数: param1"}}
            
            # 记录操作示例
            PrettyOutput.print(f"处理参数: {{args['param1']}}", OutputType.INFO)

            # 使用大模型示例
            response = self.model.chat("prompt")
            
            # 实现具体功能
            result = "处理结果"
            
            return {{
                "success": True,
                "stdout": result,
                "stderr": ""
            }}
        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {{
                "success": False,
                "error": str(e)
            }}
```"""

        # 调用模型生成代码
        response = model.chat(prompt)
        model.delete_chat()

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
            success = ToolRegistry.get_global_tool_registry().register_tool_by_file(tool_file)
            if not success:
                return {
                    "success": False,
                    "error": "工具生成成功但注册失败"
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
                "error": f"生成工具失败: {str(e)}"
            }
