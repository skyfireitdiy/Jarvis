from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple, Any, Union

class BaseLSP(ABC):
    """Base class for Language Server Protocol integration.

    Core LSP features needed for LLM-based code editing:
    1. Code navigation and analysis
    2. Code modification validation
    3. Diagnostic information
    4. Symbol analysis
    """

    language: Union[str, List[str]] = ""  # Language identifier, should be overridden by subclasses

    @abstractmethod
    def initialize(self, workspace_path: str) -> bool:
        """Initialize LSP server for the workspace.

        Args:
            workspace_path: Root path of the workspace

        Returns:
            bool: True if initialization successful
        """
        return False


    @abstractmethod
    def get_diagnostics(self, file_path: str) -> List[Dict[str, Any]]:
        """Get diagnostics (errors, warnings) for file.

        Args:
            file_path: Path to the file

        Returns:
            List of diagnostic items:
            [
                {
                    "range": {
                        "start": {"line": int, "character": int},
                        "end": {"line": int, "character": int}
                    },
                    "severity": 1 | 2 | 3 | 4,  # Error=1, Warning=2, Info=3, Hint=4
                    "code": str,                # Error code if any
                    "source": str,             # Source of diagnostic (e.g. "pylint")
                    "message": str,            # Diagnostic message
                    "relatedInformation": [    # Optional related info
                        {
                            "location": {
                                "uri": str,
                                "range": {...}
                            },
                            "message": str
                        }
                    ]
                }
            ]
        """
        return []


    def shutdown(self):
        """Shutdown LSP server cleanly."""
        pass
