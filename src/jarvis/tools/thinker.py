from typing import Dict, Any
from jarvis.utils import OutputType, PrettyOutput, init_env
from jarvis.models.registry import PlatformRegistry

class ThinkerTool:
    name = "thinker"
    description = "Use chain of thought reasoning to analyze complex problems, suitable for scenarios that require multi-step reasoning, logical analysis, or creative thinking"
    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The problem or task to analyze"
            },
            "context": {
                "type": "string",
                "description": "Context information or background knowledge related to the problem",
                "default": ""
            },
            "goal": {
                "type": "string",
                "description": "The specific goal or result to achieve",
                "default": ""
            }
        },
        "required": ["question"]
    }

    def __init__(self):
        """Initialize thinker tool"""
        self.model = PlatformRegistry.get_global_platform_registry().get_thinking_platform()

    def _generate_prompt(self, question: str, context: str, goal: str) -> str:
        """Generate prompt
        
        Args:
            question: problem
            context: context
            goal: goal
            
        Returns:
            str: complete prompt
        """
        # 基础提示词
        prompt = f"""You are a helpful assistant that is good at deep thinking and logical reasoning. Please help analyze the problem and provide a solution.

Please think as follows:
1. Carefully understand the problem and goal
2. Conduct a systematic analysis and reasoning
3. Consider multiple possible solutions
4. Provide the best suggestions and specific action steps

Problem:
{question}
"""
        # 如果有目标，添加到提示词中
        if goal:
            prompt += f"""
Goal:
{goal}
"""

        # 如果有上下文，添加到提示词中
        if context:
            prompt += f"""
Related context:
{context}
"""

        prompt += "\nPlease start analyzing:"
        return prompt

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute thinking analysis
        
        Args:
            args: dictionary containing parameters
                - question: problem
                - context: context (optional)
                - goal: goal (optional)
                
        Returns:
            Dict[str, Any]: execution result
        """
        try:
            # Get parameters
            question = args["question"]
            context = args.get("context", "")
            goal = args.get("goal", "")
            
            # 生成提示词
            prompt = self._generate_prompt(question, context, goal)
            
            # Record start analysis
            PrettyOutput.print(f"Start analyzing problem: {question}", OutputType.INFO)
            if context:
                PrettyOutput.print("Contains context information", OutputType.INFO)
            if goal:
                PrettyOutput.print(f"Goal: {goal}", OutputType.INFO)
            
            # 调用模型进行分析
            response = self.model.chat_until_success(prompt)
            
            if not response:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Failed to obtain valid analysis results"
                }
                
            return {
                "success": True,
                "stdout": response,
                "stderr": ""
            }
            
        except Exception as e:
            PrettyOutput.print(f"Thinking analysis failed: {str(e)}", OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution failed: {str(e)}"
            }

def main():
    """Run tool directly from command line"""
    import argparse

    init_env()
    
    parser = argparse.ArgumentParser(description='Deep thinking analysis tool')
    parser.add_argument('--question', required=True, help='The problem to analyze')
    parser.add_argument('--context', help='Context information related to the problem')
    parser.add_argument('--goal', help='Specific goal or result to achieve')
    args = parser.parse_args()
    
    tool = ThinkerTool()
    result = tool.execute({
        "question": args.question,
        "context": args.context,
        "goal": args.goal
    })
    
    if result["success"]:
        PrettyOutput.print("\nAnalysis results:", OutputType.INFO)
        PrettyOutput.print(result["stdout"], OutputType.INFO)
    else:
        PrettyOutput.print(result["stderr"], OutputType.ERROR)

if __name__ == "__main__":
    main() 