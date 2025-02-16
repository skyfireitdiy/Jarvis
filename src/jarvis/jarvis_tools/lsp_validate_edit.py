import os
from typing import Dict, Any
from jarvis.jarvis_lsp.registry import LSPRegistry

class LSPValidateEditTool:
    """Tool for validating code edits using LSP."""
    
    name = "lsp_validate_edit"
    description = "Validate if a proposed code edit is syntactically correct"
    parameters = {
        "file_path": "Path to the file to edit",
        "start_line": "Starting line number (0-based) of the edit",
        "start_character": "Starting character position in the start line",
        "end_line": "Ending line number (0-based) of the edit",
        "end_character": "Ending character position in the end line",
        "new_text": "New text to insert",
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
        start_line = args.get("start_line", None)
        start_character = args.get("start_character", None)
        end_line = args.get("end_line", None)
        end_character = args.get("end_character", None)
        new_text = args.get("new_text", "")
        language = args.get("language", "")
        
        # Validate inputs
        if not all([file_path, start_line is not None, start_character is not None,
                   end_line is not None, end_character is not None, language]):
            return {
                "success": False,
                "stderr": "All parameters except new_text must be provided",
                "stdout": ""
            }
            
        try:
            start_line = int(start_line)
            start_character = int(start_character)
            end_line = int(end_line)
            end_character = int(end_character)
        except ValueError:
            return {
                "success": False,
                "stderr": "Line and character positions must be integers",
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
            if not lsp.initialize(os.path.dirname(os.path.abspath(file_path))):
                return {
                    "success": False,
                    "stderr": "LSP initialization failed",
                    "stdout": ""
                }
                
            # Prepare edit operation
            edit = {
                "range": {
                    "start": {"line": start_line, "character": start_character},
                    "end": {"line": end_line, "character": end_character}
                },
                "newText": new_text
            }
            
            # Show the edit preview
            output = ["Edit Preview:"]
            
            # Show original code
            try:
                with open(file_path, 'r') as f:
                    lines = f.readlines()
                    context_start = max(0, start_line - 2)
                    context_end = min(len(lines), end_line + 3)
                    
                    output.append("\nOriginal code:")
                    for i in range(context_start, context_end):
                        prefix = ">" if start_line <= i <= end_line else " "
                        output.append(f"{prefix} {i+1:4d} | {lines[i].rstrip()}")
            except Exception:
                pass
            
            # Show new text
            output.extend([
                "\nNew text to insert:",
                new_text,
                "\nEdit range:",
                f"From line {start_line + 1}, character {start_character}",
                f"To line {end_line + 1}, character {end_character}"
            ])
            
            # Validate edit
            is_valid = lsp.validate_edit(file_path, edit)
            
            if is_valid:
                output.append("\nValidation Result: The edit is syntactically correct ✓")
            else:
                output.append("\nValidation Result: The edit would introduce syntax errors ✗")
            
            return {
                "success": True,
                "stdout": "\n".join(output),
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stderr": f"Error validating edit: {str(e)}",
                "stdout": ""
            }
        finally:
            if lsp:
                lsp.shutdown()
