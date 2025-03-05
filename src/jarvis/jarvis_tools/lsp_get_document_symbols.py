import os
from typing import Dict, Any
from jarvis.jarvis_lsp.registry import LSPRegistry

class LSPGetDocumentSymbolsTool:
    """Tool for getting document symbols in code files using LSP."""
    
    name = "lsp_get_document_symbols"
    description = "Get document symbols (functions, classes, variables) in code files"
    parameters = {
        "file_path": "Path to the file to analyze",
        "language": f"Programming language of the file ({', '.join(LSPRegistry.get_global_lsp_registry().get_supported_languages())})"
    }
    
    @staticmethod
    def check() -> bool:
        """Check if any LSP server is available."""
        registry = LSPRegistry.get_global_lsp_registry()
        return len(registry.get_supported_languages()) > 0
    
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the tool."""
        file_path = args.get("file_path", "")
        language = args.get("language", "")
        
        if not file_path or not language:
            return {
                "success": False,
                "stderr": "Both file_path and language must be provided",
                "stdout": ""
            }
            
        if not os.path.exists(file_path):
            return {
                "success": False,
                "stderr": f"File not found: {file_path}",
                "stdout": ""
            }
            
        # Get LSP instance
        registry = LSPRegistry.get_global_lsp_registry()
        lsp = registry.create_lsp(language)
        
        if not lsp:
            return {
                "success": False,
                "stderr": f"No LSP support for language: {language}",
                "stdout": ""
            }
            
        try:
            # Initialize LSP
            if not lsp.initialize(os.path.abspath(os.getcwd())):
                return {
                    "success": False,
                    "stderr": "LSP initialization failed",
                    "stdout": ""
                }
                
            # Get symbols
            symbols = lsp.get_document_symbols(file_path)
            
            # Format output
            output = []
            for symbol in symbols:
                start = symbol["range"]["start"]
                name = LSPRegistry.get_text_at_position(file_path, start["line"], start["character"])
                line = LSPRegistry.get_line_at_position(file_path, start["line"]).strip()
                output.append(f"Symbol: {name}")
                output.append(f"Line {start['line'] + 1}: {line}")
                output.append("-" * 40)
            
            return {
                "success": True,
                "stdout": "\n".join(output) if output else "No symbols found",
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stderr": f"Error finding symbols: {str(e)}",
                "stdout": ""
            }
        finally:
            if lsp:
                lsp.shutdown()
