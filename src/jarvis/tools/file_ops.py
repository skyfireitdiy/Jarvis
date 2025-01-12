from typing import Dict, Any, Protocol, Optional
import os
from pathlib import Path
from enum import Enum

class OutputType(Enum):
    INFO = "info"
    ERROR = "error"

class OutputHandler(Protocol):
    def print(self, text: str, output_type: OutputType) -> None: ...

class ModelHandler(Protocol):
    def chat(self, message: str) -> str: ...

class FileOperationTool:
    name = "file_operation"
    description = "文件操作 (read/write/append/exists)"
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

    def __init__(self, **kwargs):
        self.output = kwargs.get('output_handler')

    def _print(self, text: str, output_type: OutputType = OutputType.INFO):
        """输出信息"""
        if self.output:
            self.output.print(text, output_type)

    def execute(self, args: Dict) -> Dict[str, Any]:
        """执行文件操作"""
        try:
            operation = args["operation"]
            filepath = args["filepath"]
            encoding = args.get("encoding", "utf-8")
            
            # 记录操作和完整路径
            abs_path = os.path.abspath(filepath)
            self._print(f"文件操作: {operation} - {abs_path}")
            
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
            self._print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "error": f"文件操作失败: {str(e)}"
            } 