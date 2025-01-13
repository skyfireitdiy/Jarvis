from typing import Dict, Any, Protocol, Optional
from enum import Enum
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from jarvis.agent import Agent
from jarvis.utils import OutputType

class OutputHandler(Protocol):
    def print(self, text: str, output_type: OutputType) -> None: ...

class ModelHandler(Protocol):
    def chat(self, message: str) -> str: ...

class SubAgentTool:
    name = "create_sub_agent"
    description = "创建一个子代理来处理特定任务，子代理会生成任务总结报告"
    parameters = {
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "description": "子代理的名称"
            },
            "task": {
                "type": "string",
                "description": "需要完成的具体任务"
            },
            "context": {
                "type": "string",
                "description": "任务相关的上下文信息",
                "default": ""
            },
            "goal": {
                "type": "string",
                "description": "任务的完成目标",
                "default": ""
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "相关文件路径列表，用于文件问答和处理",
                "default": []
            }
        },
        "required": ["agent_name", "task", "context", "goal"]
    }

    def __init__(self, **kwargs):
        """初始化子代理工具
        
        Args:
            model: 模型处理器
            output_handler: 输出处理器
            register: 工具注册器
        """
        self.model = kwargs.get('model')
        if not self.model:
            raise Exception("Model is required for SubAgentTool")
        self.output = kwargs.get('output_handler')
        self.register = kwargs.get('register')

    def _print(self, text: str, output_type: OutputType = OutputType.INFO):
        """输出信息"""
        if self.output:
            self.output.print(text, output_type)

    def execute(self, args: Dict) -> Dict[str, Any]:
        """创建并运行子代理"""
        try:
            agent_name = args["agent_name"]
            task = args["task"]
            context = args.get("context", "")
            goal = args.get("goal", "")
            files = args.get("files", [])

            self._print(f"创建子代理: {agent_name}")

            # 构建任务描述
            task_description = task
            if context:
                task_description = f"上下文信息:\n{context}\n\n任务:\n{task}"
            if goal:
                task_description += f"\n\n完成目标:\n{goal}"

            # 创建子代理
            sub_agent = Agent(
                name=agent_name,
                model=self.model,
                tool_registry=self.register,
                is_sub_agent=True
            )

            # 运行子代理，传入文件列表
            self._print(f"子代理开始执行任务...")
            result = sub_agent.run(task_description, file_list=files)

            return {
                "success": True,
                "stdout": f"子代理任务完成\n\n{result}",
                "stderr": ""
            }

        except Exception as e:
            self._print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "error": f"子代理执行失败: {str(e)}"
            } 