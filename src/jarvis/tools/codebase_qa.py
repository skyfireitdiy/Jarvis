import os
from typing import Any, Dict
from jarvis.jarvis_codebase.main import CodeBase
from jarvis.utils import find_git_root, PrettyOutput, OutputType

class CodebaseQATool:
    """Codebase QA Tool"""
    
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
        """Execute codebase QA"""
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
                    "stderr": "Error: Current directory is not in a Git repository",
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
            }
            
        except Exception as e:
            PrettyOutput.print(f"Codebase QA error: {str(e)}", output_type=OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Error executing codebase QA: {str(e)}",
            }

