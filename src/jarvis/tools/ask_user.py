from typing import Dict, Any
from jarvis.tools.base import Tool
from jarvis.utils import get_multiline_input, PrettyOutput, OutputType

class AskUserTool:
    name="ask_user"
    description="""当缺少完成任务的信息或有关键决策信息缺失时，询问用户。用户可以输入多行文本，空行结束输入。使用场景：1. 需要用户提供更多信息来完成任务；2. 需要用户做出关键决策；3. 需要用户确认某些重要操作；4. 需要用户提供额外信息"""
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "要询问用户的问题"
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
            PrettyOutput.print("\n请输入您的回答（输入空行结束）:", OutputType.INPUT)
            user_response = get_multiline_input()
            
            if user_response == "__interrupt__":
                return {
                    "success": False,
                    "error": "用户取消了输入"
                }
            
            return {
                "success": True,
                "stdout": user_response
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"询问用户失败: {str(e)}"
            } 