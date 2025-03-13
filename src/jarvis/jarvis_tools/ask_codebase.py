from typing import Dict, Any
from jarvis.jarvis_codebase.main import CodeBase
from jarvis.jarvis_utils.config import dont_use_local_model
from jarvis.jarvis_utils.git_utils import find_git_root
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

class AskCodebaseTool:
    """用于智能代码库查询和分析的工具"""

    name = "ask_codebase"
    description = "查询代码库问题并获取详细分析"
    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "关于代码库的问题"
            },
            "top_k": {
                "type": "integer",
                "description": "要分析的最相关文件数量（可选）",
                "default": 20
            }
        },
        "required": ["question"]
    }

    @staticmethod
    def check() -> bool:
        return not dont_use_local_model()

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute codebase analysis using CodeBase
        
        Args:
            args: Dictionary containing:
                - question: The question to answer
                - top_k: Optional number of files to analyze
                
        Returns:
            Dict containing:
                - success: Boolean indicating success
                - stdout: Analysis result
                - stderr: Error message if any
        """
        try:
            question = args["question"]
            top_k = args.get("top_k", 20)

            PrettyOutput.print(f"正在分析代码库以回答问题: {question}", OutputType.INFO)

            # Create new CodeBase instance
            git_root = find_git_root()
            codebase = CodeBase(git_root)

            # Use ask_codebase method
            files, response = codebase.ask_codebase(question, top_k)
            
            # Print found files
            if files:
                output = "找到的相关文件:\n"
                for file in files:
                    output += f"- {file['file']} ({file['reason']})\n"
                PrettyOutput.print(output, OutputType.INFO, lang="markdown")
            
            return {
                "success": True,
                "stdout": response,
                "stderr": ""
            }
        except Exception as e:
            error_msg = f"分析代码库失败: {str(e)}"
            PrettyOutput.print(error_msg, OutputType.WARNING)
            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg
            }
def main():
    """Command line interface for the tool"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Ask questions about the codebase')
    parser.add_argument('question', help='Question about the codebase')
    parser.add_argument('--top-k', type=int, help='Number of files to analyze', default=20)
    
    args = parser.parse_args()
    tool = AskCodebaseTool()
    result = tool.execute({
        "question": args.question,
        "top_k": args.top_k
    })
    
    if result["success"]:
        PrettyOutput.print(result["stdout"], OutputType.INFO, lang="markdown")
    else:
        PrettyOutput.print(result["stderr"], OutputType.WARNING)
        

if __name__ == "__main__":
    main()