import os
import shutil
import subprocess
from typing import List, Dict, Optional, Tuple, Any
import json
from jarvis.jarvis_lsp.base import BaseLSP
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

class GoLSP(BaseLSP):
    """Go LSP implementation using gopls."""

    language = "go"

    @staticmethod
    def check() -> bool:
        """Check if gopls is installed."""
        return shutil.which("gopls") is not None

    def __init__(self):
        self.workspace_path = ""
        self.gopls_process = None
        self.request_id = 0

    def initialize(self, workspace_path: str) -> bool:
        try:
            self.workspace_path = workspace_path
            # Start gopls process
            self.gopls_process = subprocess.Popen(
                ["gopls", "serve"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Send initialize request
            self._send_request("initialize", {
                "processId": os.getpid(),
                "rootUri": f"file://{workspace_path}",
                "capabilities": {
                    "textDocument": {
                        "hover": {"contentFormat": ["markdown", "plaintext"]},
                        "completion": {"completionItem": {"snippetSupport": True}},
                        "signatureHelp": {"signatureInformation": {"documentationFormat": ["markdown", "plaintext"]}},
                    }
                }
            })

            return True
        except Exception as e:
            PrettyOutput.print(f"Go LSP 初始化失败: {str(e)}", OutputType.ERROR)
            return False

    def _send_request(self, method: str, params: Dict) -> Optional[Dict]:
        """Send JSON-RPC request to gopls."""
        if not self.gopls_process:
            return None

        try:
            self.request_id += 1
            request = {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": method,
                "params": params
            }

            self.gopls_process.stdin.write(json.dumps(request).encode() + b"\n") # type: ignore
            self.gopls_process.stdin.flush() # type: ignore

            response = json.loads(self.gopls_process.stdout.readline().decode()) # type: ignore
            return response.get("result")
        except Exception:
            return None

    def get_diagnostics(self, file_path: str) -> List[Dict[str, Any]]:
        # Send didOpen notification to trigger diagnostics
        self._send_request("textDocument/didOpen", {
            "textDocument": {
                "uri": f"file://{file_path}",
                "languageId": "go",
                "version": 1,
                "text": open(file_path).read()
            }
        })

        # Wait for diagnostic notification
        try:
            response = json.loads(self.gopls_process.stdout.readline().decode()) # type: ignore
            if response.get("method") == "textDocument/publishDiagnostics":
                return response.get("params", {}).get("diagnostics", [])
        except Exception:
            pass
        return []


    def shutdown(self):
        if self.gopls_process:
            try:
                self._send_request("shutdown", {})
                self.gopls_process.terminate()
                self.gopls_process = None
            except Exception:
                pass
