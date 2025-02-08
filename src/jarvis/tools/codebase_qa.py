import os
from typing import Any, Dict
from jarvis.jarvis_codebase.main import CodeBase
from jarvis.utils import find_git_root, PrettyOutput, OutputType

class CodebaseQATool:
    """代码库问答工具，用于回答关于代码库的问题"""
    
    name = "codebase_qa"
    description = "Answer questions about the codebase, can query and understand code functionality, structure, and implementation details"
    parameters = {
        "type": "object",
        "properties": {
            "dir": {
                "type": "string",
                "description": "Project root directory"
            },
            "question": {
                "type": "string",
                "description": "Question about the codebase"
            },
            "top_k": {
                "type": "integer",
                "description": "Number of relevant files to search",
                "default": 5
            }
        },
        "required": ["question"]
    }
    
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行代码问答"""
        try:
            dir = params.get("dir")
            question = params["question"]
            top_k = params.get("top_k", 5)
            
            # 初始化代码库
            current_dir = os.getcwd()
            root_dir = find_git_root(dir or current_dir)
            if not root_dir:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "错误：当前目录不在Git仓库中",
                    "error": "NotInGitRepository"
                }

            os.chdir(root_dir)
            codebase = CodeBase(root_dir)
            # 生成索引

            codebase.generate_codebase()
            # 执行问答
            response = codebase.ask_codebase(question, top_k)
            os.chdir(current_dir)
            return {
                "success": True,
                "stdout": response,
                "stderr": "",
                "error": None
            }
            
        except Exception as e:
            PrettyOutput.print(f"代码问答出错: {str(e)}", output_type=OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行代码问答时发生错误: {str(e)}",
                "error": str(type(e).__name__)
            }

def register():
    return CodebaseQATool() 