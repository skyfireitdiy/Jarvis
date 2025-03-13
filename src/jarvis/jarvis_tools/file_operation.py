from typing import Dict, Any
import os

from jarvis.jarvis_utils.output import OutputType, PrettyOutput



class FileOperationTool:
    name = "file_operation"
    description = "用于读写多个文件的操作工具"
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["read", "write"],
                "description": "要执行的文件操作类型（读取或写入多个文件）"
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
                "description": "要操作的文件列表"
            }
        },
        "required": ["operation", "files"]
    }

    def _handle_single_file(self, operation: str, filepath: str, content: str = "", 
                          start_line: int = 1, end_line: int = -1) -> Dict[str, Any]:
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
                    
                with open(abs_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # Handle line range
                total_lines = len(lines)
                start_line = start_line if start_line >= 0 else total_lines + start_line + 1
                end_line = end_line if end_line >= 0 else total_lines + end_line + 1
                start_line = max(1, min(start_line, total_lines))
                end_line = max(1, min(end_line, total_lines))
                if end_line == -1:
                    end_line = total_lines
                
                if start_line > end_line:
                    error_msg = f"无效的行范围 [{start_line, end_line}] (文件总行数: {total_lines})"
                    PrettyOutput.print(error_msg, OutputType.WARNING)
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": error_msg
                    }
                
                content = "".join(lines[start_line - 1:end_line])
                output = f"\文件: {abs_path}\行: [{start_line}-{end_line}]\n{content}" + "\n\n" + "="*80 + "\n\n"
                
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
                result = self._handle_single_file(
                    operation,
                    file_info["path"].strip(),
                    content,
                    file_info.get("start_line", 1),
                    file_info.get("end_line", -1)
                )
                
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
