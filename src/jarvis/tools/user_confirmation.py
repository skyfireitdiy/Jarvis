from typing import Dict, Any
from ..utils import PrettyOutput, OutputType

class UserConfirmationTool:
    name = "ask_user_confirmation"
    description = "Request confirmation from user, returns yes/no"
    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Question to ask for confirmation"
            },
            "details": {
                "type": "string",
                "description": "Additional details or context",
                "default": ""
            }
        },
        "required": ["question"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """获取用户确认"""
        try:
            question = args["question"]
            details = args.get("details", "")
            
            # 打印详细信息
            if details:
                PrettyOutput.print(details, OutputType.INFO)
                PrettyOutput.print("", OutputType.INFO)  # 空行
            
            # 打印问题
            PrettyOutput.print(f"{question} (y/n)", OutputType.INFO)
            
            while True:
                response = input(">>> ").strip().lower()
                if response in ['y', 'yes']:
                    result = True
                    break
                elif response in ['n', 'no']:
                    result = False
                    break
                else:
                    PrettyOutput.print("请输入 y/yes 或 n/no", OutputType.ERROR)
            
            return {
                "success": True,
                "stdout": str(result),
                "stderr": ""
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"获取用户确认失败: {str(e)}"
            } 