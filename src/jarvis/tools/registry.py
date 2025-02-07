import importlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Optional

from jarvis.models.registry import PlatformRegistry
from jarvis.tools.base import Tool
from jarvis.utils import OutputType, PrettyOutput, get_max_context_length


class ToolRegistry:
    global_tool_registry = None # type: ignore
    def __init__(self):
        """初始化工具注册器
        """
        self.tools: Dict[str, Tool] = {}
        # 加载内置工具和外部工具
        self._load_builtin_tools()
        self._load_external_tools()
        # 确保 max_context_length 是整数
        self.max_context_length = int(get_max_context_length() * 0.8)

    @staticmethod
    def get_global_tool_registry():
        """获取全局工具注册器"""
        if ToolRegistry.global_tool_registry is None:
            ToolRegistry.global_tool_registry = ToolRegistry()
        return ToolRegistry.global_tool_registry

    def _load_builtin_tools(self):
        """从内置tools目录加载工具"""
        tools_dir = Path(__file__).parent
        
        # 遍历目录下的所有.py文件
        for file_path in tools_dir.glob("*.py"):
            # 跳过基础文件和__init__.py
            if file_path.name in ["base.py", "__init__.py", "registry.py"]:
                continue
                
            self.register_tool_by_file(str(file_path))

    def _load_external_tools(self):
        """从~/.jarvis_tools加载外部工具"""
        external_tools_dir = Path.home() / '.jarvis_tools'
        if not external_tools_dir.exists():
            return
            
        # 遍历目录下的所有.py文件
        for file_path in external_tools_dir.glob("*.py"):
            # 跳过__init__.py
            if file_path.name == "__init__.py":
                continue
                
            self.register_tool_by_file(str(file_path))

    def register_tool_by_file(self, file_path: str):
        """从指定文件加载并注册工具
        
        Args:
            file_path: 工具文件的路径
            
        Returns:
            bool: 是否成功加载工具
        """
        try:
            p_file_path = Path(file_path).resolve()  # 获取绝对路径
            if not p_file_path.exists() or not p_file_path.is_file():
                PrettyOutput.print(f"文件不存在: {p_file_path}", OutputType.ERROR)
                return False
                
            # 动态导入模块
            module_name = p_file_path.stem
            spec = importlib.util.spec_from_file_location(module_name, p_file_path) # type: ignore
            if not spec or not spec.loader:
                PrettyOutput.print(f"无法加载模块: {p_file_path}", OutputType.ERROR)
                return False
                
            module = importlib.util.module_from_spec(spec) # type: ignore
            sys.modules[module_name] = module  # 添加到 sys.modules 以支持相对导入
            spec.loader.exec_module(module)
            
            # 查找模块中的工具类
            tool_found = False
            for item_name in dir(module):
                item = getattr(module, item_name)
                # 检查是否是类，并且有必要的属性
                if (isinstance(item, type) and 
                    hasattr(item, 'name') and 
                    hasattr(item, 'description') and 
                    hasattr(item, 'parameters')):
                    
                    # 实例化工具类，传入模型和输出处理器
                    tool_instance = item()
                    
                    # 注册工具
                    self.register_tool(
                        name=tool_instance.name,
                        description=tool_instance.description,
                        parameters=tool_instance.parameters,
                        func=tool_instance.execute
                    )
                    PrettyOutput.print(f"从 {p_file_path} 加载工具: {tool_instance.name}: {tool_instance.description}", OutputType.SUCCESS)
                    tool_found = True
                    break
                    
            if not tool_found:
                PrettyOutput.print(f"文件中未找到有效的工具类: {p_file_path}", OutputType.WARNING)
                return False
                
            return True
            
        except Exception as e:
            PrettyOutput.print(f"加载工具失败 {p_file_path.name}: {str(e)}", OutputType.ERROR)
            return False

    def register_tool(self, name: str, description: str, parameters: Dict, func: Callable):
        """注册新工具"""
        self.tools[name] = Tool(name, description, parameters, func)

    def get_tool(self, name: str) -> Optional[Tool]:
        """获取工具"""
        return self.tools.get(name)

    def get_all_tools(self) -> List[Dict]:
        """获取所有工具的Ollama格式定义"""
        return [tool.to_dict() for tool in self.tools.values()]

    def execute_tool(self, name: str, arguments: Dict) -> Dict[str, Any]:
        """执行指定工具"""
        tool = self.get_tool(name)
        if tool is None:
            return {"success": False, "error": f"Tool {name} does not exist"}
        return tool.execute(arguments)

    def handle_tool_calls(self, tool_calls: List[Dict]) -> str:
        """处理工具调用，只处理第一个工具"""
        try:
            if not tool_calls:
                return ""
                
            # 只处理第一个工具调用
            tool_call = tool_calls[0]
            name = tool_call["name"]
            args = tool_call["arguments"]
            
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    PrettyOutput.print(f"工具参数格式无效: {name}", OutputType.ERROR)
                    return ""

            # 显示工具调用信息
            PrettyOutput.section(f"执行工具: {name}", OutputType.TOOL)
            if isinstance(args, dict):
                for key, value in args.items():
                    PrettyOutput.print(f"参数: {key} = {value}", OutputType.DEBUG)
            else:
                PrettyOutput.print(f"参数: {args}", OutputType.DEBUG)
            
            # 执行工具调用
            result = self.execute_tool(name, args)
            
            # 处理结果
            if result["success"]:
                stdout = result["stdout"]
                stderr = result.get("stderr", "")
                output_parts = []
                if stdout:
                    output_parts.append(f"输出:\n{stdout}")
                if stderr:
                    output_parts.append(f"错误:\n{stderr}")
                output = "\n\n".join(output_parts)
                output = "没有输出和错误" if not output else output
                PrettyOutput.section("执行成功", OutputType.SUCCESS)
                
                # 如果输出超过4k字符，使用大模型总结
                if len(output) > self.max_context_length:
                    try:
                        PrettyOutput.print("输出较长，正在总结...", OutputType.PROGRESS)
                        model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
                        
                        # 如果输出超过最大上下文长度，只取最后部分
                        max_len = self.max_context_length
                        if len(output) > max_len:
                            output_to_summarize = output[-max_len:]
                            truncation_notice = f"\n(注意: 由于输出过长，仅总结最后{max_len}字符)"
                        else:
                            output_to_summarize = output
                            truncation_notice = ""

                        prompt = f"""请总结以下工具执行结果，提取关键信息和重要结果。注意：
1. 保留所有重要的数值、路径、错误信息等关键数据
2. 保持结果的准确性
3. 用简洁的语言描述主要内容
4. 如果有错误信息，确保包含在总结中

工具名称: {name}
执行结果:
{output_to_summarize}

请提供总结："""

                        summary = model.chat_until_success(prompt)
                        output = f"""--- 原始输出较长，以下是总结 ---{truncation_notice}

{summary}

--- 总结结束 ---"""
                        
                    except Exception as e:
                        PrettyOutput.print(f"总结失败: {str(e)}", OutputType.ERROR)
                        output = f"输出较长 ({len(output)} 字符)，建议查看原始输出。\n前300字符预览:\n{output[:300]}..."
            
            else:
                error_msg = result["error"]
                output = f"执行失败: {error_msg}"
                PrettyOutput.section("执行失败", OutputType.ERROR)
                
            return output
            
        except Exception as e:
            PrettyOutput.print(f"执行工具失败: {str(e)}", OutputType.ERROR)
            return f"Tool call failed: {str(e)}"
