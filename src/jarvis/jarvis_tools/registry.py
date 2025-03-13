import json
from pathlib import Path
import re
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

from jarvis.jarvis_agent.output_handler import OutputHandler
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.base import Tool
from jarvis.jarvis_utils.config import get_max_token_count
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.output import OutputType, PrettyOutput



tool_call_help = """
# 🛠️ 工具使用系统
您正在使用一个需要精确格式和严格规则的工具执行系统。

# 📋 工具调用格式
<TOOL_CALL>
name: 工具名称
arguments:
    param1: 值1
    param2: 值2
</TOOL_CALL>

# ❗ 关键规则
1. 每次只使用一个工具
   - 一次只执行一个工具
   - 等待结果后再进行下一步

2. 严格遵守格式
   - 完全按照上述格式
   - 使用正确的YAML缩进
   - 包含所有必需参数

3. 结果处理
   - 等待执行结果
   - 不要假设结果
   - 不要创建虚假响应
   - 不要想象对话

4. 信息管理
   - 如果信息不足，询问用户
   - 跳过不必要的步骤
   - 如果卡住，请求指导
   - 不要在没有完整信息的情况下继续

# 📝 字符串参数格式
始终使用 | 语法表示字符串参数：

<TOOL_CALL>
name: execute_shell
arguments:
    command: |
        git status --porcelain
</TOOL_CALL>

# 💡 最佳实践
- 准备好后立即开始执行
- 无需请求许可即可开始
- 使用正确的字符串格式
- 监控进度并调整
- 遇到困难时请求帮助

# ⚠️ 常见错误
- 同时调用多个工具
- 字符串参数缺少 |
- 假设工具结果
- 创建虚构对话
- 在没有所需信息的情况下继续
"""

class ToolRegistry(OutputHandler):

    def name(self) -> str:
        return "TOOL_CALL"

    def can_handle(self, response: str) -> bool:
        if self._extract_tool_calls(response):
            return True
        return False
    
    def prompt(self) -> str:
        """加载工具"""
        tools = self.get_all_tools()
        if tools:
            tools_prompt = "## 可用工具:\n"
            for tool in tools:
                tools_prompt += f"- 名称: {tool['name']}\n"
                tools_prompt += f"  描述: {tool['description']}\n"
                tools_prompt += f"  参数: {tool['parameters']}\n"
            tools_prompt += tool_call_help
            return tools_prompt
        return ""
    
    def handle(self, response: str) -> Tuple[bool, Any]:
        tool_calls = self._extract_tool_calls(response)
        if len(tool_calls) > 1:
            PrettyOutput.print(f"操作失败：检测到多个操作。一次只能执行一个操作。尝试执行的操作：{', '.join([tool_call['name'] for tool_call in tool_calls])}", OutputType.WARNING)
            return False, f"调用失败：请一次只处理一个工具调用。"
        if len(tool_calls) == 0:
            return False, ""
        tool_call = tool_calls[0]
        return False, self.handle_tool_calls(tool_call)

    def __init__(self):
        """初始化工具注册表"""
        self.tools: Dict[str, Tool] = {}
        # 加载内置工具和外部工具
        self._load_builtin_tools()
        self._load_external_tools()
        # 确保max_token_count是整数
        self.max_token_count = int(get_max_token_count() * 0.8)

    def use_tools(self, name: List[str]):
        """使用指定工具"""
        missing_tools = [tool_name for tool_name in name if tool_name not in self.tools]
        if missing_tools:
            PrettyOutput.print(f"工具 {missing_tools} 不存在，可用的工具有: {', '.join(self.tools.keys())}", OutputType.WARNING)
        self.tools = {tool_name: self.tools[tool_name] for tool_name in name}

    def dont_use_tools(self, names: List[str]):
        """从注册表中移除指定工具"""
        self.tools = {name: tool for name, tool in self.tools.items() if name not in names}

    def _load_builtin_tools(self):
        """从内置工具目录加载工具"""
        tools_dir = Path(__file__).parent
        
        # 遍历目录中的所有.py文件
        for file_path in tools_dir.glob("*.py"):
            # 跳过base.py和__init__.py
            if file_path.name in ["base.py", "__init__.py", "registry.py"]:
                continue
                
            self.register_tool_by_file(str(file_path))

    def _load_external_tools(self):
        """从~/.jarvis/tools加载外部工具"""
        external_tools_dir = Path.home() / '.jarvis/tools'
        if not external_tools_dir.exists():
            return
            
        # 遍历目录中的所有.py文件
        for file_path in external_tools_dir.glob("*.py"):
            # 跳过__init__.py
            if file_path.name == "__init__.py":
                continue
                
            self.register_tool_by_file(str(file_path))

    def register_tool_by_file(self, file_path: str):
        """从指定文件加载并注册工具
        
        参数:
            file_path: 工具文件的路径
            
        返回:
            bool: 工具是否加载成功
        """
        try:
            p_file_path = Path(file_path).resolve()  # 获取绝对路径
            if not p_file_path.exists() or not p_file_path.is_file():
                PrettyOutput.print(f"文件不存在: {p_file_path}", OutputType.ERROR)
                return False
                
            # 临时将父目录添加到sys.path
            parent_dir = str(p_file_path.parent)
            sys.path.insert(0, parent_dir)
            
            try:
                # 使用标准导入机制导入模块
                module_name = p_file_path.stem
                module = __import__(module_name)
                
                # 在模块中查找工具类
                tool_found = False
                for item_name in dir(module):
                    item = getattr(module, item_name)
                    # 检查是否是类并具有必要属性
                    if (isinstance(item, type) and 
                        hasattr(item, 'name') and 
                        hasattr(item, 'description') and 
                        hasattr(item, 'parameters') and
                        hasattr(item, 'execute') and 
                        item.name == module_name):

                        if hasattr(item, "check"):
                            if not item.check():
                                continue
                        
                        # 实例化工具类
                        tool_instance = item()
                        
                        # 注册工具
                        self.register_tool(
                            name=tool_instance.name,
                            description=tool_instance.description,
                            parameters=tool_instance.parameters,
                            func=tool_instance.execute
                        )
                        tool_found = True
                        break
                        
                if not tool_found:
                    return False
                    
                return True
                
            finally:
                # 从sys.path中移除目录
                sys.path.remove(parent_dir)
                
        except Exception as e:
            PrettyOutput.print(f"从 {Path(file_path).name} 加载工具失败: {str(e)}", OutputType.ERROR)
            return False
    @staticmethod
    def _extract_tool_calls(content: str) -> List[Dict]:
        """从内容中提取工具调用。
        
        参数:
            content: 包含工具调用的内容
            
        返回:
            List[Dict]: 包含名称和参数的提取工具调用列表
            
        异常:
            Exception: 如果工具调用缺少必要字段
        """
        # 将内容拆分为行
        data = re.findall(r'<TOOL_CALL>(.*?)</TOOL_CALL>', content, re.DOTALL)
        ret = []
        for item in data:
            try:
                msg = yaml.safe_load(item)
                if 'name' in msg and 'arguments' in msg:
                    ret.append(msg)
            except Exception as e:
                continue
        return ret

    def register_tool(self, name: str, description: str, parameters: Dict, func: Callable):
        """注册新工具"""
        self.tools[name] = Tool(name, description, parameters, func)

    def get_tool(self, name: str) -> Optional[Tool]:
        """获取工具"""
        return self.tools.get(name)

    def get_all_tools(self) -> List[Dict]:
        """获取所有工具（Ollama格式定义）"""
        return [tool.to_dict() for tool in self.tools.values()]

    def execute_tool(self, name: str, arguments: Dict) -> Dict[str, Any]:
        """执行指定工具"""
        tool = self.get_tool(name)
        if tool is None:
            return {"success": False, "stderr": f"工具 {name} 不存在，可用的工具有: {', '.join(self.tools.keys())}", "stdout": ""}
        return tool.execute(arguments)

    def handle_tool_calls(self, tool_call: Dict) -> str:
        """处理工具调用，只处理第一个工具"""
        try:
            # 只处理第一个工具调用
            name = tool_call["name"]
            args = tool_call["arguments"]

            tool_call_help = """
# 🛠️ 工具使用系统
您正在使用一个需要精确格式和严格规则的工具执行系统。

# 📋 工具调用格式

<TOOL_CALL>
name: 工具名称
arguments:
    param1: 值1
    param2: 值2
</TOOL_CALL>

# ❗ 关键规则
1. 每次只使用一个工具
   - 一次只执行一个工具
   - 等待结果后再进行下一步

2. 严格遵守格式
   - 完全按照上述格式
   - 使用正确的YAML缩进
   - 包含所有必需参数

3. 结果处理
   - 等待执行结果
   - 不要假设结果
   - 不要创建虚假响应
   - 不要想象对话

4. 信息管理
   - 如果信息不足，询问用户
   - 跳过不必要的步骤
   - 如果卡住，请求指导
   - 不要在没有完整信息的情况下继续

# 📝 字符串参数格式
始终使用 | 语法表示字符串参数：

<TOOL_CALL>
name: execute_shell
arguments:
    command: |
        git status --porcelain
</TOOL_CALL>

# 💡 最佳实践
- 准备好后立即开始执行
- 无需请求许可即可开始
- 使用正确的字符串格式
- 监控进度并调整
- 遇到困难时请求帮助

# ⚠️ 常见错误
- 同时调用多个工具
- 字符串参数缺少 |
- 假设工具结果
- 创建虚构对话
- 在没有所需信息的情况下继续
"""
            
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    PrettyOutput.print(f"工具参数格式无效: {name} {tool_call_help}", OutputType.ERROR)
                    return ""

            # Display tool call information
            PrettyOutput.section(f"执行工具: {name}", OutputType.TOOL)
            params = "参数:\n"
            if isinstance(args, dict):
                for key, value in args.items():
                    params += f"{key} = {value}\n"
            else:
                params += f"{args}"

            PrettyOutput.print(params, OutputType.INFO)
            
            # Execute tool call
            result = self.execute_tool(name, args)

            stdout = result["stdout"]
            stderr = result.get("stderr", "")
            output_parts = []
            if stdout:
                output_parts.append(f"输出:\n{stdout}")
            if stderr:
                output_parts.append(f"错误:\n{stderr}")
            output = "\n\n".join(output_parts)
            output = "无输出和错误" if not output else output
            
            # Process the result
            if result["success"]:
                
                PrettyOutput.section("执行成功", OutputType.SUCCESS)
                
                # If the output exceeds 4k characters, use a large model to summarize
                if get_context_token_count(output) > self.max_token_count:
                    try:
                        PrettyOutput.print("输出过长，正在总结...", OutputType.PROGRESS)
                        model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
                        
                        # If the output exceeds the maximum context length, only take the last part
                        max_count = self.max_token_count
                        if get_context_token_count(output) > max_count:
                            output_to_summarize = output[-max_count:]
                            truncation_notice = f"\n(注意：由于输出过长，仅总结最后 {max_count} 个字符)"
                        else:
                            output_to_summarize = output
                            truncation_notice = ""

                        prompt = f"""请总结以下工具的执行结果，提取关键信息和重要结果。注意：
1. 保留所有重要的数值、路径、错误信息等
2. 保持结果的准确性
3. 用简洁的语言描述主要内容
4. 如果有错误信息，确保包含在总结中

工具名称: {name}
执行结果:
{output_to_summarize}

请提供总结:"""

                        summary = model.chat_until_success(prompt)
                        output = f"""--- 原始输出过长，以下是总结 ---{truncation_notice}

{summary}

--- 总结结束 ---"""
                        
                    except Exception as e:
                        PrettyOutput.print(f"总结失败: {str(e)}", OutputType.ERROR)
                        output = f"输出过长 ({len(output)} 字符)，建议查看原始输出。\n前300字符预览:\n{output[:300]}..."
            
            else:
                PrettyOutput.section("执行失败", OutputType.WARNING)
                PrettyOutput.print(result["stderr"], OutputType.WARNING)
            return output
            
        except Exception as e:
            PrettyOutput.print(f"工具执行失败：{str(e)}", OutputType.ERROR)
            return f"工具调用失败: {str(e)}"
