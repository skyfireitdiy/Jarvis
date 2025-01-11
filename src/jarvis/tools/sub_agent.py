from typing import Dict, Any
from ..agent import Agent
from ..models import BaseModel
from ..utils import PrettyOutput, OutputType
from .base import ToolRegistry

class SubAgentTool:
    name = "create_sub_agent"
    description = """创建一个子代理来处理独立任务。（重要：子代理启动时没有任何上下文！必须提供完整的步骤和上下文。）"""

    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "子代理名称（例如：'文件分析器'）"
            },
            "task": {
                "type": "string",
                "description": "需要明确步骤和目标的任务"
            },
            "context": {
                "type": "string",
                "description": "必填：背景信息、执行步骤和预期结果",
                "default": ""
            }
        },
        "required": ["name", "task", "context"]
    }

    def __init__(self, model: BaseModel):
        """Initialize with the same model as parent agent"""
        self.model = model

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Create and run a sub-agent for the specified task"""
        try:
            name = args["name"]
            task = args["task"]
            context = args.get("context")

            if not context:
                return {
                    "success": False,
                    "error": "必须提供上下文信息，包括完整的背景和执行步骤。"
                }

            PrettyOutput.print(f"正在创建子代理 '{name}'...", OutputType.INFO)
            
            # Create a new tool registry for the sub-agent
            tool_registry = ToolRegistry(self.model)
            
            # Create the sub-agent with the specified name
            sub_agent = Agent(self.model, tool_registry, name=name, is_sub_agent=True)
            
            # Prepare the task with context
            full_task = f"""背景和步骤：
{context}

主要任务：
{task}

要求：
1. 严格按照提供的步骤执行
2. 每完成一个步骤都要报告进度
3. 突出显示任何问题或不明确的点
4. 提供符合预期输出的详细结果"""
            
            PrettyOutput.print(f"子代理 '{name}' 正在执行任务...", OutputType.INFO)
            
            # Execute the task and get the summary
            summary = sub_agent.run(full_task)
            return {
                "success": True,
                "stdout": f"子代理 '{name}' 已完成。\n\n结果：\n{summary}",
                "stderr": ""
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"子代理执行失败：{str(e)}"
            } 