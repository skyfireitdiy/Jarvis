from typing import Dict, Any
from ..agent import Agent
from ..models import BaseModel
from ..utils import PrettyOutput, OutputType
from .base import ToolRegistry

class SubAgentTool:
    name = "create_sub_agent"
    description = """Create a sub-agent to handle independent tasks.
    
Use this tool when:
1. A subtask can be executed independently
2. The task requires separate context management
3. To optimize token usage of the main agent
4. For parallel task processing

The sub-agent will:
1. Inherit all tools from the parent agent
2. Maintain its own conversation history
3. Return a comprehensive task summary
"""
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name for the sub-agent (e.g., 'FileAnalyzer', 'CodeReviewer')"
            },
            "task": {
                "type": "string",
                "description": "Task description with complete context"
            },
            "context": {
                "type": "string",
                "description": "Additional context or background information",
                "default": ""
            }
        },
        "required": ["name", "task"]
    }

    def __init__(self, model: BaseModel):
        """Initialize with the same model as parent agent"""
        self.model = model

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Create and run a sub-agent for the specified task"""
        try:
            name = args["name"]
            task = args["task"]
            context = args.get("context", "")

            PrettyOutput.print(f"Creating sub-agent '{name}'...", OutputType.INFO)
            
            # Create a new tool registry for the sub-agent
            tool_registry = ToolRegistry()
            
            # Create the sub-agent with the specified name
            sub_agent = Agent(self.model, tool_registry, name=name)
            
            # Prepare the task with context if provided
            full_task = f"{context}\n\nTask: {task}" if context else task
            
            PrettyOutput.print(f"Sub-agent '{name}' executing task...", OutputType.INFO)
            
            # Execute the task and get the summary
            summary = sub_agent.run(full_task)
            
            return {
                "success": True,
                "stdout": f"Sub-agent '{name}' completed the task.\n\nSummary:\n{summary}",
                "stderr": ""
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Sub-agent execution failed: {str(e)}"
            } 