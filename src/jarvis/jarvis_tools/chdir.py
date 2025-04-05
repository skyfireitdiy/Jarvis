from typing import Dict, Any
import os

class ChdirTool:
    name = "chdir"
    description = "更改当前工作目录"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要切换到的目录路径，支持相对路径和绝对路径"
            }
        },
        "required": ["path"]
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行目录切换操作，并提供全面的错误处理。

        参数:
            args: 包含 'path' 键的字典，目标目录路径

        返回:
            字典，包含以下内容：
                - success: 布尔值，表示操作状态
                - stdout: 成功消息或空字符串
                - stderr: 错误消息或空字符串

        异常处理:
            处理并返回适当的错误消息：
                - 不存在的路径
                - 非目录路径
                - 权限错误
                - 其他通用异常
        """
        # 主执行块，包含全面的错误处理
        try:
            # 规范化并展开输入路径（处理 ~ 和相对路径）
            path = os.path.expanduser(args["path"].strip())
            path = os.path.abspath(path)

            # 验证目标路径是否存在
            if not os.path.exists(path):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"目录不存在: {path}"
                }

            # 确保路径指向的是目录，而不是文件
            if not os.path.isdir(path):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"路径不是目录: {path}"
                }

            # 获取当前目录并尝试切换到新路径
            old_path = os.getcwd()
            os.chdir(path)

            return {
                "success": True,
                "stdout": f"成功切换工作目录:\n原目录: {old_path}\n新目录: {path}",
                "stderr": ""
            }

        # 处理用户没有目录访问权限的情况
        except PermissionError:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"无权限访问目录: {path}"
            }
        # 捕获在目录切换过程中可能出现的其他意外错误
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"切换目录失败: {str(e)}"
            }
