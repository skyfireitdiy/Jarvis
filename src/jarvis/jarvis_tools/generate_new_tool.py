# -*- coding: utf-8 -*-
import os
from pathlib import Path
from typing import Any
from typing import Dict

from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.output import PrettyOutput


class generate_new_tool:
    name = "generate_new_tool"
    description = "智能生成具备自举和自进化能力的Jarvis新工具。利用CodeAgent根据用户需求分析生成完整的工具代码，包含最佳实践模板、参数验证、错误处理，并自动注册到工具系统。支持调用现有Jarvis生态系统功能（Agent/CodeAgent）实现复杂任务处理，可自我分析和改进工具性能。生成的工具具备完整的生命周期管理，包括可用性检查、参数定义、执行逻辑和自动集成。"

    parameters = {
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "新工具的名称，将用作文件名和工具类名",
            },
            "function_description": {
                "type": "string",
                "description": "工具的功能描述",
            },
        },
        "required": ["tool_name", "function_description"],
    }

    @staticmethod
    def check() -> bool:
        """检查工具是否可用"""
        # 检查数据目录是否存在
        data_dir = get_data_dir()
        tools_dir = Path(data_dir) / "tools"

        # 如果tools目录不存在，尝试创建
        if not tools_dir.exists():
            try:
                tools_dir.mkdir(parents=True, exist_ok=True)
                return True
            except Exception as e:
                PrettyOutput.auto_print(f"❌ 无法创建工具目录 {tools_dir}: {e}")
                return False

        return True

    def _build_enhanced_prompt(
        self, tool_name: str, function_description: str, jarvis_dir: Path
    ) -> str:
        """构建增强的提示词，包含关键参考文件"""

        key_files = [
            jarvis_dir / "jarvis_tools" / "registry.py",
            jarvis_dir / "jarvis_tools" / "base.py",
            jarvis_dir / "jarvis_agent" / "__init__.py",
            jarvis_dir / "jarvis_code_agent" / "code_agent.py",
            jarvis_dir / "jarvis_utils" / "config.py",
            jarvis_dir / "jarvis_utils" / "output.py",
        ]

        files_info = "\n".join([f"- {f.absolute()}" for f in key_files])

        return f"""请根据用户需求生成一个新的Jarvis工具。

工具要求：
- 工具名称：{tool_name}
- 功能描述：{function_description}
- 生成的文件名：{tool_name}.py
- 文件保存路径：{jarvis_dir.parent.parent / "data" / "tools" / f"{tool_name}.py"}
- 必须继承自Tool基类（参考：src/jarvis/jarvis_tools/base.py）
- 必须实现name、description、parameters、execute方法

关键参考文件：
{files_info}

生成的工具必须具备以下特性：
1. 自举能力：能够调用现有package中的Agent和CodeAgent
2. 自我进化：能够利用现有的CodeAgent功能
3. 自动注册：生成后能够立即注册到工具系统
4. 完整功能：包含check()静态方法和execute()实例方法

**强烈推荐使用Agent/CodeAgent**：
- 在execute()方法中应该优先使用CodeAgent处理复杂的代码任务
- 可以使用Agent进行需求分析和任务分解
- 示例代码模式：
  ```python
  from jarvis.jarvis_agent import Agent
  from jarvis.jarvis_code_agent.code_agent import CodeAgent
  
  # 使用CodeAgent处理代码相关任务
  agent = CodeAgent()
  agent.run("你的代码生成需求")
  
  # 或者使用普通Agent处理分析任务
  agent = Agent()
  agent.run("你的分析需求")
  ```

工具模板要求：
```python
class {tool_name}:
    name = "{tool_name}"
    description = "{function_description}"
    
    parameters = {{
        "type": "object",
        "properties": {{
            # 根据功能定义参数
        }},
        "required": ["required_param1", "required_param2"]
    }}
    
    @staticmethod
    def check() -> bool:
        # 检查工具是否可用
        return True
        
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        # 实现工具功能
        # 可以调用：
        # - from jarvis.jarvis_agent import Agent
        # - from jarvis.jarvis_code_agent.code_agent import CodeAgent
        # - 其他jarvis模块
        
        # 自举能力示例：使用generate_new_tool对自身进行改进
        # from jarvis.jarvis_tools.generate_new_tool import generate_new_tool
        # 
        # # 生成改进版本
        # improver = generate_new_tool()
        # result = improver.execute({{
        #     "tool_name": "{tool_name}_improved",
        #     "function_description": "改进版本的{tool_name}，基于使用反馈优化"
        # }})
        
        # 使用CodeAgent进行自我分析和改进
        # agent = CodeAgent()
        # analysis = agent.run("分析当前工具的性能瓶颈并提出改进方案")
        
        pass
```

请生成完整的、可直接使用的Python代码。"""

    def _register_new_tool(self, tool_name: str, tool_file_path: str) -> bool:
        """注册新生成的工具"""
        try:
            from jarvis.jarvis_tools.registry import ToolRegistry

            registry = ToolRegistry()
            return registry.register_tool_by_file(tool_file_path)
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 注册工具失败: {e}")
            return False

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成新工具并注册到当前的工具注册表中

        参数:
            args: 包含工具名称和工具代码的字典

        返回:
            Dict: 包含生成结果的字典
        """
        tool_file_path = None
        curr_dir = os.getcwd()
        try:
            data_dir = get_data_dir()
            tools_dir = Path(data_dir) / "tools"
            tools_dir.mkdir(parents=True, exist_ok=True)
            os.chdir(tools_dir)

            # 从参数中获取工具信息
            tool_name = args["tool_name"]
            function_description = args["function_description"]

            # 验证工具名称
            if not tool_name.isidentifier():
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"工具名称 '{tool_name}' 不是有效的Python标识符",
                }

            jarvis_dir = Path(__file__).parent.parent.resolve()

            # 构建增强的提示词，包含关键参考文件
            enhanced_prompt = self._build_enhanced_prompt(
                tool_name, function_description, jarvis_dir
            )

            # 使用CodeAgent生成工具代码
            from jarvis.jarvis_code_agent.code_agent import CodeAgent
            from jarvis.jarvis_utils.globals import get_global_model_group

            # 使用全局模型组和标准配置创建CodeAgent
            model_group = get_global_model_group()
            agent = CodeAgent(
                model_group=model_group,
                need_summary=True,
                non_interactive=True,
            )

            try:
                # 使用CodeAgent运行并生成工具代码
                # CodeAgent会自动处理代码生成和文件写入
                agent.auto_complete = True
                agent.run(enhanced_prompt)

                # 查找生成的工具文件
                tool_file_path = tools_dir / f"{tool_name}.py"
                if tool_file_path.exists():
                    # 自动注册新工具
                    self._register_new_tool(tool_name, str(tool_file_path))

                    return {
                        "success": True,
                        "stdout": f"成功生成并注册工具：{tool_name}\n文件路径：{tool_file_path}",
                        "stderr": "",
                    }
                else:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "CodeAgent未能生成工具文件",
                    }

            except Exception as e:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"生成工具时出错：{str(e)}",
                }

        finally:
            if curr_dir:
                os.chdir(curr_dir)
