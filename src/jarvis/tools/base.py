from typing import Dict, Any, List, Optional, Callable
import json
from ..utils import PrettyOutput, OutputType
from ..models import BaseModel

class Tool:
    def __init__(self, name: str, description: str, parameters: Dict, func: Callable):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func

    def to_dict(self) -> Dict:
        """转换为Ollama工具格式"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": json.dumps(self.parameters)
        }

    def execute(self, arguments: Dict) -> Dict[str, Any]:
        """执行工具函数"""
        return self.func(arguments)

class ToolRegistry:
    def __init__(self, model: BaseModel):
        self.tools: Dict[str, Tool] = {}
        self.model = model
        self._register_default_tools()

    def _register_default_tools(self):
        """注册所有默认工具"""
        from .search import SearchTool
        from .shell import ShellTool
        from .file_ops import FileOperationTool
        from .webpage import WebpageTool
        from .sub_agent import SubAgentTool

        tools = [
            SearchTool(),
            ShellTool(),
            FileOperationTool(),
            WebpageTool(),
        ]

        for tool in tools:
            self.register_tool(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
                func=tool.execute
            )

        sub_agent_tool = SubAgentTool(self.model)
        self.register_tool(
            name=sub_agent_tool.name,
            description=sub_agent_tool.description,
            parameters=sub_agent_tool.parameters,
            func=sub_agent_tool.execute
        )

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
