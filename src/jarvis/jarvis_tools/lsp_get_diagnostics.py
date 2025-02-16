import os
from typing import Dict, Any
from jarvis.jarvis_lsp.registry import LSPRegistry

class LSPGetDiagnosticsTool:
    """Tool for getting diagnostics (errors, warnings) from code using LSP."""
    
    name = "lsp_get_diagnostics"
    description = "Get diagnostic information (errors, warnings) from code files"
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
        
        # Validate inputs
        if not all([file_path, language]):
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
            if not lsp.initialize(os.path.dirname(os.path.abspath(file_path))):
                return {
                    "success": False,
                    "stderr": "LSP initialization failed",
                    "stdout": ""
                }
                
            # Get diagnostics
            diagnostics = lsp.get_diagnostics(file_path)
            
            if not diagnostics:
                return {
                    "success": True,
                    "stdout": "No issues found in the file",
                    "stderr": ""
                }
                
            # Format output
            output = ["Diagnostics:"]
            severity_map = {1: "Error", 2: "Warning", 3: "Info", 4: "Hint"}
            
            # Sort diagnostics by severity and line number
            sorted_diagnostics = sorted(
                diagnostics,
                key=lambda x: (x["severity"], x["range"]["start"]["line"])
            )
            
            for diag in sorted_diagnostics:
                severity = severity_map.get(diag["severity"], "Unknown")
                start = diag["range"]["start"]
                line = LSPRegistry.get_line_at_position(file_path, start["line"]).strip()
                
                output.extend([
                    f"\n{severity} at line {start['line'] + 1}, column {start['character'] + 1}:",
                    f"Message: {diag['message']}",
                    f"Code: {line}",
                    "-" * 60
                ])
                
                # Add related information if available
                if diag.get("relatedInformation"):
                    output.append("Related information:")
                    for info in diag["relatedInformation"]:
                        info_line = LSPRegistry.get_line_at_position(
                            info["location"]["uri"],
                            info["location"]["range"]["start"]["line"]
                        ).strip()
                        output.extend([
                            f"  - {info['message']}",
                            f"    at {info['location']['uri']}:{info['location']['range']['start']['line'] + 1}",
                            f"    {info_line}"
                        ])
            
            return {
                "success": True,
                "stdout": "\n".join(output),
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stderr": f"Error getting diagnostics: {str(e)}",
                "stdout": ""
            }
        finally:
            if lsp:
                lsp.shutdown()
