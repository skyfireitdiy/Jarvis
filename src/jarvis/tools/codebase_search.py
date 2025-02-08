import os
from typing import Any, Dict
from jarvis.jarvis_codebase.main import CodeBase
from jarvis.utils import find_git_root, PrettyOutput, OutputType

class CodebaseSearchTool:
    """Codebase Search Tool"""
    
    name = "codebase_search"
    description = "Search the codebase, find related code files"
    parameters = {
        "type": "object",
        "properties": {
            "dir": {
                "type": "string",
                "description": "Project root directory"
            },
            "query": {
                "type": "string",
                "description": "Query about the codebase"
            },
            "top_k": {
                "type": "integer",
                "description": "Number of relevant files to search",
                "default": 5
            }
        },
        "required": ["query"]
    }
    
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute codebase search"""
        try:
            dir = params.get("dir")
            query = params["query"]
            top_k = params.get("top_k", 5)
            
            # Find the root directory of the codebase
            current_dir = os.getcwd()
            root_dir = find_git_root(dir or current_dir)
            if not root_dir:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Error: Current directory is not in a Git repository",
                    "error": "NotInGitRepository"
                }

            os.chdir(root_dir)
            codebase = CodeBase(root_dir)
            # Generate index

            codebase.generate_codebase()
            # Execute search
            response = codebase.search_similar(query, top_k)
            os.chdir(current_dir)
            return {
                "success": True,
                "stdout": str(response),
                "stderr": "",
                "error": None
            }
            
        except Exception as e:
            PrettyOutput.print(f"Codebase QA error: {str(e)}", output_type=OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Error executing codebase QA: {str(e)}",
                "error": str(type(e).__name__)
            }
