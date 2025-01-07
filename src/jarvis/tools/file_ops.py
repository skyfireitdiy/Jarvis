from typing import Dict, Any
import os
from pathlib import Path
from ..utils import PrettyOutput, OutputType

class FileOperationTool:
    name = "file_operation"
    description = "Execute file operations (read/write/append/exists)"
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
        """执行文件操作"""
        try:
            operation = args["operation"]
            filepath = args["filepath"]
            encoding = args.get("encoding", "utf-8")
            
            # 记录操作和完整路径
            abs_path = os.path.abspath(filepath)
            PrettyOutput.print(f"文件操作: {operation} - {abs_path}", OutputType.INFO)
            
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
                        "error": f"文件不存在: {filepath}"
                    }
                    
                # 检查文件大小
                if os.path.getsize(filepath) > 10 * 1024 * 1024:  # 10MB
                    return {
                        "success": False,
                        "error": "文件过大 (>10MB)"
                    }
                    
                with open(filepath, 'r', encoding=encoding) as f:
                    content = f.read()
                return {
                    "success": True,
                    "stdout": content,
                    "stderr": ""
                }
                
            elif operation in ["write", "append"]:
                if not args.get("content"):
                    return {
                        "success": False,
                        "error": "写入/追加操作需要提供content参数"
                    }
                
                # 创建目录（如果不存在）
                os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
                    
                mode = 'a' if operation == "append" else 'w'
                with open(filepath, mode, encoding=encoding) as f:
                    f.write(args["content"])
                    
                return {
                    "success": True,
                    "stdout": f"成功{operation}内容到 {filepath}",
                    "stderr": ""
                }
                
            else:
                return {
                    "success": False,
                    "error": f"未知操作: {operation}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"文件操作失败: {str(e)}"
            } 