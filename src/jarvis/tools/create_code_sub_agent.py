


from typing import Any, Dict
from jarvis.jarvis_code_agent.code_agent import CodeAgent


class CodeSubAgentTool:
    name = "create_code_sub_agent"
    description = "Create a sub-agent to handle the code modification"
    parameters = {
        "type": "object",
        "properties": {
            "requirement": {
                "type": "string",
                "description": "The requirement of the sub-agent"
            }
        }
    }
    
    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute the sub-agent"""
        requirement = args["requirement"]
        agent = CodeAgent()
        output = agent.run(requirement)
        return {
            "success": True,
            "stdout": output,
            "stderr": ""
        }
