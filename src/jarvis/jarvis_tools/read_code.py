from typing import Dict, Any, List
import os
from jarvis.jarvis_utils import OutputType, PrettyOutput


class ReadCodeTool:
    """Read multiple code files with line numbers"""
    
    name = "read_code"
    description = "Read multiple code files with line numbers"
    parameters = {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file"
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "Start line number (1-based, inclusive)",
                            "default": 1
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "End line number (1-based, inclusive). -1 means read to end",
                            "default": -1
                        }
                    },
                    "required": ["path"]
                },
                "description": "List of files to read"
            }
        },
        "required": ["files"]
    }

    def _read_single_file(self, filepath: str, start_line: int = 1, end_line: int = -1) -> Dict[str, Any]:
        """Read a single code file with line numbers
        
        Args:
            filepath: Path to the file
            start_line: Start line number (1-based, inclusive)
            end_line: End line number (1-based, inclusive). -1 means read to end
            
        Returns:
            Dict containing operation result
        """
        try:
            abs_path = os.path.abspath(filepath.strip())
            PrettyOutput.print(f"正在读取代码文件：{abs_path} [范围: [{start_line},{end_line}]]", OutputType.INFO)
            
            if not os.path.exists(abs_path):
                PrettyOutput.print(f"文件不存在: {abs_path}", OutputType.WARNING)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"File does not exist: {abs_path}"
                }
                
            if os.path.getsize(abs_path) > 10 * 1024 * 1024:  # 10MB
                PrettyOutput.print(f"文件太大: {abs_path}", OutputType.WARNING)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "File too large (>10MB)"
                }
                
            try:
                with open(abs_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                PrettyOutput.print(f"文件解码失败: {abs_path}", OutputType.WARNING)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Failed to decode file with UTF-8 encoding"
                }
            except Exception as e:
                PrettyOutput.print(f"读取文件失败: {abs_path}", OutputType.WARNING)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Failed to read file: {str(e)}"
                }
                
            total_lines = len(lines)
            
            # 处理特殊行号值
            # 转换负数索引 (Python风格)
            start_line = start_line if start_line >= 0 else total_lines + start_line + 1
            end_line = end_line if end_line >= 0 else total_lines + end_line + 1
            
            # 自动修正范围
            start_line = max(1, min(start_line, total_lines))
            end_line = max(1, min(end_line, total_lines))
            
            # 处理-1表示到末尾的情况
            if end_line == -1:
                end_line = total_lines
                
            # 最终验证
            if start_line > end_line:
                error_msg = f"无效的行范围 [{start_line}, {end_line}] (文件总行数: {total_lines})"
                PrettyOutput.print(error_msg, OutputType.WARNING)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": error_msg
                }
                
            formatted_lines = []
            for i, line in enumerate(lines[start_line - 1:end_line]):
                line_num = start_line + i
                formatted_lines.append(f"{line_num:>5}:{line}")
                
            content = "".join(formatted_lines)
            output = f"\n\nFile: {filepath}\nLines: [{start_line}, {end_line}]\n{content}"
            return {
                "success": True,
                "stdout": output,
                "stderr": ""
            }
            
        except Exception as e:
            PrettyOutput.print(f"读取代码失败: {filepath}", OutputType.WARNING)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to read code: {str(e)}"
            }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute code reading for multiple files
        
        Args:
            args: Dictionary containing:
                - files: List of file info with path and optional line range
                
        Returns:
            Dict containing:
                - success: Boolean indicating overall success
                - stdout: Combined output of all files as string
                - stderr: Error message if any
        """
        try:
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
                
                result = self._read_single_file(
                    file_info["path"],
                    file_info.get("start_line", 1),
                    file_info.get("end_line", -1)
                )
                
                if result["success"]:
                    all_outputs.append(result["stdout"])
                else:
                    all_outputs.append(f"Error reading {file_info['path']}: {result['stderr']}")
                success = success and result["success"]
            
            # Combine all outputs with separators
            combined_output = "\n\n" + "="*80 + "\n\n".join(all_outputs)
            
            return {
                "success": success,
                "stdout": combined_output,
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to read code files: {str(e)}"
            }
