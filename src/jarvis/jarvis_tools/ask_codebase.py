from typing import Dict, Any
import os

from yaspin import yaspin
from jarvis.jarvis_codebase.main import CodeBase
from jarvis.jarvis_utils.config import dont_use_local_model
from jarvis.jarvis_utils.git_utils import find_git_root
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

class AskCodebaseTool:
    """用于智能代码库查询和分析的工具
    
    适用场景：
    - 查询特定功能所在的文件位置
    - 了解单个功能点的实现原理
    - 查找特定API或接口的用法
    
    不适用场景：
    - 跨越多文件的大范围分析
    - 复杂系统架构的全面评估
    - 需要深入上下文理解的代码重构
    """

    name = "ask_codebase"
    description = "查询代码库中特定功能的位置和实现原理，适合定位功能所在文件和理解单点实现，不适合跨文件大范围分析"
    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "关于代码库的问题，例如'登录功能在哪个文件实现？'或'如何实现了JWT验证？'"
            },
            "top_k": {
                "type": "integer",
                "description": "要分析的最相关文件数量（可选）",
                "default": 20
            },
            "root_dir": {
                "type": "string",
                "description": "代码库根目录路径（可选）",
                "default": "."
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
                - question: The question to answer, preferably about locating functionality
                  or understanding implementation details of a specific feature
                - top_k: Optional number of files to analyze
                - root_dir: Optional root directory of the codebase
                
        Returns:
            Dict containing:
                - success: Boolean indicating success
                - stdout: Analysis result
                - stderr: Error message if any
                
        Note:
            This tool works best for focused questions about specific features or implementations.
            It is not designed for comprehensive multi-file analysis or complex architectural questions.
        """
        try:
            question = args["question"]
            top_k = args.get("top_k", 20)
            root_dir = args.get("root_dir", ".")
            
            # Store current directory
            original_dir = os.getcwd()
            
            try:
                # Change to root_dir
                os.chdir(root_dir)
                
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
                    PrettyOutput.print(output, OutputType.SUCCESS, lang="markdown")

                PrettyOutput.print(response, OutputType.SUCCESS, lang="markdown")
                
                return {
                    "success": True,
                    "stdout": response,
                    "stderr": ""
                }
            finally:
                # Always restore original directory
                os.chdir(original_dir)
        except Exception as e:
            error_msg = f"分析代码库失败: {str(e)}"
            PrettyOutput.print(error_msg, OutputType.WARNING)
            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg
            }
def main():
    """Command line interface for the tool
    
    Use this tool to ask questions about specific functionality in the codebase.
    Best for questions like:
    - "Where is the authentication functionality implemented?"
    - "How does the payment processing work?"
    - "What file contains the API routes for users?"
    
    Not ideal for questions requiring deep multi-file analysis.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='Ask questions about specific functionality in the codebase')
    parser.add_argument('question', help='Question about locating or understanding specific functionality')
    parser.add_argument('--top-k', type=int, help='Number of files to analyze', default=20)
    parser.add_argument('--root-dir', type=str, help='Root directory of the codebase', default=".")
    
    args = parser.parse_args()
    tool = AskCodebaseTool()
    result = tool.execute({
        "question": args.question,
        "top_k": args.top_k,
        "root_dir": args.root_dir
    })
    
    if result["success"]:
        PrettyOutput.print(result["stdout"], OutputType.INFO, lang="markdown")
    else:
        PrettyOutput.print(result["stderr"], OutputType.WARNING)
        

if __name__ == "__main__":
    main()