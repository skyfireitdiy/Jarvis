from typing import Dict, Any
import os
from jarvis.utils import OutputType, PrettyOutput
from jarvis.jarvis_rag.main import RAGTool as RAGCore

class RAGTool:
    name = "rag"
    description = "Ask questions based on a document directory, supporting multiple document formats (txt, pdf, docx, etc.)"
    parameters = {
        "type": "object",
        "properties": {
            "dir": {
                "type": "string",
                "description": "Document directory path, supports both relative and absolute paths"
            },
            "question": {
                "type": "string",
                "description": "The question to ask"
            },
            "rebuild_index": {
                "type": "boolean",
                "description": "Whether to rebuild the index",
                "default": False
            }
        },
        "required": ["dir", "question"]
    }

    def __init__(self):
        """Initialize RAG tool"""
        self.rag_instances = {}  # Cache RAG instances for different directories

    def _get_rag_instance(self, dir_path: str) -> RAGCore:
        """Get or create RAG instance
        
        Args:
            dir_path: The absolute path of the document directory
            
        Returns:
            RAGCore: RAG instance
        """
        if dir_path not in self.rag_instances:
            self.rag_instances[dir_path] = RAGCore(dir_path)
        return self.rag_instances[dir_path]

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute document question and answer
        
        Args:
            args: A dictionary containing parameters
                - dir: The document directory path
                - question: The question to ask
                - rebuild_index: Whether to rebuild the index
                
        Returns:
            Dict[str, Any]: The execution result
        """
        try:
            # Get parameters
            dir_path = os.path.expanduser(args["dir"])  # Expand ~ paths
            dir_path = os.path.abspath(dir_path)  # Convert to absolute path
            question = args["question"]
            rebuild_index = args.get("rebuild_index", False)
            
            # Check if the directory exists
            if not os.path.exists(dir_path):
                return {
                    "success": False,
                    "error": f"Directory does not exist: {dir_path}"
                }
                
            # Check if it is a directory
            if not os.path.isdir(dir_path):
                return {
                    "success": False,
                    "error": f"The path is not a directory: {dir_path}"
                }
                
            # Get RAG instance
            rag = self._get_rag_instance(dir_path)
            
            # If you need to rebuild the index or the index does not exist
            if rebuild_index or not rag.is_index_built():
                PrettyOutput.print("Building document index...", OutputType.INFO)
                rag.build_index(dir_path)
            
            # Execute question and answer
            PrettyOutput.print(f"Question: {question}", OutputType.INFO)
            response = rag.ask(question)
            
            if response is None:
                return {
                    "success": False,
                    "error": "Failed to get answer, possibly no relevant documents found"
                }
                
            return {
                "success": True,
                "stdout": response,
                "stderr": ""
            }
            
        except Exception as e:
            PrettyOutput.print(f"Document question and answer failed: {str(e)}", OutputType.ERROR)
            return {
                "success": False,
                "error": f"Execution failed: {str(e)}"
            }

def main():
    """Run the tool directly from the command line"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Document question and answer tool')
    parser.add_argument('--dir', required=True, help='Document directory path')
    parser.add_argument('--question', required=True, help='The question to ask')
    parser.add_argument('--rebuild', action='store_true', help='Rebuild index')
    args = parser.parse_args()
    
    tool = RAGTool()
    result = tool.execute({
        "dir": args.dir,
        "question": args.question,
        "rebuild_index": args.rebuild
    })
    
    if result["success"]:
        PrettyOutput.print("\nAnswer:", OutputType.INFO)
        PrettyOutput.print(result["stdout"], OutputType.INFO)
    else:
        PrettyOutput.print(result["error"], OutputType.ERROR)

if __name__ == "__main__":
    main() 