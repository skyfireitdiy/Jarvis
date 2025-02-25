from typing import Dict, Any


from jarvis.jarvis_agent import Agent, origin_agent_system_prompt
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils import OutputType, PrettyOutput


class SubAgentTool:
    name = "create_sub_agent"
    description = "Create a sub-agent to handle specific tasks, the sub-agent will generate a task summary report"
    parameters = {
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "description": "Sub-agent name"
            },
            "task": {
                "type": "string",
                "description": "Specific task to complete"
            },
            "context": {
                "type": "string",
                "description": "Context information related to the task",
                "default": ""
            },
            "goal": {
                "type": "string",
                "description": "Completion goal of the task",
                "default": ""
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Related file path list, used for file question answering and processing",
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