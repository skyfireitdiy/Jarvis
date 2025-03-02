from typing import Dict, Any, List, Union
import os

from jarvis.jarvis_utils import OutputType, PrettyOutput


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
                if not os.path.exists(abs_path):
                    PrettyOutput.print(f"文件不存在: {abs_path}", OutputType.WARNING)
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"文件不存在: {abs_path}"
                    }
                    
                if os.path.getsize(abs_path) > 10 * 1024 * 1024:  # 10MB
                    PrettyOutput.print(f"文件太大: {abs_path}", OutputType.WARNING)
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "File too large (>10MB)"
                    }
                    
                content = open(abs_path, 'r', encoding='utf-8').read()
                output = f"File: {abs_path}\n{content}"
                
                return {
                    "success": True,
                    "stdout": output,
                    "stderr": ""
                }
                
            elif operation == "write":
                os.makedirs(os.path.dirname(os.path.abspath(abs_path)), exist_ok=True)
                with open(abs_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                PrettyOutput.print(f"写入文件: {abs_path}", OutputType.INFO)
                return {
                    "success": True,
                    "stdout": f"Successfully wrote content to {abs_path}",
                    "stderr": ""
                }
            PrettyOutput.print(f"未知操作: {operation}", OutputType.WARNING)
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
                "stderr": f"File operation failed for {abs_path}: {str(e)}"
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
                result = self._handle_single_file(operation, file_info["path"].strip(), content)
                
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