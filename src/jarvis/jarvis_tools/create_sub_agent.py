from typing import Dict, Any
import os


from jarvis.jarvis_agent import Agent, origin_agent_system_prompt
from jarvis.jarvis_utils.output import OutputType, PrettyOutput



class SubAgentTool:
    name = "create_sub_agent"
    description = "创建子代理以处理特定任务，子代理将生成任务总结报告"
    labels = ['agent', 'automation', 'task']
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
            "root_dir": {
                "type": "string",
                "description": "任务执行的根目录路径（可选）",
                "default": "."
            }
        },
        "required": ["agent_name", "task"]
    }


    def execute(self, args: Dict) -> Dict[str, Any]:
        """Create and run sub-agent"""
        try:
            agent_name = args["agent_name"]
            task = args["task"]
            context = args.get("context", "")
            goal = args.get("goal", "")
            root_dir = args.get("root_dir", ".")

            PrettyOutput.print(f"创建子代理: {agent_name}", OutputType.INFO)

            # Build task description
            task_description = task
            if context:
                task_description = f"Context information:\n{context}\n\nTask:\n{task}"
            if goal:
                task_description += f"\n\nCompletion goal:\n{goal}"


            # Store current directory
            original_dir = os.getcwd()

            try:
                # Change to root_dir
                os.chdir(root_dir)

                # Create sub-agent
                sub_agent = Agent(
                    system_prompt=origin_agent_system_prompt,
                    name=f"Agent({agent_name})",
                )

                # Run sub-agent, pass file list
                PrettyOutput.print("子代理开始执行任务...", OutputType.INFO)
                result = sub_agent.run(task_description)

                return {
                    "success": True,
                    "stdout": f"Sub-agent task completed\n\n{result}",
                    "stderr": ""
                }
            finally:
                # Always restore original directory
                os.chdir(original_dir)

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Sub-agent execution failed: {str(e)}"
            }