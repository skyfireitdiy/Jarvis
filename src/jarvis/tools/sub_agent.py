from typing import Dict, Any
from ..agent import Agent
from ..models import BaseModel
from ..utils import PrettyOutput, OutputType
from .base import ToolRegistry

class SubAgentTool:
    name = "create_sub_agent"
    description = """Create a sub-agent to handle independent tasks.
    
IMPORTANT: Sub-agents start with NO context!
Must provide complete steps and context.

Required:
1. Context
   - Project background
   - File locations
   - Current standards
   - Requirements

2. Steps
   - Clear actions
   - Success criteria
   - Expected output

Example (Good):
<START_TOOL_CALL>
name: create_sub_agent
arguments:
    name: CodeAnalyzer
    task: Analyze error handling
    context: |
        Project: Python 3.8+
        File: src/utils.py
        
        Steps:
        1. Read file content
        2. Find error patterns
        3. Check consistency
        4. Verify logging
        
        Expected:
        - Pattern list
        - Issues found
        - Suggestions
        
        Standards:
        - Dict[str, Any] returns
        - PrettyOutput logging
<END_TOOL_CALL>

Example (Bad):
<START_TOOL_CALL>
name: create_sub_agent
arguments:
    name: Analyzer
    task: Check code
    context: Look at utils.py
<END_TOOL_CALL>

Use for:
✓ Clear, independent tasks
✓ Well-defined goals
✗ Vague tasks
✗ Simple operations"""

    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Sub-agent name (e.g., 'FileAnalyzer')"
            },
            "task": {
                "type": "string",
                "description": "Task with clear steps and goals"
            },
            "context": {
                "type": "string",
                "description": "REQUIRED: Background, steps, and expected results",
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
                    "error": "Context is required. Please provide complete background and steps."
                }

            PrettyOutput.print(f"Creating sub-agent '{name}'...", OutputType.INFO)
            
            # Create a new tool registry for the sub-agent
            tool_registry = ToolRegistry(self.model)
            
            # Create the sub-agent with the specified name
            sub_agent = Agent(self.model, tool_registry, name=name)
            
            # Prepare the task with context
            full_task = f"""Background and Steps:
{context}

Primary Task:
{task}

Requirements:
1. Follow the provided steps exactly
2. Report progress after each step
3. Highlight any issues or unclear points
4. Provide detailed results matching expected output"""
            
            PrettyOutput.print(f"Sub-agent '{name}' executing task...", OutputType.INFO)
            
         
            # Execute the task and get the summary
            summary = sub_agent.run(full_task)
            return {
                "success": True,
                "stdout": f"Sub-agent '{name}' completed.\n\nResults:\n{summary}",
                "stderr": ""
            }


        except Exception as e:
            return {
                "success": False,
                "error": f"Sub-agent failed: {str(e)}"
            } 