from typing import List, Dict, Optional, Tuple, Any
import jedi
from jarvis.jarvis_lsp.base import BaseLSP

class PythonLSP(BaseLSP):
    """Python LSP implementation using jedi."""

    language = "python"

    def __init__(self):
        self.workspace_path = ""
        self.script_cache = {}

    def initialize(self, workspace_path: str) -> bool:
        self.workspace_path = workspace_path
        return True

    def _get_script(self, file_path: str):
        if file_path not in self.script_cache:
            try:
                with open(file_path, 'r', errors="ignore") as f:
                    content = f.read()
                self.script_cache[file_path] = jedi.Script(code=content, path=file_path)
            except Exception:
                return None
        return self.script_cache[file_path]


    def _location_to_dict(self, location) -> Dict[str, Any]:
        return {
            "uri": location.module_path,
            "range": {
                "start": {"line": location.line - 1, "character": location.column},
                "end": {"line": location.line - 1, "character": location.column + len(location.name)}
            }
        }

    def get_diagnostics(self, file_path: str) -> List[Dict[str, Any]]:
        script = self._get_script(file_path)
        if not script:
            return []
        try:
            errors = script.get_syntax_errors()
            return [{
                "range": {
                    "start": {"line": e.line - 1, "character": e.column},
                    "end": {"line": e.line - 1, "character": e.column + 1}
                },
                "severity": 1,  # Error
                "source": "jedi",
                "message": str(e)
            } for e in errors]
        except Exception:
            return []

    def shutdown(self):
        self.script_cache.clear()
