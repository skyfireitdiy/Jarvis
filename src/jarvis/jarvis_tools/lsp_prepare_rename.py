import os
from typing import Dict, Any
from jarvis.jarvis_lsp.registry import LSPRegistry

class LSPPrepareRenameTool:
    """使用LSP检查符号是否可以安全重命名并显示所有受影响位置的工具"""
    
    name = "lsp_prepare_rename"
    description = "检查符号是否可以安全重命名，并显示所有受影响的位置"
    parameters = {
        "file_path": "包含符号的文件路径",
        "line": "符号所在的行号（从0开始）",
        "character": "符号在行中的字符位置",
        "language": f"文件的编程语言（{', '.join(LSPRegistry.get_global_lsp_registry().get_supported_languages())}）"
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
                
            # Check if rename is possible
            rename_info = lsp.prepare_rename(file_path, (line, character))
            if not rename_info:
                return {
                    "success": True,
                    "stdout": f"Symbol '{symbol}' cannot be renamed. It might be:\n" +
                             "- A built-in or library symbol\n" +
                             "- A read-only symbol\n" +
                             "- Not a valid identifier",
                    "stderr": ""
                }
                
            # Get all references to show affected locations
            refs = lsp.find_references(file_path, (line, character))
            
            # Format output
            output = [
                f"Symbol '{symbol}' can be renamed.",
                f"\nRenaming will affect the following locations:"
            ]
            
            for ref in refs:
                ref_line = ref["range"]["start"]["line"]
                ref_char = ref["range"]["start"]["character"]
                context = LSPRegistry.get_line_at_position(ref["uri"], ref_line).strip()
                output.extend([
                    f"\nFile: {ref['uri']}",
                    f"Line {ref_line + 1}, Col {ref_char + 1}: {context}"
                ])
            
            output.append("\nNote: Make sure to review all locations before performing the rename.")
            
            return {
                "success": True,
                "stdout": "\n".join(output),
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stderr": f"Error checking rename possibility: {str(e)}",
                "stdout": ""
            }
        finally:
            if lsp:
                lsp.shutdown()