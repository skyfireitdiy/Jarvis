from typing import Dict, Any
from ..utils import PrettyOutput, OutputType, get_multiline_input

class UserInputTool:
    name = "ask_user"
    description = """Ask user for information or confirmation.

Use this tool when you need:
1. Additional information
2. Confirmation before critical actions
3. User preferences or choices"""

    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Clear question for the user"
            },
            "options": {
                "type": "string",
                "description": "Optional: Numbered list of choices",
                "default": ""
            },
            "context": {
                "type": "string",
                "description": "Optional: Additional context to help user understand",
                "default": ""
            }
        },
        "required": ["question"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """向用户询问信息并返回响应"""
        try:
            question = args["question"]
            options = args.get("options", "")
            context = args.get("context", "")

            # 显示问题
            PrettyOutput.section("用户确认", OutputType.USER)
            
            # 显示上下文（如果有）
            if context:
                PrettyOutput.print(f"背景: {context}", OutputType.INFO)
            
            # 显示问题
            PrettyOutput.print(f"问题: {question}", OutputType.USER)
            
            # 显示选项（如果有）
            if options:
                PrettyOutput.print("\n选项:\n" + options, OutputType.INFO)

            # 获取用户输入
            response = get_multiline_input("请输入您的回答:")
            
            if response == "__interrupt__":
                return {
                    "success": False,
                    "error": "User cancelled the input"
                }

            return {
                "success": True,
                "stdout": response,
                "stderr": ""
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get user input: {str(e)}"
            } 