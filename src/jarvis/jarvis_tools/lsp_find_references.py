import os
from typing import Dict, Any
from jarvis.jarvis_lsp.registry import LSPRegistry

class LSPFindReferencesTool:
    """Tool for finding references to symbols in code using LSP."""
    
    name = "lsp_find_references"
    description = "Find all references to a symbol in code"
    parameters = {
        "file_path": "Path to the file containing the symbol",
        "line": "Line number (0-based) of the symbol",
        "character": "Character position in the line",
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
        line = args.get("line", None)
        character = args.get("character", None)
        language = args.get("language", "")
        
        # Validate inputs
        if not all([file_path, line is not None, character is not None, language]):
            return {
                "success": False,
                "stderr": "All parameters (file_path, line, character, language) must be provided",
                "stdout": ""
            }
            
        try:
            line = int(line)
            character = int(character)
        except ValueError:
            return {
                "success": False,
                "stderr": "Line and character must be integers",
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
                
            # Get symbol at position
            symbol = LSPRegistry.get_text_at_position(file_path, line, character)
            if not symbol:
                return {
                    "success": False,
                    "stderr": f"No symbol found at position {line}:{character}",
                    "stdout": ""
                }
                
            # Find references
            refs = lsp.find_references(file_path, (line, character))
            
            # Format output
            output = [f"References to '{symbol}':\n"]
            for ref in refs:
                ref_line = ref["range"]["start"]["line"]
                ref_char = ref["range"]["start"]["character"]
                context = LSPRegistry.get_line_at_position(ref["uri"], ref_line).strip()
                output.append(f"File: {ref['uri']}")
                output.append(f"Line {ref_line + 1}, Col {ref_char + 1}: {context}")
                output.append("-" * 40)
            
            return {
                "success": True,
                "stdout": "\n".join(output) if len(refs) > 0 else f"No references found for '{symbol}'",
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stderr": f"Error finding references: {str(e)}",
                "stdout": ""
            }
        finally:
            if lsp:
                lsp.shutdown()
