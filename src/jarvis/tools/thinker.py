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
            "approach": {
                "type": "string",
                "enum": ["chain_of_thought", "tree_of_thought", "step_by_step"],
                "description": "思考方式：chain_of_thought(思维链)、tree_of_thought(思维树)、step_by_step(步骤分解)",
                "default": "chain_of_thought"
            }
        },
        "required": ["question"]
    }

    def __init__(self):
        """初始化思考工具"""
        self.model = PlatformRegistry.get_global_platform_registry().get_thinking_platform()

    def _generate_prompt(self, question: str, context: str, approach: str) -> str:
        """生成提示词
        
        Args:
            question: 问题
            context: 上下文
            approach: 思考方式
            
        Returns:
            str: 完整的提示词
        """
        # 基础提示词
        base_prompt = "你是一个擅长深度思考和逻辑推理的助手。"
        
        # 根据不同的思考方式添加具体指导
        approach_prompts = {
            "chain_of_thought": """请使用思维链方式分析问题：
1. 仔细阅读问题和上下文
2. 逐步推理，每一步都要说明推理依据
3. 考虑多个可能的角度
4. 得出最终结论

请按以下格式输出：
思考过程：
1. [第一步推理]
2. [第二步推理]
...

结论：
[最终结论]""",

            "tree_of_thought": """请使用思维树方式分析问题：
1. 将问题分解为多个子问题
2. 对每个子问题进行分支探索
3. 评估每个分支的可行性
4. 整合最优路径

请按以下格式输出：
问题分解：
- 子问题1
  - 分支1.1
  - 分支1.2
- 子问题2
  - 分支2.1
  - 分支2.2

分析过程：
[详细分析每个分支]

最优路径：
[说明选择原因]

结论：
[最终结论]""",

            "step_by_step": """请使用步骤分解方式分析问题：
1. 将问题分解为具体步骤
2. 详细说明每个步骤的执行方法
3. 考虑每个步骤可能的问题
4. 提供完整的解决方案

请按以下格式输出：
步骤分解：
步骤1: [具体内容]
步骤2: [具体内容]
...

执行分析：
[详细分析每个步骤]

解决方案：
[完整方案]"""
        }

        # 构建完整提示词
        prompt = f"""{base_prompt}

{approach_prompts[approach]}

问题：
{question}

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
                - approach: 思考方式（可选）
                
        Returns:
            Dict[str, Any]: 执行结果
        """
        try:
            # 获取参数
            question = args["question"]
            context = args.get("context", "")
            approach = args.get("approach", "chain_of_thought")
            
            # 生成提示词
            prompt = self._generate_prompt(question, context, approach)
            
            # 记录开始分析
            PrettyOutput.print(f"开始分析问题: {question}", OutputType.INFO)
            if context:
                PrettyOutput.print("包含上下文信息", OutputType.INFO)
            PrettyOutput.print(f"使用{approach}方式思考", OutputType.INFO)
            
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
    parser.add_argument('--approach', choices=['chain_of_thought', 'tree_of_thought', 'step_by_step'],
                      default='chain_of_thought', help='思考方式')
    args = parser.parse_args()
    
    tool = ThinkerTool()
    result = tool.execute({
        "question": args.question,
        "context": args.context,
        "approach": args.approach
    })
    
    if result["success"]:
        PrettyOutput.print("\n分析结果:", OutputType.INFO)
        PrettyOutput.print(result["stdout"], OutputType.INFO)
    else:
        PrettyOutput.print(result["error"], OutputType.ERROR)

if __name__ == "__main__":
    main() 