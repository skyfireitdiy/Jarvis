from typing import Dict, Any
import os

from jarvis.utils import OutputType, PrettyOutput


class FileOperationTool:
    name = "file_operation"
    description = "File operations (read/write/append/exists)"
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["read", "write", "append", "exists"],
                "description": "Type of file operation to perform"
            },
            "filepath": {
                "type": "string",
                "description": "Absolute or relative path to the file"
            },
            "content": {
                "type": "string",
                "description": "Content to write (required for write/append operations)",
                "default": ""
            },
            "encoding": {
                "type": "string",
                "description": "File encoding (default: utf-8)",
                "default": "utf-8"
            }
        },
        "required": ["operation", "filepath"]
    }


    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute file operations"""
        try:
            operation = args["operation"].strip()
            filepath = args["filepath"].strip()
            encoding = args.get("encoding", "utf-8")
            
            # Record the operation and the full path
            abs_path = os.path.abspath(filepath)
            PrettyOutput.print(f"File operation: {operation} - {abs_path}", OutputType.INFO)
            
            if operation == "exists":
                exists = os.path.exists(filepath)
                return {
                    "success": True,
                    "stdout": str(exists),
                    "stderr": ""
                }
                
            elif operation == "read":
                if not os.path.exists(filepath):
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"文件不存在: {filepath}"
                    }
                    
                # Check file size
                if os.path.getsize(filepath) > 10 * 1024 * 1024:  # 10MB
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "File too large (>10MB)"
                    }
                    
                content = open(filepath, 'r', encoding=encoding).read()
                PrettyOutput.print(content, OutputType.INFO)
                return {
                    "success": True,
                    "stdout": content,
                    "stderr": ""
                }
                
            elif operation in ["write", "append"]:
                if not args.get("content"):
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "Write/append operation requires providing the content parameter"
                    }
                
                # Create directory (if it doesn't exist)
                os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
                    
                mode = 'a' if operation == "append" else 'w'
                with open(filepath, mode, encoding=encoding) as f:
                    f.write(args["content"])
                    
                return {
                    "success": True,
                    "stdout": f"Successfully {operation} content to {filepath}",
                    "stderr": ""
                }
                
            else:
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
                "stderr": f"File operation failed: {str(e)}"
            } 