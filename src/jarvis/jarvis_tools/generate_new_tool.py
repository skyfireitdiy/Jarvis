# -*- coding: utf-8 -*-
import re
from pathlib import Path
from typing import Any, Dict, Tuple

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
                "description": "新工具的名称，将用作文件名和工具类名"
            },
            "tool_code": {
                "type": "string",
                "description": "工具的完整Python代码，包含类定义、名称、描述、参数和execute方法"
            }
        },
        "required": ["tool_name", "tool_code"]
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
                PrettyOutput.print(f"无法创建工具目录 {tools_dir}: {e}", OutputType.ERROR)
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
                    "stderr": f"工具名称 '{tool_name}' 不是有效的Python标识符"
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
                    "stderr": f"工具 '{tool_name}' 已经存在于 {tool_file_path}"
                }
            
            # 验证并处理工具代码
            processed_code, error_msg = self._validate_and_process_code(tool_name, tool_code)
            if error_msg:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": error_msg
                }
            
            # 写入工具文件
            with open(tool_file_path, "w", encoding="utf-8") as f:
                f.write(processed_code)
            
            # 注册新工具到当前的工具注册表
            success_message = f"工具 '{tool_name}' 已成功生成在 {tool_file_path}"
            
            registration_successful = False
            if agent:
                tool_registry = agent.get_tool_registry()
                if tool_registry:
                    # 尝试加载并注册新工具
                    PrettyOutput.print(f"正在注册工具 '{tool_name}'...", OutputType.INFO)
                    if tool_registry.register_tool_by_file(str(tool_file_path)):
                        success_message += f"\n已成功注册到当前会话的工具注册表中"
                        registration_successful = True
                    else:
                        # 注册失败，删除已创建的文件
                        PrettyOutput.print(f"注册工具 '{tool_name}' 失败，正在删除文件...", OutputType.WARNING)
                        if tool_file_path.exists():
                            tool_file_path.unlink()
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": f"工具文件已生成，但注册失败。文件已被删除。"
                        }
                else:
                    PrettyOutput.print("未找到工具注册表，无法自动注册工具", OutputType.WARNING)
                    success_message += f"\n注册到当前会话失败，可能需要重新启动Jarvis"
            
            PrettyOutput.print(f"工具 '{tool_name}' 创建" + ("并注册" if registration_successful else "") + "成功！", OutputType.SUCCESS)
            return {
                "success": True,
                "stdout": success_message,
                "stderr": ""
            }
            
        except Exception as e:
            # 如果发生异常，删除已创建的文件并返回失败响应
            error_msg = f"生成工具失败: {str(e)}"
            PrettyOutput.print(error_msg, OutputType.ERROR)
            
            # 删除已创建的文件
            if tool_file_path and tool_file_path.exists():
                try:
                    PrettyOutput.print(f"正在删除已创建的文件 {tool_file_path}...", OutputType.INFO)
                    tool_file_path.unlink()
                    PrettyOutput.print(f"文件已删除", OutputType.SUCCESS)
                except Exception as delete_error:
                    PrettyOutput.print(f"删除文件失败: {str(delete_error)}", OutputType.ERROR)
            
            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg
            }
    
    def _validate_and_process_code(self, tool_name: str, tool_code: str) -> Tuple[str, str]:
        """
        验证并处理工具代码
        
        参数:
            tool_name: 工具名称
            tool_code: 工具代码
            
        返回:
            Tuple[str, str]: (处理后的代码, 错误信息)
        """
        # 检查工具代码中是否包含类定义
        if f"class {tool_name}" not in tool_code:
            # 尝试找到任何类定义
            class_match = re.search(r"class\s+(\w+)", tool_code)
            if class_match:
                old_class_name = class_match.group(1)
                # 替换类名为工具名
                tool_code = tool_code.replace(f"class {old_class_name}", f"class {tool_name}")
                tool_code = tool_code.replace(f'name = "{old_class_name}"', f'name = "{tool_name}"')
            else:
                # 没有找到类定义，返回错误
                return "", f"工具代码中缺少类定义 'class {tool_name}'"
        
        # 检查工具代码中是否包含必要的属性和方法
        missing_components = []
        
        if f'name = "{tool_name}"' not in tool_code and f"name = '{tool_name}'" not in tool_code:
            # 尝试查找任何name属性并修复
            name_match = re.search(r'name\s*=\s*["\'](\w+)["\']', tool_code)
            if name_match:
                old_name = name_match.group(1)
                tool_code = re.sub(r'name\s*=\s*["\'](\w+)["\']', f'name = "{tool_name}"', tool_code)
            else:
                missing_components.append(f"name = \"{tool_name}\"")
        
        if "description = " not in tool_code:
            missing_components.append("description 属性")
        
        if "parameters = " not in tool_code:
            missing_components.append("parameters 属性")
        
        if "def execute(self, args:" not in tool_code:
            missing_components.append("execute 方法")
        
        if "def check(" not in tool_code:
            # 添加默认的check方法
            class_match = re.search(r"class\s+(\w+).*?:", tool_code, re.DOTALL)
            if class_match:
                indent = "    "  # 默认缩进
                # 找到类定义后的第一个属性
                first_attr_match = re.search(r"class\s+(\w+).*?:(.*?)(\w+\s*=)", tool_code, re.DOTALL)
                if first_attr_match:
                    # 获取属性前的缩进
                    attr_indent = re.search(r"\n([ \t]*)\w+\s*=", first_attr_match.group(2))
                    if attr_indent:
                        indent = attr_indent.group(1)
                
                check_method = f"\n{indent}@staticmethod\n{indent}def check() -> bool:\n{indent}    \"\"\"检查工具是否可用\"\"\"\n{indent}    return True\n"
                
                # 在类定义后插入check方法
                pattern = r"(class\s+(\w+).*?:.*?)(\n\s*\w+\s*=|\n\s*@|\n\s*def)"
                replacement = r"\1" + check_method + r"\3"
                tool_code = re.sub(pattern, replacement, tool_code, 1, re.DOTALL)
        
        # 如果缺少必要组件，返回错误信息
        if missing_components:
            return "", f"工具代码中缺少以下必要组件: {', '.join(missing_components)}"
        
        # 确保代码有正确的Python文件头部
        if not tool_code.startswith("# -*- coding:") and not tool_code.startswith("# coding="):
            tool_code = "# -*- coding: utf-8 -*-\n" + tool_code
        
        # 确保导入了必要的模块
        if "from typing import Dict, Any" not in tool_code:
            imports_pos = tool_code.find("\n\n")
            if imports_pos > 0:
                tool_code = tool_code[:imports_pos] + "\nfrom typing import Dict, Any" + tool_code[imports_pos:]
            else:
                tool_code = "from typing import Dict, Any\n\n" + tool_code
        
        return tool_code, ""
