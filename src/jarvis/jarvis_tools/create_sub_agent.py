from typing import Dict, Any


from jarvis.jarvis_agent import Agent, origin_agent_system_prompt
from jarvis.jarvis_utils.output import OutputType, PrettyOutput



class SubAgentTool:
    name = "create_sub_agent"
    description = "创建子代理以处理特定任务，子代理将生成任务总结报告"
    parameters = {
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "description": "子代理名称"
            },
            "task": {
                "type": "string",
                "description": "要完成的特定任务"
            },
            "context": {
                "type": "string",
                "description": "与任务相关的上下文信息",
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
        """Create and run sub-agent"""
        try:
            agent_name = args["agent_name"]
            task = args["task"]
            context = args.get("context", "")
            goal = args.get("goal", "")
            files = args.get("files", [])

            PrettyOutput.print(f"创建子代理: {agent_name}", OutputType.INFO)

            # Build task description
            task_description = task
            if context:
                task_description = f"Context information:\n{context}\n\nTask:\n{task}"
            if goal:
                task_description += f"\n\nCompletion goal:\n{goal}"


            # Create sub-agent
            sub_agent = Agent(
                system_prompt=origin_agent_system_prompt,
                name=f"Agent({agent_name})",
                is_sub_agent=True
            )

            # Run sub-agent, pass file list
            PrettyOutput.print("子代理开始执行任务...", OutputType.INFO)
            result = sub_agent.run(task_description, file_list=files)

            return {
                "success": True,
                "stdout": f"Sub-agent task completed\n\n{result}",
                "stderr": ""
            }

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Sub-agent execution failed: {str(e)}"
            }