from typing import Dict, Any

from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

class AskUserTool:
    name="ask_user"
    description="""当完成任务所需的信息缺失或关键决策信息不足时，向用户提问。用户可以输入多行文本，以空行结束。使用场景：1. 需要用户提供更多信息以完成任务；2. 需要用户做出关键决策；3. 需要用户确认重要操作；4. 需要用户提供额外信息"""
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "要向用户提出的问题"
            }
        },
        "required": ["question"]
    }
        

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the operation of asking the user
        
        Args:
            args: A dictionary containing the question
            
        Returns:
            Dict: A dictionary containing the user's response
        """
        try:
            question = args["question"]
            
            # Display the question
            PrettyOutput.print(f"问题: {question}", OutputType.SYSTEM)
            
            # Get user input
            user_response = get_multiline_input("请输入您的答案 (输入空行结束)")
            
            return {
                "success": True,
                "stdout": user_response,
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to ask user: {str(e)}"
            } 