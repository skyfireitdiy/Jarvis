from typing import Dict, Any
from jarvis.utils import OutputType, PrettyOutput, load_env_from_file
from jarvis.models.registry import PlatformRegistry

class ThinkerTool:
    name = "thinker"
    description = "使用思维链推理方式分析复杂问题，适用于需要多步推理、逻辑分析或创造性思考的场景"
    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "需要分析的问题或任务"
            },
            "context": {
                "type": "string",
                "description": "问题相关的上下文信息或背景知识",
                "default": ""
            },
            "goal": {
                "type": "string",
                "description": "期望达成的具体目标或结果",
                "default": ""
            }
        },
        "required": ["question"]
    }

    def __init__(self):
        """初始化思考工具"""
        self.model = PlatformRegistry.get_global_platform_registry().get_thinking_platform()

    def _generate_prompt(self, question: str, context: str, goal: str) -> str:
        """生成提示词
        
        Args:
            question: 问题
            context: 上下文
            goal: 期望目标
            
        Returns:
            str: 完整的提示词
        """
        # 基础提示词
        prompt = """你是一个擅长深度思考和逻辑推理的助手。请帮助分析问题并给出解决方案。

请按以下方式思考：
1. 仔细理解问题和目标
2. 进行系统性分析和推理
3. 考虑多个可能的解决方案
4. 给出最佳建议和具体行动步骤

问题：
{question}
"""
        # 如果有目标，添加到提示词中
        if goal:
            prompt += f"""
期望目标：
{goal}
"""

        # 如果有上下文，添加到提示词中
        if context:
            prompt += f"""
相关上下文：
{context}
"""

        prompt += "\n请开始分析："
        return prompt

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行思考分析
        
        Args:
            args: 包含参数的字典
                - question: 问题
                - context: 上下文（可选）
                - goal: 期望目标（可选）
                
        Returns:
            Dict[str, Any]: 执行结果
        """
        try:
            # 获取参数
            question = args["question"]
            context = args.get("context", "")
            goal = args.get("goal", "")
            
            # 生成提示词
            prompt = self._generate_prompt(question, context, goal)
            
            # 记录开始分析
            PrettyOutput.print(f"开始分析问题: {question}", OutputType.INFO)
            if context:
                PrettyOutput.print("包含上下文信息", OutputType.INFO)
            if goal:
                PrettyOutput.print(f"目标: {goal}", OutputType.INFO)
            
            # 调用模型进行分析
            response = self.model.chat(prompt)
            
            if not response:
                return {
                    "success": False,
                    "error": "未能获得有效的分析结果"
                }
                
            return {
                "success": True,
                "stdout": response,
                "stderr": ""
            }
            
        except Exception as e:
            PrettyOutput.print(f"思考分析失败: {str(e)}", OutputType.ERROR)
            return {
                "success": False,
                "error": f"执行失败: {str(e)}"
            }

def main():
    """命令行直接运行工具"""
    import argparse

    load_env_from_file()
    
    parser = argparse.ArgumentParser(description='深度思考分析工具')
    parser.add_argument('--question', required=True, help='需要分析的问题')
    parser.add_argument('--context', help='问题相关的上下文信息')
    parser.add_argument('--goal', help='期望达成的具体目标或结果')
    args = parser.parse_args()
    
    tool = ThinkerTool()
    result = tool.execute({
        "question": args.question,
        "context": args.context,
        "goal": args.goal
    })
    
    if result["success"]:
        PrettyOutput.print("\n分析结果:", OutputType.INFO)
        PrettyOutput.print(result["stdout"], OutputType.INFO)
    else:
        PrettyOutput.print(result["error"], OutputType.ERROR)

if __name__ == "__main__":
    main() 