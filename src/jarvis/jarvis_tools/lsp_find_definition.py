import os
from typing import Dict, Any
from jarvis.jarvis_lsp.registry import LSPRegistry

class LSPFindDefinitionTool:
    """使用LSP在代码中查找符号定义的工具"""
    
    name = "lsp_find_definition"
    description = "在代码中查找符号的定义"
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
                
            # Find definition
            defn = lsp.find_definition(file_path, (line, character))
            
            if not defn:
                return {
                    "success": True,
                    "stdout": f"No definition found for '{symbol}'",
                    "stderr": ""
                }
                
            # Format output
            def_line = defn["range"]["start"]["line"]
            def_char = defn["range"]["start"]["character"]
            context = LSPRegistry.get_line_at_position(defn["uri"], def_line).strip()
            
            output = [
                f"Definition of '{symbol}':",
                f"File: {defn['uri']}",
                f"Line {def_line + 1}, Col {def_char + 1}: {context}"
            ]
            
            # Get a few lines of context around the definition
            try:
                with open(defn["uri"], 'r') as f:
                    lines = f.readlines()
                    start = max(0, def_line - 2)
                    end = min(len(lines), def_line + 3)
                    
                    if start < def_line:
                        output.append("\nContext:")
                        for i in range(start, end):
                            prefix = ">" if i == def_line else " "
                            output.append(f"{prefix} {i+1:4d} | {lines[i].rstrip()}")
            except Exception:
                pass
            
            return {
                "success": True,
                "stdout": "\n".join(output),
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stderr": f"Error finding definition: {str(e)}",
                "stdout": ""
            }
        finally:
            if lsp:
                lsp.shutdown()