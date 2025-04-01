# 导入所需的类型注解模块
from typing import Dict, Any

# 导入多行输入工具和输出工具
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

# 定义AskUserTool类，用于向用户提问
class AskUserTool:
    name="ask_user"
    description="""当完成任务所需的信息缺失或关键决策信息不足时，向用户提问。用户可以输入多行文本，以空行结束。使用场景：1. 需要用户提供更多信息以完成任务；2. 需要用户做出关键决策；3. 需要用户确认重要操作；4. 需要用户提供额外信息"""
    labels=['user', 'interaction', 'input']  # 工具标签
    # 定义参数结构，指定必须包含的问题字段
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
        """执行向用户提问的操作

        Args:
            args: 一个包含问题的字典

        Returns:
            Dict: 一个包含用户响应的字典
        """
        try:
            # 从参数中获取问题
            question = args["question"]

            # 获取agent对象并重置工具调用计数
            agent = args["agent"]
            agent.reset_tool_call_count()

            # 显示问题给用户
            PrettyOutput.print(f"问题: {question}", OutputType.SYSTEM)

            # 获取用户输入
            user_response = get_multiline_input("请输入您的答案 (输入空行结束)")

            # 返回成功响应，包含用户输入的内容
            return {
                "success": True,
                "stdout": user_response,
                "stderr": ""
            }

        except Exception as e:
            # 如果发生异常，返回失败响应，包含错误信息
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to ask user: {str(e)}"
            }