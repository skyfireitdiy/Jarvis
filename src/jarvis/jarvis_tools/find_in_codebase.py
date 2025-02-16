from typing import Dict, Any
from jarvis.jarvis_code_agent.file_select import select_files
from jarvis.utils import OutputType, PrettyOutput, dont_use_local_model, find_git_root
from jarvis.jarvis_codebase.main import CodeBase

class FindInCodebaseTool:
    """Tool for searching files in codebase based on requirements"""
    
    name = "find_in_codebase"
    description = "Search and identify relevant code files in the codebase based on requirements description, using semantic search"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query or requirement description"
            },
            "top_k": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 20
            }
        },
        "required": ["query"]
    }

    @staticmethod
    def check() -> bool:
        return not dont_use_local_model()

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute the search
        
        Args:
            args: Dictionary containing:
                - query: Search query string
                - top_k: Maximum number of results (optional)
                
        Returns:
            Dict containing:
                - success: Boolean indicating success
                - stdout: Search results in YAML format
                - stderr: Error message if any
        """
        try:
            query = args["query"]
            top_k = args.get("top_k", 20)

            root_dir = find_git_root()

            codebase = CodeBase(root_dir)

            # Search for relevant files
            results = codebase.search_similar(query, top_k)

            results = select_files(results, root_dir)

            if not results:
                return {
                    "success": True,
                    "stdout": "files: []\n",
                    "stderr": "No relevant files found"
                }


            return {
                "success": True,
                "stdout": "\n".join(results),
                "stderr": ""
            }

        except Exception as e:
            PrettyOutput.print(f"Search error: {str(e)}", OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to execute search: {str(e)}"
            }
