from typing import Dict, Any
import os

from yaspin import yaspin

from jarvis.jarvis_utils.globals import add_read_file_record
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

class ReadCodeTool:
    name = "read_code"
    description = "代码阅读与分析工具，用于读取源代码文件并添加行号，针对代码文件优化，提供更好的格式化输出和行号显示，适用于代码分析、审查和理解代码实现的场景"
    # 工具标签
    parameters = {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "start_line": {"type": "number", "default": 1},
                        "end_line": {"type": "number", "default": -1}
                    },
                    "required": ["path"]
                },
                "description": "要读取的文件列表"
            }
        },
        "required": ["files"]
    }

    def _handle_single_file(self, filepath: str, start_line: int = 1, end_line: int = -1) -> Dict[str, Any]:
        """处理单个文件的读取操作

        Args:
            filepath (str): 文件路径
            start_line (int): 起始行号，默认为1
            end_line (int): 结束行号，默认为-1表示文件末尾

        Returns:
            Dict[str, Any]: 包含成功状态、输出内容和错误信息的字典
        """
        try:
            abs_path = os.path.abspath(filepath)
            add_read_file_record(abs_path)
            with yaspin(text=f"正在读取文件: {abs_path}...", color="cyan") as spinner:
                # 文件存在性检查
                if not os.path.exists(abs_path):
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"文件不存在: {abs_path}"
                    }

                # 文件大小限制检查（10MB）
                if os.path.getsize(abs_path) > 10 * 1024 * 1024:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "文件过大 (>10MB)"
                    }

                # 读取文件内容
                with open(abs_path, 'r', encoding='utf-8', errors="ignore") as f:
                    lines = f.readlines()

                total_lines = len(lines)

                # 处理特殊值-1表示文件末尾
                if end_line == -1:
                    end_line = total_lines
                else:
                    end_line = max(1, min(end_line, total_lines)) if end_line >= 0 else total_lines + end_line + 1

                start_line = max(1, min(start_line, total_lines)) if start_line >= 0 else total_lines + start_line + 1

                if start_line > end_line:
                    spinner.fail("❌")
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"无效的行范围 [{start_line}-{end_line}] (总行数: {total_lines})"
                    }

                # 添加行号并构建输出内容
                selected_lines = lines[start_line-1:end_line]
                numbered_content = "".join(
                    [f"{i:4d}:{line}"
                     for i, line in enumerate(selected_lines, start=start_line)]
                )

                # 构建输出格式
                output = (
                    f"\n🔍 文件: {abs_path}\n"
                    f"📄 原始行号: {start_line}-{end_line} (共{total_lines}行) \n\n"
                    f"{numbered_content}\n\n"
                )
                spinner.text = f"文件读取完成: {abs_path}"
                spinner.ok("✅")

                PrettyOutput.print(output, OutputType.SUCCESS)

                return {
                    "success": True,
                    "stdout": output,
                    "stderr": ""
                }

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"文件读取失败: {str(e)}"
            }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """执行代码读取操作

        Args:
            args (Dict): 包含文件列表的参数字典

        Returns:
            Dict[str, Any]: 包含成功状态、输出内容和错误信息的字典
        """
        try:
            if "files" not in args or not isinstance(args["files"], list):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "参数中必须包含文件列表"
                }

            all_outputs = []
            overall_success = True

            for file_info in args["files"]:
                if not isinstance(file_info, dict) or "path" not in file_info:
                    continue

                result = self._handle_single_file(
                    file_info["path"].strip(),
                    file_info.get("start_line", 1),
                    file_info.get("end_line", -1)
                )

                if result["success"]:
                    all_outputs.append(result["stdout"])
                else:
                    all_outputs.append(f"❌ {file_info['path']}: {result['stderr']}")
                    overall_success = False

            return {
                "success": overall_success,
                "stdout": "\n".join(all_outputs),
                "stderr": ""
            }

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"代码读取失败: {str(e)}"
            }
