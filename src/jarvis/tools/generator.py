from typing import Dict, Any, Protocol, Optional
import os
from pathlib import Path
from enum import Enum

class OutputType(Enum):
    INFO = "info"
    ERROR = "error"

class OutputHandler(Protocol):
    def print(self, text: str, output_type: OutputType) -> None: ...

class ModelHandler(Protocol):
    def chat(self, message: str) -> str: ...

class ToolGeneratorTool:
    name = "generate_tool"
    description = "生成新的工具代码并自动注册到ToolRegistry"
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

    def __init__(self, **kwargs):
        """初始化工具生成器
        
        Args:
            model: 模型处理器 (必需)
            output_handler: 输出处理器 (可选)
        """
        self.register = kwargs.get('register')
        if not self.register:
            raise Exception("Register is required for ToolGeneratorTool")
        self.model = kwargs.get('model')
        if not self.model:
            raise Exception("Model is required for ToolGeneratorTool")
        self.output = kwargs.get('output_handler')
        
    def _print(self, text: str, output_type: OutputType = OutputType.INFO):
        """输出信息"""
        if self.output:
            self.output.print(text, output_type)

    def _generate_tool_code(self, tool_name: str, class_name: str, description: str, parameters: Dict) -> str:
        """使用大模型生成工具代码"""
        if not self.model:
            raise Exception("Model not initialized")

        prompt = f"""请生成一个Python工具类的代码，要求如下：

1. 类名: {class_name}
2. 工具名称: {tool_name}
3. 功能描述: {description}
4. 参数定义: {parameters}

严格按照以下格式生成代码(各函数的参数和返回值一定要与示例一致)：

```python
from typing import Dict, Any, Protocol, Optional
from enum import Enum

class OutputType(Enum):
    INFO = "info"
    ERROR = "error"

class OutputHandler(Protocol):
    def print(self, text: str, output_type: OutputType) -> None: ...

class ModelHandler(Protocol):
    def chat(self, message: str) -> str: ...

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

    def __init__(self, **kwargs):
        '''初始化工具
        Args:
            model: 模型处理器 
            output_handler: 输出处理器 
            register: 注册器
        '''
        self.model = kwargs.get('model')
        self.output = kwargs.get('output_handler')
        self.register = kwargs.get('register')
        
    def _print(self, text: str, output_type: OutputType = OutputType.INFO):
        if self.output:
            self.output.print(text, output_type)

    def execute(self, args: Dict) -> Dict[str, Any]:
        try:
            # 验证参数
            if "param1" not in args:
                return {{"success": False, "error": "缺少必需参数: param1"}}
            
            # 记录操作
            self._print(f"处理参数: {{args['param1']}}")
            
            # 实现具体功能
            result = "处理结果"
            
            return {{
                "success": True,
                "stdout": result,
                "stderr": ""
            }}
        except Exception as e:
            self._print(str(e), OutputType.ERROR)
            return {{
                "success": False,
                "error": str(e)
            }}
```

请根据以上要求生成完整的工具代码："""

        # 调用模型生成代码
        response = self.model.chat(prompt)
        self.model.delete_chat()

        # 提取代码块
        code_start = response.find("```python")
        code_end = response.rfind("```")
        
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

            self._print(f"开始生成工具: {tool_name}")

            # 生成工具代码
            tool_code = self._generate_tool_code(
                tool_name,
                class_name,
                description,
                parameters
            )

            # 获取工具目录路径
            tools_dir = Path(__file__).parent
            tool_file = tools_dir / f"{tool_name}.py"

            # 写入工具文件
            with open(tool_file, "w", encoding="utf-8") as f:
                f.write(tool_code)

            self.register.register_tool_by_file(tool_file)

            return {
                "success": True,
                "stdout": f"工具已生成,并已经注册到Jarvis, 在后面的对话中可直接调用此工具。工具信息为:\n工具名称: {tool_name}\n工具描述: {description}\n工具参数: {parameters}",
                "stderr": ""
            }

        except Exception as e:
            self._print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "error": f"生成工具失败: {str(e)}"
            }
