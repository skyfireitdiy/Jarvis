from typing import Dict, Any, List, Union
import os

from jarvis.utils import OutputType, PrettyOutput


class FileOperationTool:
    name = "file_operation"
    description = "File operations for reading and writing multiple files"
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["read", "write"],
                "description": "Type of file operation to perform (read or write multiple files)"
            },
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["path"]
                },
                "description": "List of files to operate on"
            }
        },
        "required": ["operation", "files"]
    }

    def _handle_single_file(self, operation: str, filepath: str, content: str = "") -> Dict[str, Any]:
        """Handle operations for a single file"""
        try:
            abs_path = os.path.abspath(filepath)
            PrettyOutput.print(f"文件操作: {operation} - {abs_path}", OutputType.INFO)
            
            if operation == "read":
                if not os.path.exists(filepath):
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"文件不存在: {filepath}"
                    }
                    
                if os.path.getsize(filepath) > 10 * 1024 * 1024:  # 10MB
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "File too large (>10MB)"
                    }
                    
                content = open(filepath, 'r', encoding='utf-8').read()
                PrettyOutput.print(f"读取文件: {filepath}", OutputType.INFO)
                return {
                    "success": True,
                    "stdout": f"File: {filepath}\n{content}",
                    "stderr": ""
                }
                
            elif operation == "write":
                os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                PrettyOutput.print(f"写入文件: {filepath}", OutputType.INFO)
                return {
                    "success": True,
                    "stdout": f"Successfully wrote content to {filepath}",
                    "stderr": ""
                }
            
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Unknown operation: {operation}"
            }
            
        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"File operation failed for {filepath}: {str(e)}"
            }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute file operations for multiple files
        
        Args:
            args: Dictionary containing operation and files list
            
        Returns:
            Dict containing:
                - success: Boolean indicating overall success
                - stdout: Combined output of all operations as string
                - stderr: Error message if any
        """
        try:
            operation = args["operation"].strip()
            
            if "files" not in args or not isinstance(args["files"], list):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "files parameter is required and must be a list"
                }
            
            all_outputs = []
            success = True
            
            for file_info in args["files"]:
                if not isinstance(file_info, dict) or "path" not in file_info:
                    continue
                
                content = file_info.get("content", "") if operation == "write" else ""
                result = self._handle_single_file(operation, file_info["path"], content)
                
                if result["success"]:
                    all_outputs.append(result["stdout"])
                else:
                    all_outputs.append(f"Error with {file_info['path']}: {result['stderr']}")
                success = success and result["success"]
            
            # Combine all outputs with separators
            combined_output = "\n\n" + "="*80 + "\n\n".join(all_outputs)
            
            return {
                "success": success,
                "stdout": combined_output,
                "stderr": ""
            }
                
        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"File operation failed: {str(e)}"
            } 