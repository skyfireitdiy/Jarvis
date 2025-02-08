from typing import Dict, Any
from jarvis.tools.base import Tool
from jarvis.utils import get_multiline_input, PrettyOutput, OutputType

class AskUserTool:
    name="ask_user"
    description="""Ask the user when information needed to complete the task is missing or when critical decision information is lacking. Users can input multiple lines of text, ending with an empty line. Use cases: 1. Need user to provide more information to complete the task; 2. Need user to make critical decisions; 3. Need user to confirm important operations; 4. Need user to provide additional information"""
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to ask the user"
            }
        },
        "required": ["question"]
    }
        

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行询问用户操作
        
        Args:
            args: 包含问题的字典
            
        Returns:
            Dict: 包含用户响应的字典
        """
        try:
            question = args["question"]
            
            # 显示问题
            PrettyOutput.print("\n问题:", OutputType.SYSTEM)
            PrettyOutput.print(question, OutputType.SYSTEM)
            
            # 获取用户输入
            user_response = get_multiline_input("Please enter your answer (input empty line to end)")
            
            if user_response == "__interrupt__":
                return {
                    "success": False,
                    "error": "User canceled input"
                }
            
            return {
                "success": True,
                "stdout": user_response
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to ask user: {str(e)}"
            } 