# -*- coding: utf-8 -*-
import os
from pathlib import Path
from typing import Any, Dict

from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.output import PrettyOutput


class meta_agent:
    """元代理（Meta-Agent）工具：负责自举和进化 Jarvis 工具生态。

    该工具本身利用 CodeAgent/Agent 分析需求、生成/改进其他工具代码，并自动完成注册与集成，
    是一个可以“创造和改造工具的工具”，体现 Jarvis 的自举和自演化能力。
    """

    name = "meta_agent"
    description = (
        "元代理（Meta-Agent）工具：用于**根据自然语言需求自动创建或改进 Jarvis 工具**，并完成注册集成。"
        "核心能力：1）调用 CodeAgent 生成完整可用的新工具代码（包含参数定义、错误处理、最佳实践模板）；"
        "2）在生成后自动写入到 data/tools 目录并注册到 ToolRegistry；"
        "3）支持在新工具内部编排现有 Agent（通用任务编排、IIRIPER 工作流、task_list_manager）和 CodeAgent（代码修改、构建验证、lint、review 等）；"
        "4）支持通过再次调用 meta_agent 对已有工具进行自举式改进（自我分析和演化）。"
        "调用方式：传入 tool_name（工具名/文件名）与 function_description（目标功能的清晰描述），返回值中包含生成状态和新工具文件的绝对路径。"
    )

    parameters = {
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "要生成或改进的工具名称，将同时用作文件名（<name>.py）和工具类名",
            },
            "function_description": {
                "type": "string",
                "description": "工具的目标功能与使用场景描述：应尽量具体，包含输入参数含义、预期输出、约束条件（例如只读/允许写文件）、是否需要编排 Agent/CodeAgent 等信息",
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

其他文件也可酌情参考。

### Agent / CodeAgent 关键用法（仅列核心要点，详细规则请阅读源码的绝对路径）
- Agent（通用 Agent）：
  - 职责：通用任务编排与对话式工作流，严格遵循 IIRIPER（INTENT → RESEARCH → INNOVATE → PLAN → EXECUTE → REVIEW）。
  - 初始化要点：`Agent(system_prompt=..., name=..., model_group=..., use_tools=[...], non_interactive=...)`，大部分默认行为（记忆、方法论、工具过滤等）在 `{(jarvis_dir / "jarvis_agent" / "__init__.py").absolute()}` 中定义。
  - 典型用法：通过 `agent.run(user_input)` 启动完整闭环，内部会自动处理系统提示、工具调用、task_list_manager 调度和总结；总结与返回值行为由 `summary_prompt` 和 `need_summary` 控制。
  - 更多细节（参数含义、总结与返回值策略、事件回调等）请直接阅读：`{(jarvis_dir / "jarvis_agent" / "__init__.py").absolute()}`。
- CodeAgent（代码 Agent）：
  - 职责：代码分析与修改、git 操作、构建验证、lint、diff 展示和自动 review。
  - 初始化要点：`CodeAgent(model_group=..., need_summary=..., non_interactive=True/False, append_tools=..., rule_names=...)`，工作流和提示词在 `{(jarvis_dir / "jarvis_code_agent" / "code_agent.py").absolute()}` 与 `{(jarvis_dir / "jarvis_code_agent" / "code_agent_prompts.py").absolute()}` 中定义。
  - 典型用法：通过 `agent.run(requirement, prefix=..., suffix=...)` 驱动代码修改流程；内部会自动处理上下文分析、补丁生成、git 提交、构建校验、lint 与 review，`run` 的返回值通常是“结果摘要字符串或 None”。
  - 更多细节（review 流程、任务总结、返回值语义等）请直接阅读：`{(jarvis_dir / "jarvis_code_agent" / "code_agent.py").absolute()}` 与 `{(jarvis_dir / "jarvis_code_agent" / "code_agent_prompts.py").absolute()}`。

在本工具生成的新工具中，推荐：
- 使用 Agent 负责上层的需求分析、IIRIPER 工作流以及多步骤任务编排；
- 使用 CodeAgent 负责具体代码层面的修改、重构和验证。

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
        
        # 自举能力示例：使用 meta_agent 对自身进行改进
        # from jarvis.jarvis_tools.meta_agent import meta_agent
        # 
        # # 生成改进版本
        # improver = meta_agent()
        # result = improver.execute({{
        #     "tool_name": "{tool_name}_improved",
        #     "function_description": "改进版本的{tool_name}，基于使用反馈优化"
        # }})
        
        # 使用CodeAgent进行自我分析和改进
        # agent = CodeAgent()
        # analysis = agent.run("分析当前工具的性能瓶颈并提出改进方案")
        
        pass
```

请生成完整的、可直接使用的Python代码，生成完成后不用进行测试与验证。"""

    def _register_new_tool(
        self, agent: Any, tool_name: str, tool_file_path: str
    ) -> bool:
        """注册新生成的工具"""
        try:
            tool_registry = agent.get_tool_registry()
            result = tool_registry.register_tool_by_file(tool_file_path)
            if not result:
                # 注册失败，清理生成的文件
                try:
                    from pathlib import Path

                    Path(tool_file_path).unlink(missing_ok=True)
                    PrettyOutput.auto_print(
                        f"ℹ️ 已清理注册失败的工具文件: {tool_file_path}"
                    )
                except Exception as cleanup_error:
                    PrettyOutput.auto_print(f"⚠️ 清理文件失败: {cleanup_error}")
            return bool(result)
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 注册工具失败: {e}")
            # 注册异常时也尝试清理文件
            try:
                from pathlib import Path

                Path(tool_file_path).unlink(missing_ok=True)
                PrettyOutput.auto_print(f"ℹ️ 已清理注册异常的工具文件: {tool_file_path}")
            except Exception as cleanup_error:
                PrettyOutput.auto_print(f"⚠️ 清理文件失败: {cleanup_error}")
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
                    self._register_new_tool(agent, tool_name, str(tool_file_path))

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
