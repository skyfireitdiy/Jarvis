# -*- coding: utf-8 -*-
from pathlib import Path
from typing import Any, Dict

from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class generate_new_tool:
    name = "generate_new_tool"
    description = """
    生成并注册新的Jarvis工具。该工具会在用户数据目录下创建新的工具文件，
    并自动注册到当前的工具注册表中。适用场景：1. 需要创建新的自定义工具；
    2. 扩展Jarvis功能；3. 自动化重复性操作；4. 封装特定领域的功能。
    """

    parameters = {
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "新工具的名称，将用作文件名和工具类名",
            },
            "tool_code": {
                "type": "string",
                "description": "工具的完整Python代码，包含类定义、名称、描述、参数和execute方法",
            },
        },
        "required": ["tool_name", "tool_code"],
    }

    @staticmethod
    def check() -> bool:
        """检查工具是否可用"""
        # 检查数据目录是否存在
        data_dir = get_data_dir()
        tools_dir = Path(data_dir) / "tools"

        # 如果tools目录不存在，尝试创建
        if not tools_dir.exists():
            try:
                tools_dir.mkdir(parents=True, exist_ok=True)
                return True
            except Exception as e:
                PrettyOutput.print(
                    f"无法创建工具目录 {tools_dir}: {e}", OutputType.ERROR
                )
                return False

        return True

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成新工具并注册到当前的工具注册表中

        参数:
            args: 包含工具名称和工具代码的字典

        返回:
            Dict: 包含生成结果的字典
        """
        tool_file_path = None
        try:
            # 从参数中获取工具信息
            tool_name = args["tool_name"]
            tool_code = args["tool_code"]
            agent = args.get("agent", None)

            # 验证工具名称
            if not tool_name.isidentifier():
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"工具名称 '{tool_name}' 不是有效的Python标识符",
                }

            # 准备工具目录
            tools_dir = Path(get_data_dir()) / "tools"
            tools_dir.mkdir(parents=True, exist_ok=True)

            # 生成工具文件路径
            tool_file_path = tools_dir / f"{tool_name}.py"

            # 检查是否已存在同名工具
            if tool_file_path.exists():
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"工具 '{tool_name}' 已经存在于 {tool_file_path}",
                }

            # 写入工具文件
            with open(tool_file_path, "w", encoding="utf-8") as f:
                f.write(tool_code)

            # 注册新工具到当前的工具注册表
            success_message = f"工具 '{tool_name}' 已成功生成在 {tool_file_path}"

            registration_successful = False
            if agent:
                tool_registry = agent.get_tool_registry()
                if tool_registry:
                    # 尝试加载并注册新工具
                    PrettyOutput.print(
                        f"正在注册工具 '{tool_name}'...", OutputType.INFO
                    )
                    if tool_registry.register_tool_by_file(str(tool_file_path)):
                        success_message += f"\n已成功注册到当前会话的工具注册表中"
                        registration_successful = True
                    else:
                        # 注册失败，删除已创建的文件
                        PrettyOutput.print(
                            f"注册工具 '{tool_name}' 失败，正在删除文件...",
                            OutputType.WARNING,
                        )
                        if tool_file_path.exists():
                            tool_file_path.unlink()
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": f"工具文件已生成，但注册失败。文件已被删除。",
                        }
                else:
                    PrettyOutput.print(
                        "未找到工具注册表，无法自动注册工具", OutputType.WARNING
                    )
                    success_message += f"\n注册到当前会话失败，可能需要重新启动Jarvis"

            PrettyOutput.print(
                f"工具 '{tool_name}' 创建"
                + ("并注册" if registration_successful else "")
                + "成功！",
                OutputType.SUCCESS,
            )

            # 检查并安装缺失的依赖
            try:
                required_packages = set()

                # 从代码中提取import语句
                for line in tool_code.split("\n"):
                    if line.strip().startswith("import "):
                        # 处理 import a.b.c 形式
                        pkg = line.split()[1].split(".")[0]
                        required_packages.add(pkg)
                    elif line.strip().startswith("from "):
                        # 处理 from a.b.c import d 形式
                        parts = line.split()
                        if (
                            len(parts) >= 4
                            and parts[0] == "from"
                            and parts[2] == "import"
                        ):
                            pkg = parts[1].split(".")[0]
                            required_packages.add(pkg)

                # 检查并安装缺失的包
                for pkg in required_packages:
                    try:
                        __import__(pkg)
                    except ImportError:
                        PrettyOutput.print(
                            f"检测到缺失依赖: {pkg}, 正在尝试安装...", OutputType.INFO
                        )
                        import subprocess

                        subprocess.run(["pip", "install", pkg], check=True)
                        PrettyOutput.print(f"成功安装依赖: {pkg}", OutputType.SUCCESS)
            except Exception as e:
                PrettyOutput.print(f"依赖检查/安装失败: {str(e)}", OutputType.WARNING)

            return {"success": True, "stdout": success_message, "stderr": ""}

        except Exception as e:
            # 如果发生异常，删除已创建的文件并返回失败响应
            error_msg = f"生成工具失败: {str(e)}"
            PrettyOutput.print(error_msg, OutputType.ERROR)

            # 删除已创建的文件
            if tool_file_path and tool_file_path.exists():
                try:
                    PrettyOutput.print(
                        f"正在删除已创建的文件 {tool_file_path}...", OutputType.INFO
                    )
                    tool_file_path.unlink()
                    PrettyOutput.print(f"文件已删除", OutputType.SUCCESS)
                except Exception as delete_error:
                    PrettyOutput.print(
                        f"删除文件失败: {str(delete_error)}", OutputType.ERROR
                    )

            return {"success": False, "stdout": "", "stderr": error_msg}
