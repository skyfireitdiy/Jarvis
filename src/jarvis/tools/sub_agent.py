from typing import Dict, Any


from jarvis.agent import Agent
from jarvis.utils import OutputType, PrettyOutput


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


    def execute(self, args: Dict) -> Dict[str, Any]:
        """创建并运行子代理"""
        try:
            agent_name = args["agent_name"]
            task = args["task"]
            context = args.get("context", "")
            goal = args.get("goal", "")
            files = args.get("files", [])

            PrettyOutput.print(f"创建子代理: {agent_name}", OutputType.INFO)

            # 构建任务描述
            task_description = task
            if context:
                task_description = f"上下文信息:\n{context}\n\n任务:\n{task}"
            if goal:
                task_description += f"\n\n完成目标:\n{goal}"

            # 创建子代理
            sub_agent = Agent(
                name=agent_name,
                is_sub_agent=True
            )

            # 运行子代理，传入文件列表
            PrettyOutput.print("子代理开始执行任务...", OutputType.INFO)
            result = sub_agent.run(task_description, file_list=files)

            return {
                "success": True,
                "stdout": f"子代理任务完成\n\n{result}",
                "stderr": ""
            }

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "error": f"子代理执行失败: {str(e)}"
            } 