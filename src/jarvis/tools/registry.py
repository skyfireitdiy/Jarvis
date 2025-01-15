
import importlib
import json
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Optional

from jarvis.models.registry import PlatformRegistry
from jarvis.tools.base import Tool
from jarvis.utils import OutputType, PrettyOutput


class ToolRegistry:
    global_tool_registry = None # type: ignore
    def __init__(self):
        """初始化工具注册器
        """
        self.tools: Dict[str, Tool] = {}
        # 加载内置工具和外部工具
        self._load_builtin_tools()
        self._load_external_tools()

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
                
            self.register_tool_by_file(file_path)

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
                
            self.register_tool_by_file(file_path)

    def register_tool_by_file(self, file_path: str):
        """从指定文件加载并注册工具
        
        Args:
            file_path: 工具文件的路径
            
        Returns:
            bool: 是否成功加载工具
        """
        try:
            file_path = Path(file_path).resolve()  # 获取绝对路径
            if not file_path.exists() or not file_path.is_file():
                PrettyOutput.print(f"文件不存在: {file_path}", OutputType.ERROR)
                return False
                
            # 动态导入模块
            module_name = file_path.stem
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if not spec or not spec.loader:
                PrettyOutput.print(f"无法加载模块: {file_path}", OutputType.ERROR)
                return False
                
            module = importlib.util.module_from_spec(spec)
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
                    PrettyOutput.print(f"从 {file_path} 加载工具: {tool_instance.name}: {tool_instance.description}", OutputType.INFO)
                    tool_found = True
                    
            if not tool_found:
                PrettyOutput.print(f"文件中未找到有效的工具类: {file_path}", OutputType.WARNING)
                return False
                
            return True
            
        except Exception as e:
            PrettyOutput.print(f"加载工具失败 {file_path.name}: {str(e)}", OutputType.ERROR)
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
            else:
                error_msg = result["error"]
                output = f"执行失败: {error_msg}"
                PrettyOutput.section("执行失败", OutputType.ERROR)
                
            return output
        except Exception as e:
            PrettyOutput.print(f"执行工具失败: {str(e)}", OutputType.ERROR)
            return f"Tool call failed: {str(e)}"
