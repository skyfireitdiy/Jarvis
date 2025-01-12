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

    def __init__(self, **kwargs):
        """初始化工具生成器
        
        Args:
            model: 模型处理器 (必需)
            output_handler: 输出处理器 (可选)
            register: 注册器 (必需)
            tools_dir: 工具目录 (可选，默认为 ~/.jarvis_tools)
        """
        self.register = kwargs.get('register')
        if not self.register:
            raise Exception("Register is required for ToolGeneratorTool")
        self.model = kwargs.get('model')
        if not self.model:
            raise Exception("Model is required for ToolGeneratorTool")
        self.output = kwargs.get('output_handler')
        
        # 设置工具目录
        tools_dir = kwargs.get('tools_dir')
        if tools_dir:
            self.tools_dir = Path(tools_dir)
        else:
            self.tools_dir = Path.home() / '.jarvis_tools'
        
        # 确保工具目录存在
        self.tools_dir.mkdir(parents=True, exist_ok=True)

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
                与大模型交互: model.chat(prompt) 
                使用完成后删除会话: model.delete_chat()
            output_handler: 输出处理器 
                输出信息: output_handler.print(text, output_type)
            register: 注册器
                注册工具: register.register_tool_by_file(tool_file)
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
```"""

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
            success = self.register.register_tool_by_file(tool_file)
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
            self._print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "error": f"生成工具失败: {str(e)}"
            }
