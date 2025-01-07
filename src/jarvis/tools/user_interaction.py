from typing import Dict, Any, List
from ..utils import PrettyOutput, OutputType, get_multiline_input

class UserInteractionTool:
    name = "ask_user"
    description = "Ask user for information, supports option selection and multiline input"
    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Question to ask the user"
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of options for user to choose from",
                "default": []
            },
            "multiline": {
                "type": "boolean",
                "description": "Allow multiline input",
                "default": False
            },
            "description": {
                "type": "string",
                "description": "Additional description or context",
                "default": ""
            }
        },
        "required": ["question"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """获取用户输入"""
        try:
            question = args["question"]
            options = args.get("options", [])
            multiline = args.get("multiline", False)
            description = args.get("description", "")
            
            # 打印问题描述
            if description:
                PrettyOutput.print(description, OutputType.INFO)
            
            # 如果有选项，显示选项列表
            if options:
                PrettyOutput.print("\n可选项:", OutputType.INFO)
                for i, option in enumerate(options, 1):
                    PrettyOutput.print(f"[{i}] {option}", OutputType.INFO)
                
                while True:
                    try:
                        choice = input("\n请选择 (输入数字): ").strip()
                        if not choice:
                            continue
                        
                        choice = int(choice)
                        if 1 <= choice <= len(options):
                            response = options[choice - 1]
                            break
                        else:
                            PrettyOutput.print("无效选择，请重试", OutputType.ERROR)
                    except ValueError:
                        PrettyOutput.print("请输入有效数字", OutputType.ERROR)
            
            # 多行输入
            elif multiline:
                response = get_multiline_input(question)
            
            # 单行输入
            else:
                PrettyOutput.print(question, OutputType.INFO)
                response = input(">>> ").strip()
            
            return {
                "success": True,
                "stdout": response,
                "stderr": ""
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"获取用户输入失败: {str(e)}"
            } 