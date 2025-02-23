from typing import Dict, Any, List, Callable
from jarvis.agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_dev.team_role import TeamRole
from jarvis.jarvis_dev.message import Message

class ProductManager(TeamRole):
    """Product Manager role for requirement analysis"""
    
    def __init__(self, message_handler: Callable[[Message], Dict[str, Any]]):
        """Initialize Product Manager agent"""
        system_prompt = """You are an AI Product Manager agent focused on:

1. Task Understanding
- Analyze user requirements
- Break down into clear tasks
- Identify completion criteria
- Track progress

2. Team Coordination
- Direct agents to needed tasks
- Remove blockers
- Share relevant context
- Ensure task completion

Remember:
- Focus on completing user requirements
- Skip unnecessary processes
- Direct communication with agents
- Ask user when unclear
"""
        super().__init__("ProductManager", system_prompt, message_handler)
        
    def _get_platform(self):
        return PlatformRegistry().get_thinking_platform()
        
    def _get_tools(self):
        tools = ToolRegistry()
        tools.use_tools([
            # 基础工具
            "ask_user",
            "execute_shell",
            # PM工具
            "read_code",
            "ask_codebase",
            "search",
            "read_webpage",
            "rag",
            "file_operation"
        ])
        return tools

    def complete_requirement(self, requirement: str) -> Dict[str, Any]:
        """Analyze development requirement"""
        try:
            # Create analysis prompt
            prompt = f"""Please analyze this development requirement:

{requirement}

Start by:
1. Understanding the requirements
2. Breaking down into tasks
3. Consulting BA for business analysis
4. Checking with TL for technical feasibility
5. Planning the development process

Remember to:
- Ask user for any unclear points
- Record key decisions
- Keep team informed
"""
            # Get analysis result
            result = self.agent.run(prompt)
            
            # Extract YAML content between tags
            import re
            import yaml
            
            yaml_match = re.search(r'<ANALYSIS>\s*(.*?)\s*</ANALYSIS>', result, re.DOTALL)
            if yaml_match:
                yaml_content = yaml_match.group(1)
                try:
                    analysis = yaml.safe_load(yaml_content)
                    tasks = analysis.get("tasks", [])
                except:
                    tasks = []
            else:
                tasks = []
            
            return {
                "success": True,
                "analysis": result,
                "tasks": tasks
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Requirement analysis failed: {str(e)}"
            }
