from typing import Dict, Any
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

            codebase = CodeBase(find_git_root())

            # Search for relevant files
            results = codebase.search_similar(query, top_k)

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

def main():
    """Command line interface for the tool"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Search for relevant files in codebase')
    parser.add_argument('query', help='Search query or requirement description')
    parser.add_argument('--top-k', type=int, default=20, help='Maximum number of results to return')
    
    args = parser.parse_args()
    
    tool = FindInCodebaseTool()
    result = tool.execute({
        "query": args.query,
        "top_k": args.top_k
    })
    
    if result["success"]:
        if result["stdout"]:
            print(result["stdout"])
        else:
            PrettyOutput.print("No relevant files found", OutputType.WARNING)
    else:
        PrettyOutput.print(result["stderr"], OutputType.ERROR)
        return 1
        
    return 0

if __name__ == "__main__":
    exit(main())
