from typing import Dict, Any, List
import os
from jarvis.utils import OutputType, PrettyOutput


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
                            "description": "Start line number (0-based, inclusive)",
                            "default": 0
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "End line number (0-based, exclusive). -1 means read to end",
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

    def _read_single_file(self, filepath: str, start_line: int = 0, end_line: int = -1) -> Dict[str, Any]:
        """Read a single code file with line numbers
        
        Args:
            filepath: Path to the file
            start_line: Start line number (0-based, inclusive)
            end_line: End line number (0-based, exclusive). -1 means read to end
            
        Returns:
            Dict containing operation result
        """
        try:
            abs_path = os.path.abspath(filepath)
            PrettyOutput.print(f"正在读取代码文件：{abs_path}", OutputType.INFO)
            
            if not os.path.exists(filepath):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"File does not exist: {filepath}"
                }
                
            if os.path.getsize(filepath) > 10 * 1024 * 1024:  # 10MB
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "File too large (>10MB)"
                }
                
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Failed to decode file with UTF-8 encoding"
                }
                
            if start_line < 0:
                start_line = 0
            if end_line == -1 or end_line > len(lines):
                end_line = len(lines)
            if start_line >= end_line:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Invalid line range: [{start_line}, {end_line})"
                }
                
            formatted_lines = []
            for i, line in enumerate(lines[start_line:end_line]):
                line_num = start_line + i
                formatted_lines.append(f"{line_num:>5}:{line}")
                
            content = "".join(formatted_lines)
            output = f"File: {filepath}\nLines: [{start_line}, {end_line})\n{content}"
            
            return {
                "success": True,
                "stdout": output,
                "stderr": ""
            }
            
        except Exception as e:
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
                    file_info.get("start_line", 0),
                    file_info.get("end_line", -1)
                )
                
                if result["success"]:
                    all_outputs.append(result["stdout"])
                    PrettyOutput.print(result["stdout"], OutputType.CODE)
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
