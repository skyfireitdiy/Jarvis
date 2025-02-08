from typing import Dict, Any


from jarvis.agent import Agent
from jarvis.utils import OutputType, PrettyOutput


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

            PrettyOutput.print(f"Create sub-agent: {agent_name}", OutputType.INFO)

            # Build task description
            task_description = task
            if context:
                task_description = f"Context information:\n{context}\n\nTask:\n{task}"
            if goal:
                task_description += f"\n\nCompletion goal:\n{goal}"

            system_prompt = f"""You are {agent_name}, an AI assistant with powerful problem-solving capabilities.

When users need to execute tasks, you will strictly follow these steps to handle problems:
1. Problem Restatement: Confirm understanding of the problem
2. Root Cause Analysis (only if needed for problem analysis tasks)
3. Set Objectives: Define achievable and verifiable goals
4. Generate Solutions: Create one or more actionable solutions
5. Evaluate Solutions: Select the optimal solution from multiple options
6. Create Action Plan: Based on available tools, create an action plan using PlantUML format for clear execution flow
7. Execute Action Plan: Execute one step at a time, **use at most one tool** (wait for tool execution results before proceeding)
8. Monitor and Adjust: If execution results don't match expectations, reflect and adjust the action plan, iterate previous steps
9. Methodology: If the current task has general applicability and valuable experience is gained, use methodology tools to record it for future similar problems
10. Task Completion: End the task using task completion command when finished

Methodology Template:
1. Problem Restatement
2. Optimal Solution
3. Optimal Solution Steps (exclude failed actions)
                                          
Strict Rules:
- Execute only one tool at a time
- Tool execution must strictly follow the tool usage format
- Wait for user to provide execution results
- Don't assume or imagine results
- Don't create fake dialogues
- If current information is insufficient, you may ask the user
- Not all problem-solving steps are mandatory, skip as appropriate
- Ask user before executing tools that might damage system or user's codebase
- Request user guidance when multiple iterations show no progress
- If yaml string contains colons, wrap the entire string in quotes to avoid yaml parsing errors
- Use | syntax for multi-line strings in yaml

-------------------------------------------------------------"""

            # Create sub-agent
            sub_agent = Agent(
                system_prompt=system_prompt,
                name=agent_name,
                is_sub_agent=True
            )

            # Run sub-agent, pass file list
            PrettyOutput.print("Sub-agent starts executing task...", OutputType.INFO)
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
                "error": f"Sub-agent execution failed: {str(e)}"
            } 