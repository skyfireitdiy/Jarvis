from typing import Dict, Any
import os
from pathlib import Path

from yaspin import yaspin # type: ignore

from jarvis.jarvis_utils.globals import add_read_file_record
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
# 导入文件处理器
from jarvis.jarvis_utils.file_processors import (
    TextFileProcessor
)



class FileOperationTool:
    name = "file_operation"
    description = "文件批量操作工具，可批量读写多个文件，仅支持文本文件，适用于需要同时处理多个文件的场景（读取配置文件、保存生成内容等）"
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

    def _get_file_processor(self, file_path: str):
        """获取适合处理指定文件的处理器"""
        processors = [
            TextFileProcessor  # 文本文件处理器(放在最后作为兜底)
        ]
        
        for processor in processors:
            if processor.can_handle(file_path):
                return processor
        
        return None  # 如果没有合适的处理器，返回None
    
    def _handle_single_file(self, operation: str, filepath: str, content: str = "",
                          start_line: int = 1, end_line: int = -1) -> Dict[str, Any]:
        """Handle operations for a single file"""
        try:
            abs_path = os.path.abspath(filepath)
            add_read_file_record(abs_path)
            
            if operation == "read":
                with yaspin(text=f"正在读取文件: {abs_path}...", color="cyan") as spinner:
                    if not os.path.exists(abs_path):
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": f"文件不存在: {abs_path}"
                        }

                    # 检查文件大小
                    if os.path.getsize(abs_path) > 30 * 1024 * 1024:  # 30MB
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": "文件过大 (>30MB)，无法处理"
                        }
                    
                    file_extension = Path(abs_path).suffix.lower()
                    
                    # 获取文件处理器
                    processor = self._get_file_processor(abs_path)
                    
                    if processor is None:
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": f"不支持的文件类型: {file_extension}"
                        }
                    
                    # 特殊处理纯文本文件，支持行范围选择
                    if processor == TextFileProcessor:
                        try:
                            with open(abs_path, 'r', encoding='utf-8', errors="ignore") as f:
                                lines = f.readlines()

                            total_lines = len(lines)
                            start_line = start_line if start_line >= 0 else total_lines + start_line + 1
                            end_line = end_line if end_line >= 0 else total_lines + end_line + 1
                            start_line = max(1, min(start_line, total_lines))
                            end_line = max(1, min(end_line, total_lines))
                            if end_line == -1:
                                end_line = total_lines

                            if start_line > end_line:
                                spinner.text = "无效的行范围"
                                spinner.fail("❌")
                                error_msg = f"无效的行范围 [{start_line, end_line}] (文件总行数: {total_lines})"
                                return {
                                    "success": False,
                                    "stdout": "",
                                    "stderr": error_msg
                                }

                            content = "".join(lines[start_line - 1:end_line])
                            file_info = f"\n文件: {abs_path} (文本文件)\n行: [{start_line}-{end_line}]/{total_lines}"
                        except Exception as e:
                            return {
                                "success": False,
                                "stdout": "",
                                "stderr": f"读取文本文件失败: {str(e)}"
                            }
                    else:
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": f"不支持的文件类型: {file_extension}"
                        }
                    
                    # 构建输出信息
                    output = f"{file_info}\n{content}" + "\n\n"
                    
                    spinner.text = f"文件读取完成: {abs_path}"
                    spinner.ok("✅")
                    return {
                        "success": True,
                        "stdout": output,
                        "stderr": ""
                    }
            elif operation == "write":
                with yaspin(text=f"正在写入文件: {abs_path}...", color="cyan") as spinner:
                    os.makedirs(os.path.dirname(os.path.abspath(abs_path)), exist_ok=True)
                    with open(abs_path, 'w', encoding='utf-8', errors="ignore") as f:
                        f.write(content)
                    spinner.text = f"文件写入完成: {abs_path}"
                    spinner.ok("✅")
                    return {
                        "success": True,
                        "stdout": f"文件写入成功: {abs_path}",
                        "stderr": ""
                    }
            return {
                "success": False,
                "stdout": "",
                "stderr": f"未知操作: {operation}"
            }

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"文件操作失败 {abs_path}: {str(e)}"
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
                    "stderr": "files参数是必需的，且必须是一个列表"
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
                    all_outputs.append(f"处理文件 {file_info['path']} 时出错: {result['stderr']}")
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
                "stderr": f"文件操作失败: {str(e)}"
            }
