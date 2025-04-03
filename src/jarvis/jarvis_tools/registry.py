import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml
from yaspin import yaspin

from jarvis.jarvis_agent.output_handler import OutputHandler
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.base import Tool
from jarvis.jarvis_utils.config import INPUT_WINDOW_REVERSE_SIZE, get_max_input_token_count
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import ct, ot, init_env



tool_call_help = f"""
# 🛠️ 工具使用系统
您正在使用一个需要精确格式和严格规则的工具执行系统。

# 📋 工具调用格式
{ot("TOOL_CALL")}
want: 想要从执行结果中获取到的信息，如果工具输出内容过长，会根据此字段尝试提取有效信息
name: 工具名称
arguments:
    param1: 值1
    param2: 值2
{ct("TOOL_CALL")}

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

{ot("TOOL_CALL")}
want: 当前的git状态，期望获取xxx的提交记录
name: execute_script
arguments:
    interpreter: bash
    script_cotent: |
        git status --porcelain
{ct("TOOL_CALL")}

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
        return ToolRegistry._has_tool_calls_block(response)

    def prompt(self) -> str:
        """加载工具"""
        tools = self.get_all_tools()
        if tools:
            tools_prompt = "## 可用工具:\n"
            for tool in tools:
                try:
                    tools_prompt += f"- 名称: {tool['name']}\n"
                    tools_prompt += f"  描述: {tool['description']}\n"
                    tools_prompt += "  参数: |\n"

                    # 生成格式化的YAML参数
                    yaml_params = yaml.dump(
                        tool['parameters'],
                        allow_unicode=True,
                        indent=4,
                        sort_keys=False,
                        width=120  # 增加行宽限制
                    )

                    # 添加缩进并移除尾部空格
                    for line in yaml_params.split('\n'):
                        tools_prompt += f"    {line.rstrip()}\n"

                except yaml.YAMLError as e:
                    PrettyOutput.print(f"工具 {tool['name']} 参数序列化失败: {str(e)}", OutputType.ERROR)
                    continue

            tools_prompt += tool_call_help.rstrip()  # 移除帮助文本尾部空格
            return tools_prompt
        return ""

    def handle(self, response: str, agent: Any) -> Tuple[bool, Any]:
        tool_call, err_msg = self._extract_tool_calls(response)
        if err_msg:
            return False, err_msg
        return False, self.handle_tool_calls(tool_call, agent)

    def __init__(self):
        """初始化工具注册表"""
        self.tools: Dict[str, Tool] = {}
        # 加载内置工具和外部工具
        self._load_builtin_tools()
        self._load_external_tools()
        self.max_input_token_count = get_max_input_token_count() - INPUT_WINDOW_REVERSE_SIZE

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
    def _has_tool_calls_block(content: str) -> bool:
        """从内容中提取工具调用块"""
        return re.search(ot("TOOL_CALL")+r'(.*?)'+ct("TOOL_CALL"), content, re.DOTALL) is not None
        
    @staticmethod
    def _extract_tool_calls(content: str) -> Tuple[Dict, str]:
        """从内容中提取工具调用。

        参数:
            content: 包含工具调用的内容

        返回:
            List[Dict]: 包含名称和参数的提取工具调用列表

        异常:
            Exception: 如果工具调用缺少必要字段
        """
        # 将内容拆分为行
        data = re.findall(ot("TOOL_CALL")+r'(.*?)'+ct("TOOL_CALL"), content, re.DOTALL)
        ret = []
        for item in data:
            try:
                msg = yaml.safe_load(item)
                if 'name' in msg and 'arguments' in msg and 'want' in msg:
                    ret.append(msg)
                else:
                    return {}, f"""工具调用格式错误，请检查工具调用格式。 
                    
                    {tool_call_help}""" 
            except Exception as e:
                return {}, f"""工具调用格式错误，请检查工具调用格式。 
                
                {tool_call_help}""" 
        if len(ret) > 1:
            return {}, "检测到多个工具调用，请一次只处理一个工具调用。"
        return ret[0] if ret else {}, ""

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

    def _format_tool_output(self, stdout: str, stderr: str) -> str:
        """格式化工具输出为可读字符串

        Args:
            stdout: 标准输出
            stderr: 标准错误

        Returns:
            str: 格式化后的输出
        """
        output_parts = []
        if stdout:
            output_parts.append(f"输出:\n{stdout}")
        if stderr:
            output_parts.append(f"错误:\n{stderr}")
        output = "\n\n".join(output_parts)
        return "无输出和错误" if not output else output


    def handle_tool_calls(self, tool_call: Dict, agent: Any) -> str:
        try:
            name = tool_call["name"]
            args = tool_call["arguments"]
            want = tool_call["want"]
            args["agent"] = agent

            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    PrettyOutput.print(f"工具参数格式无效: {name} {tool_call_help}", OutputType.ERROR)
                    return ""

            # 执行工具调用
            result = self.execute_tool(name, args)

            # 格式化输出
            output = self._format_tool_output(result["stdout"], result.get("stderr", ""))

            # 处理结果
            if get_context_token_count(output) > self.max_input_token_count:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp_file:
                    output_file = tmp_file.name
                    tmp_file.write(output)
                    tmp_file.flush()
                model = PlatformRegistry().get_normal_platform()
                model.set_suppress_output(False)
                model.upload_files([output_file]) # TODO 处理错误
                prompt = f"该文件为工具执行结果，请阅读文件内容，并根据文件提取出以下信息：{want}"
                return f"""工具调用原始输出过长，以下是根据输出提出的信息：

{model.chat_until_success(prompt)}"""
                
            return output

        except Exception as e:
            PrettyOutput.print(f"工具执行失败：{str(e)}", OutputType.ERROR)
            return f"工具调用失败: {str(e)}"


def main():
    """命令行工具入口，提供工具列表查看和工具调用功能"""
    import argparse
    import json

    init_env()

    parser = argparse.ArgumentParser(description='Jarvis 工具系统命令行界面')
    subparsers = parser.add_subparsers(dest='command', help='命令')

    # 列出工具子命令
    list_parser = subparsers.add_parser('list', help='列出所有可用工具')
    list_parser.add_argument('--json', action='store_true', help='以JSON格式输出')
    list_parser.add_argument('--detailed', action='store_true', help='显示详细信息')

    # 调用工具子命令
    call_parser = subparsers.add_parser('call', help='调用指定工具')
    call_parser.add_argument('tool_name', help='要调用的工具名称')
    call_parser.add_argument('--args', type=str, help='工具参数 (JSON格式)')
    call_parser.add_argument('--args-file', type=str, help='从文件加载工具参数 (JSON格式)')

    args = parser.parse_args()

    # 初始化工具注册表
    registry = ToolRegistry()

    if args.command == 'list':
        tools = registry.get_all_tools()

        if args.json:
            if args.detailed:
                print(json.dumps(tools, indent=2, ensure_ascii=False))
            else:
                simple_tools = [{"name": t["name"], "description": t["description"]} for t in tools]
                print(json.dumps(simple_tools, indent=2, ensure_ascii=False))
        else:
            PrettyOutput.section("可用工具列表", OutputType.SYSTEM)
            for tool in tools:
                print(f"\n✅ {tool['name']}")
                print(f"   描述: {tool['description']}")
                if args.detailed:
                    print(f"   参数:")
                    params = tool['parameters'].get('properties', {})
                    required = tool['parameters'].get('required', [])
                    for param_name, param_info in params.items():
                        req_mark = "*" if param_name in required else ""
                        desc = param_info.get('description', '无描述')
                        print(f"     - {param_name}{req_mark}: {desc}")

    elif args.command == 'call':
        tool_name = args.tool_name
        tool = registry.get_tool(tool_name)

        if not tool:
            PrettyOutput.print(f"错误: 工具 '{tool_name}' 不存在", OutputType.ERROR)
            available_tools = ", ".join([t["name"] for t in registry.get_all_tools()])
            print(f"可用工具: {available_tools}")
            return 1

        # 获取参数
        tool_args = {}
        if args.args:
            try:
                tool_args = json.loads(args.args)
            except json.JSONDecodeError:
                PrettyOutput.print("错误: 参数必须是有效的JSON格式", OutputType.ERROR)
                return 1

        elif args.args_file:
            try:
                with open(args.args_file, 'r', encoding='utf-8') as f:
                    tool_args = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                PrettyOutput.print(f"错误: 无法从文件加载参数: {str(e)}", OutputType.ERROR)
                return 1

        # 检查必需参数
        required_params = tool.parameters.get('required', [])
        missing_params = [p for p in required_params if p not in tool_args]

        if missing_params:
            PrettyOutput.print(f"错误: 缺少必需参数: {', '.join(missing_params)}", OutputType.ERROR)
            print("\n参数说明:")
            params = tool.parameters.get('properties', {})
            for param_name in required_params:
                param_info = params.get(param_name, {})
                desc = param_info.get('description', '无描述')
                print(f"  - {param_name}: {desc}")
            return 1

        # 执行工具
        with yaspin(text=f"正在执行工具 {tool_name}...").dots12:
            result = registry.execute_tool(tool_name, tool_args)

        # 显示结果
        if result["success"]:
            PrettyOutput.section(f"工具 {tool_name} 执行成功", OutputType.SUCCESS)
        else:
            PrettyOutput.section(f"工具 {tool_name} 执行失败", OutputType.ERROR)

        if result.get("stdout"):
            print("\n输出:")
            print(result["stdout"])

        if result.get("stderr"):
            PrettyOutput.print("\n错误:", OutputType.ERROR)
            print(result["stderr"])

        return 0 if result["success"] else 1

    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
