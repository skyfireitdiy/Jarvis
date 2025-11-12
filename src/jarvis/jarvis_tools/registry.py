# -*- coding: utf-8 -*-
import json5 as json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

import yaml  # type: ignore[import-untyped]

from jarvis.jarvis_mcp import McpClient
from jarvis.jarvis_mcp.sse_mcp_client import SSEMcpClient
from jarvis.jarvis_mcp.stdio_mcp_client import StdioMcpClient
from jarvis.jarvis_mcp.streamable_mcp_client import StreamableMcpClient
from jarvis.jarvis_tools.base import Tool
from jarvis.jarvis_utils.config import get_data_dir, get_tool_load_dirs
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.tag import ct, ot
from jarvis.jarvis_utils.utils import is_context_overflow, daily_check_git_updates

tool_call_help = f"""
<tool_system_guide>
工具调用格式（JSON5）：
{ot("TOOL_CALL")}
{{
  "want": "想要从执行结果中获取到的信息",
  "name": "工具名称",
  "arguments": {{
    "param1": "值1",
    "param2": "值2"
  }}
}}
{ct("TOOL_CALL")}

JSON5格式特性：
- 字符串引号：可使用双引号或单引号
- 多行字符串：使用反引号 `...` 包裹（推荐），自动处理换行，无需转义
- 尾随逗号：对象/数组最后一个元素后可添加逗号
- 注释：支持 // 单行或 /* */ 多行注释

关键规则：
1. 每次只使用一个工具，等待结果后再进行下一步
2. {ot("TOOL_CALL")} 和 {ct("TOOL_CALL")} 必须出现在行首
3. 多行字符串参数优先使用反引号格式
4. 等待执行结果，不要假设或创建虚假响应
5. 信息不足时询问用户，不要在没有完整信息的情况下继续

常见错误：同时调用多个工具、假设工具结果、JSON5格式错误、标签未出现在行首
</tool_system_guide>
"""


class OutputHandlerProtocol(Protocol):
    def name(self) -> str: ...

    def can_handle(self, response: str) -> bool: ...

    def prompt(self) -> str: ...

    def handle(self, response: str, agent: Any) -> Tuple[bool, Any]: ...


class ToolRegistry(OutputHandlerProtocol):
    def name(self) -> str:
        return "TOOL_CALL"

    def can_handle(self, response: str) -> bool:
        # 仅当 {ot("TOOL_CALL")} 出现在行首时才认为可以处理（忽略大小写）
        return re.search(rf'(?mi){re.escape(ot("TOOL_CALL"))}', response) is not None

    def prompt(self) -> str:
        """加载工具"""
        tools = self.get_all_tools()
        if tools:
            tools_prompt = "<tools_section>\n"
            tools_prompt += "  <header>## 可用工具:</header>\n"
            tools_prompt += "  <tools_list>\n"
            for tool in tools:
                try:
                    tools_prompt += "    <tool>\n"
                    tools_prompt += f"      <name>名称: {tool['name']}</name>\n"
                    tools_prompt += f"      <description>描述: {tool['description']}</description>\n"
                    tools_prompt += "      <parameters>\n"
                    tools_prompt += "        <json>|\n"

                    # 生成格式化的JSON参数
                    json_params = json.dumps(
                        tool["parameters"],
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=False,
                    )

                    # 添加缩进并移除尾部空格
                    for line in json_params.split("\n"):
                        tools_prompt += f"          {line.rstrip()}\n"

                    tools_prompt += "        </json>\n"
                    tools_prompt += "      </parameters>\n"
                    tools_prompt += "    </tool>\n"

                except Exception as e:
                    PrettyOutput.print(
                        f"工具 {tool['name']} 参数序列化失败: {str(e)}",
                        OutputType.ERROR,
                    )
                    continue

            tools_prompt += "  </tools_list>\n"
            tools_prompt += "</tools_section>\n"
            tools_prompt += tool_call_help.rstrip()  # 移除帮助文本尾部空格
            return tools_prompt
        return ""

    def handle(self, response: str, agent_: Any) -> Tuple[bool, Any]:
        try:
            tool_call, err_msg, auto_completed = self._extract_tool_calls(response)
            if err_msg:
                # 只要工具解析错误，追加工具使用帮助信息（相当于一次 <ToolUsage>）
                try:
                    from jarvis.jarvis_agent import Agent
                    agent: Agent = agent_
                    tool_usage = agent.get_tool_usage_prompt()
                    return False, f"{err_msg}\n\n{tool_usage}"
                except Exception:
                    # 兼容处理：无法获取Agent或ToolUsage时，至少返回工具系统帮助信息
                    return False, f"{err_msg}\n\n{tool_call_help}"
            result = self.handle_tool_calls(tool_call, agent_)
            if auto_completed:
                # 如果自动补全了结束标签，在结果中添加说明信息
                result = f"检测到工具调用缺少结束标签，已自动补全{ct('TOOL_CALL')}。请确保后续工具调用包含完整的开始和结束标签。\n\n{result}"
            return False, result
        except Exception as e:
            PrettyOutput.print(f"工具调用处理失败: {str(e)}", OutputType.ERROR)
            from jarvis.jarvis_agent import Agent

            agent: Agent = agent_
            return (
                False,
                f"工具调用处理失败: {str(e)}\n\n{agent.get_tool_usage_prompt()}",
            )

    def __init__(self) -> None:
        """初始化工具注册表"""
        self.tools: Dict[str, Tool] = {}
        # 加载内置工具和外部工具
        self._load_builtin_tools()
        self._load_external_tools()
        self._load_mcp_tools()
        # 应用工具配置组过滤
        self._apply_tool_config_filter()

    def _get_tool_stats(self) -> Dict[str, int]:
        """从数据目录获取工具调用统计"""
        from jarvis.jarvis_stats.stats import StatsManager
        from datetime import datetime

        # 获取所有工具的统计数据
        tool_stats = {}
        tools = self.get_all_tools()

        # 获取所有历史数据（从很早的时间开始）
        end_time = datetime.now()
        start_time = datetime(2000, 1, 1)  # 使用一个足够早的时间

        for tool in tools:
            tool_name = tool["name"]
            # 获取该工具的统计数据
            stats_data = StatsManager.get_stats(
                metric_name=tool_name,
                start_time=start_time,
                end_time=end_time,
                tags={"group": "tool"},
            )

            # 计算总调用次数
            if stats_data and "records" in stats_data:
                total_count = sum(record["value"] for record in stats_data["records"])
                tool_stats[tool_name] = int(total_count)
            else:
                tool_stats[tool_name] = 0

        return tool_stats

    def _update_tool_stats(self, name: str) -> None:
        """更新工具调用统计"""
        from jarvis.jarvis_stats.stats import StatsManager

        StatsManager.increment(name, group="tool")

    def use_tools(self, name: List[str]) -> None:
        """使用指定工具

        参数:
            name: 要使用的工具名称列表
        """
        missing_tools = [tool_name for tool_name in name if tool_name not in self.tools]
        if missing_tools:
            PrettyOutput.print(
                f"工具 {missing_tools} 不存在，可用的工具有: {', '.join(self.tools.keys())}",
                OutputType.WARNING,
            )
        self.tools = {
            tool_name: self.tools[tool_name]
            for tool_name in name
            if tool_name in self.tools
        }

    def dont_use_tools(self, names: List[str]) -> None:
        """从注册表中移除指定工具

        参数:
            names: 要移除的工具名称列表
        """
        self.tools = {
            name: tool for name, tool in self.tools.items() if name not in names
        }

    def _apply_tool_config_filter(self) -> None:
        """应用工具配置组的过滤规则"""
        from jarvis.jarvis_utils.config import get_tool_use_list, get_tool_dont_use_list

        use_list = get_tool_use_list()
        dont_use_list = get_tool_dont_use_list()

        # 如果配置了 use 列表，只保留列表中的工具
        if use_list:
            filtered_tools = {}
            missing = []
            for tool_name in use_list:
                if tool_name in self.tools:
                    filtered_tools[tool_name] = self.tools[tool_name]
                else:
                    missing.append(tool_name)
            if missing:
                PrettyOutput.print(
                    "警告: 配置的工具不存在: " + ", ".join(f"'{name}'" for name in missing),
                    OutputType.WARNING,
                )
            self.tools = filtered_tools

        # 如果配置了 dont_use 列表，排除列表中的工具
        if dont_use_list:
            for tool_name in dont_use_list:
                if tool_name in self.tools:
                    del self.tools[tool_name]

    def _load_mcp_tools(self) -> None:
        """加载MCP工具，优先从配置获取，其次从目录扫描"""
        from jarvis.jarvis_utils.config import get_mcp_config

        # 优先从配置获取MCP工具配置
        mcp_configs = get_mcp_config()
        if mcp_configs:
            for config in mcp_configs:
                self.register_mcp_tool_by_config(config)
            return

        # 如果配置中没有，则扫描目录
        mcp_tools_dir = Path(get_data_dir()) / "mcp"
        if not mcp_tools_dir.exists():
            return

        # 添加警告信息
        PrettyOutput.print(
            "警告: 从文件目录加载MCP工具的方式将在未来版本中废弃，请尽快迁移到JARVIS_MCP配置方式",
            OutputType.WARNING,
        )

        # 遍历目录中的所有.yaml文件
        error_lines = []
        for file_path in mcp_tools_dir.glob("*.yaml"):
            try:
                config = yaml.safe_load(open(file_path, "r", encoding="utf-8"))
                self.register_mcp_tool_by_config(config)
            except Exception as e:
                error_lines.append(f"文件 {file_path} 加载失败: {str(e)}")
        if error_lines:
            PrettyOutput.print("\n".join(error_lines), OutputType.WARNING)

    def _load_builtin_tools(self) -> None:
        """从内置工具目录加载工具"""
        tools_dir = Path(__file__).parent

        # 遍历目录中的所有.py文件
        for file_path in tools_dir.glob("*.py"):
            # 跳过base.py和__init__.py
            if file_path.name in ["base.py", "__init__.py", "registry.py"]:
                continue

            self.register_tool_by_file(str(file_path))

    def _load_external_tools(self) -> None:
        """从jarvis_data/tools和配置的目录加载外部工具"""
        from jarvis.jarvis_utils.config import get_central_tool_repo

        tool_dirs = [str(Path(get_data_dir()) / "tools")] + get_tool_load_dirs()

        # 如果配置了中心工具仓库，将其添加到加载路径
        central_repo = get_central_tool_repo()
        if central_repo:
            # 支持本地目录路径或Git仓库URL
            expanded = os.path.expanduser(os.path.expandvars(central_repo))
            if os.path.isdir(expanded):
                # 直接使用本地目录（支持Git仓库的子目录）
                tool_dirs.append(expanded)
            else:
                # 中心工具仓库存储在数据目录下的特定位置
                central_repo_path = os.path.join(get_data_dir(), "central_tool_repo")
                tool_dirs.append(central_repo_path)

                # 确保中心工具仓库被克隆/更新
                if not os.path.exists(central_repo_path):
                    try:
                        import subprocess

                        subprocess.run(
                            ["git", "clone", central_repo, central_repo_path], check=True
                        )
                    except Exception as e:
                        PrettyOutput.print(
                            f"克隆中心工具仓库失败: {str(e)}", OutputType.ERROR
                        )

        # --- 全局每日更新检查 ---
        daily_check_git_updates(tool_dirs, "tools")

        for tool_dir in tool_dirs:
            p_tool_dir = Path(tool_dir)
            if not p_tool_dir.exists() or not p_tool_dir.is_dir():
                continue

            # 遍历目录中的所有.py文件
            for file_path in p_tool_dir.glob("*.py"):
                # 跳过__init__.py
                if file_path.name == "__init__.py":
                    continue

                self.register_tool_by_file(str(file_path))

    def register_mcp_tool_by_config(self, config: Dict[str, Any]) -> bool:
        """从配置字典加载并注册工具

        参数:
            config: MCP工具配置字典

        返回:
            bool: 工具是否加载成功
        """
        try:
            if "type" not in config:
                PrettyOutput.print(
                    f"配置{config.get('name', '')}缺少type字段", OutputType.WARNING
                )
                return False

            # 检查enable标志
            if not config.get("enable", True):

                return False

            name = config.get("name", "mcp")

            # 注册资源工具
            def create_resource_list_func(client: McpClient):
                def execute(arguments: Dict[str, Any]) -> Dict[str, Any]:
                    args = arguments.copy()
                    args.pop("agent", None)
                    args.pop("want", None)
                    ret = client.get_resource_list()

                    return {
                        "success": True,
                        "stdout": json.dumps(ret, ensure_ascii=False, indent=2),
                        "stderr": "",
                    }

                return execute

            def create_resource_get_func(client: McpClient):
                def execute(arguments: Dict[str, Any]) -> Dict[str, Any]:
                    args = arguments.copy()
                    args.pop("agent", None)
                    args.pop("want", None)
                    if "uri" not in args:
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": "缺少必需的uri参数",
                        }
                    ret = client.get_resource(args["uri"])

                    return ret

                return execute

            def create_mcp_execute_func(tool_name: str, client: McpClient):
                def execute(arguments: Dict[str, Any]) -> Dict[str, Any]:
                    args = arguments.copy()
                    args.pop("agent", None)
                    args.pop("want", None)
                    ret = client.execute(tool_name, args)

                    return ret

                return execute

            if config["type"] == "stdio":
                if "command" not in config:
                    PrettyOutput.print(
                        f"配置{config.get('name', '')}缺少command字段",
                        OutputType.WARNING,
                    )
                    return False
            elif config["type"] == "sse":
                if "base_url" not in config:
                    PrettyOutput.print(
                        f"配置{config.get('name', '')}缺少base_url字段",
                        OutputType.WARNING,
                    )
                    return False
            elif config["type"] == "streamable":
                if "base_url" not in config:
                    PrettyOutput.print(
                        f"配置{config.get('name', '')}缺少base_url字段",
                        OutputType.WARNING,
                    )
                    return False
            else:
                PrettyOutput.print(
                    f"不支持的MCP客户端类型: {config['type']}", OutputType.WARNING
                )
                return False

            # 创建MCP客户端
            mcp_client: McpClient
            if config["type"] == "stdio":
                mcp_client = StdioMcpClient(config)
            elif config["type"] == "sse":
                mcp_client = SSEMcpClient(config)
            elif config["type"] == "streamable":
                mcp_client = StreamableMcpClient(config)
            else:
                raise ValueError(f"不支持的MCP客户端类型: {config['type']}")

            # 获取工具信息
            tools = mcp_client.get_tool_list()
            if not tools:
                PrettyOutput.print(
                    f"从配置{config.get('name', '')}获取工具列表失败",
                    OutputType.WARNING,
                )
                return False

            # 注册每个工具
            for tool in tools:
                # 注册工具
                self.register_tool(
                    name=f"{name}.tool_call.{tool['name']}",
                    description=tool["description"],
                    parameters=tool["parameters"],
                    func=create_mcp_execute_func(tool["name"], mcp_client),
                )

            # 注册资源列表工具
            self.register_tool(
                name=f"{name}.resource.get_resource_list",
                description=f"获取{name}MCP服务器上的资源列表",
                parameters={"type": "object", "properties": {}, "required": []},
                func=create_resource_list_func(mcp_client),
            )

            # 注册获取资源工具
            self.register_tool(
                name=f"{name}.resource.get_resource",
                description=f"获取{name}MCP服务器上的指定资源",
                parameters={
                    "type": "object",
                    "properties": {
                        "uri": {"type": "string", "description": "资源的URI标识符"}
                    },
                    "required": ["uri"],
                },
                func=create_resource_get_func(mcp_client),
            )

            return True

        except Exception as e:
            PrettyOutput.print(
                f"MCP配置{config.get('name', '')}加载失败: {str(e)}", OutputType.WARNING
            )
            return False

    def register_tool_by_file(self, file_path: str) -> bool:
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
                    if (
                        isinstance(item, type)
                        and hasattr(item, "name")
                        and hasattr(item, "description")
                        and hasattr(item, "parameters")
                        and hasattr(item, "execute")
                        and item.name == module_name
                    ):
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
                            func=tool_instance.execute,
                            protocol_version=getattr(
                                tool_instance, "protocol_version", "1.0"
                            ),
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
            PrettyOutput.print(
                f"从 {Path(file_path).name} 加载工具失败: {str(e)}", OutputType.ERROR
            )
            return False

    @staticmethod
    def _has_tool_calls_block(content: str) -> bool:
        """从内容中提取工具调用块（仅匹配行首标签，忽略大小写）"""
        pattern = rf'(?msi){re.escape(ot("TOOL_CALL"))}(.*?)^{re.escape(ct("TOOL_CALL"))}'
        return re.search(pattern, content) is not None

    @staticmethod
    def _extract_tool_calls(
        content: str,
    ) -> Tuple[Dict[str, Dict[str, Any]], str, bool]:
        """从内容中提取工具调用。

        参数:
            content: 包含工具调用的内容

        返回:
            Tuple[Dict[str, Dict[str, Any]], str, bool]:
                - 第一个元素是提取的工具调用字典
                - 第二个元素是错误消息字符串(成功时为"")
                - 第三个元素是是否自动补全了结束标签

        异常:
            Exception: 如果工具调用缺少必要字段
        """
        # 如果</TOOL_CALL>出现在响应的末尾，但是前面没有换行符，自动插入一个换行符进行修复（忽略大小写）
        close_tag = ct("TOOL_CALL")
        # 使用正则表达式查找结束标签（忽略大小写），以获取实际位置和原始大小写
        close_tag_pattern = re.escape(close_tag)
        match = re.search(rf'{close_tag_pattern}$', content.rstrip(), re.IGNORECASE)
        if match:
            pos = match.start()
            if pos > 0 and content[pos - 1] not in ("\n", "\r"):
                content = content[:pos] + "\n" + content[pos:]

        # 将内容拆分为行（忽略大小写）
        pattern = rf'(?msi){re.escape(ot("TOOL_CALL"))}(.*?)^{re.escape(ct("TOOL_CALL"))}'
        data = re.findall(pattern, content)
        auto_completed = False
        if not data:
            # can_handle 确保 ot("TOOL_CALL") 在内容中（行首）。
            # 如果数据为空，则表示行首的 ct("TOOL_CALL") 可能丢失。
            has_open_at_bol = re.search(rf'(?mi){re.escape(ot("TOOL_CALL"))}', content) is not None
            has_close_at_bol = re.search(rf'(?mi)^{re.escape(ct("TOOL_CALL"))}', content) is not None
            if has_open_at_bol and not has_close_at_bol:
                # 尝试通过附加结束标签来修复它（确保结束标签位于行首）
                fixed_content = content.strip() + f"\n{ct('TOOL_CALL')}"

                # 再次提取，并检查JSON是否有效
                temp_data = re.findall(
                    pattern,
                    fixed_content,
                )

                if temp_data:
                    try:
                        json.loads(temp_data[0])  # Check if valid JSON

                        # Ask user for confirmation

                        data = temp_data
                        auto_completed = True
                    except (Exception, EOFError, KeyboardInterrupt):
                        # Even after fixing, it's not valid JSON, or user cancelled.
                        # Fall through to the original error.
                        pass

            if not data:
                return (
                    {},
                    f"只有{ot('TOOL_CALL')}标签，未找到{ct('TOOL_CALL')}标签，调用格式错误，请检查工具调用格式。\n{tool_call_help}",
                    False,
                )
        ret = []
        for item in data:
            try:
                msg = json.loads(item)
            except Exception as e:
                return (
                    {},
                    f"""JSON5 解析失败：{e}

提示：JSON5支持双引号/单引号、反引号多行字符串（推荐）、尾随逗号。多行字符串中直接换行，无需转义\\n。

{tool_call_help}""",
                    False,
                )

            if "name" in msg and "arguments" in msg and "want" in msg:
                ret.append(msg)
            else:
                return (
                    {},
                    f"""工具调用格式错误，请检查工具调用格式（缺少name、arguments、want字段）。

                {tool_call_help}""",
                    False,
                )
        if len(ret) > 1:
            return {}, "检测到多个工具调用，请一次只处理一个工具调用。", False
        return ret[0] if ret else {}, "", auto_completed

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: Any,
        func: Callable[..., Dict[str, Any]],
        protocol_version: str = "1.0",
    ) -> None:
        """注册新工具

        参数:
            name: 工具名称
            description: 工具描述
            parameters: 工具参数定义
            func: 工具执行函数
        """
        if name in self.tools:
            PrettyOutput.print(
                f"警告: 工具 '{name}' 已存在，将被覆盖", OutputType.WARNING
            )
        self.tools[name] = Tool(name, description, parameters, func, protocol_version)

    def get_tool(self, name: str) -> Optional[Tool]:
        """获取工具

        参数:
            name: 工具名称

        返回:
            Optional[Tool]: 找到的工具实例，如果不存在则返回None
        """
        return self.tools.get(name)

    def get_all_tools(self) -> List[Dict[str, Any]]:
        """获取所有工具（Ollama格式定义）

        返回:
            List[Dict[str, Any]]: 包含所有工具信息的列表
        """
        return [tool.to_dict() for tool in self.tools.values()]

    def execute_tool(
        self, name: str, arguments: Dict[str, Any], agent: Optional[Any] = None
    ) -> Dict[str, Any]:
        """执行指定工具

        参数:
            name: 工具名称
            arguments: 工具参数
            agent: 智能体实例（由系统内部传递，用于v2.0分离agent与参数）

        返回:
            Dict[str, Any]: 包含执行结果的字典，包含success、stdout和stderr字段
        """
        tool = self.get_tool(name)
        if tool is None:
            return {
                "success": False,
                "stderr": f"工具 {name} 不存在，可用的工具有: {', '.join(self.tools.keys())}",
                "stdout": "",
            }

        # 更新工具调用统计
        self._update_tool_stats(name)

        # 根据工具实现声明的协议版本分发调用方式
        try:
            if getattr(tool, "protocol_version", "1.0") == "2.0":
                # v2.0: agent与参数分离传递
                return tool.func(arguments, agent)  # type: ignore[misc]
            else:
                # v1.0: 兼容旧实现，将agent注入到arguments（如果提供）
                args_to_call = arguments.copy() if isinstance(arguments, dict) else {}
                if agent is not None:
                    args_to_call["agent"] = agent
                return tool.execute(args_to_call)
        except TypeError:
            # 兼容处理：如果函数签名不匹配，回退到旧方式
            args_to_call = arguments.copy() if isinstance(arguments, dict) else {}
            if agent is not None:
                args_to_call["agent"] = agent
            return tool.execute(args_to_call)

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
            output_parts.append(f"<stdout>\n{stdout}\n</stdout>")
        if stderr:
            output_parts.append(f"<stderr>\n{stderr}\n</stderr>")
        output = "\n\n".join(output_parts)
        return "<无输出和错误>" if not output else output

    def _truncate_output(self, output: str) -> str:
        """截断过长的输出内容

        参数:
            output: 要截断的输出内容

        返回:
            截断后的内容，如果内容不超过60行则返回原内容
        """
        if len(output.splitlines()) > 60:
            lines = output.splitlines()
            return "\n".join(
                lines[:30] + ["\n...内容太长，已截取前后30行...\n"] + lines[-30:]
            )
        return output

    def handle_tool_calls(self, tool_call: Dict[str, Any], agent: Any) -> str:
        try:
            name = tool_call["name"]  # 确保name是str类型
            args = tool_call["arguments"]  # 原始参数（来自外部协议）
            want = tool_call["want"]

            from jarvis.jarvis_agent import Agent

            agent_instance: Agent = agent

            # 如果args是字符串，尝试解析为JSON
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    # 返回错误并附带完整的工具使用提示，指导下一次正确调用
                    try:
                        usage_prompt = agent_instance.get_tool_usage_prompt()
                    except Exception:
                        usage_prompt = tool_call_help
                    return f"工具参数格式无效: {name}。arguments 应为可解析的 JSON5 或对象，请按工具调用格式提供。\n提示：对于多行字符串参数，推荐使用反引号 `...` 包裹以提高可读性。\n\n{usage_prompt}"

            # 执行工具调用（根据工具实现的协议版本，由系统在内部决定agent的传递方式）
            result = self.execute_tool(name, args, agent)

            # 记录本轮实际执行的工具，供上层逻辑（如记忆保存判定）使用
            try:
                from jarvis.jarvis_agent import Agent  # 延迟导入避免循环依赖
                agent_instance_for_record: Agent = agent_instance
                # 记录最后一次执行的工具
                agent_instance_for_record.set_user_data("__last_executed_tool__", name)  # type: ignore
                # 记录本轮累计执行的工具列表
                executed_list = agent_instance_for_record.get_user_data("__executed_tools__")  # type: ignore
                if not isinstance(executed_list, list):
                    executed_list = []
                executed_list.append(name)
                agent_instance_for_record.set_user_data("__executed_tools__", executed_list)  # type: ignore
            except Exception:
                pass

            # 如果执行失败，附带工具使用提示返回
            if not result.get("success", False):
                try:
                    usage_prompt = agent_instance.get_tool_usage_prompt()
                except Exception:
                    usage_prompt = tool_call_help
                err_output = self._format_tool_output(result.get("stdout", ""), result.get("stderr", ""))
                return f"{err_output}\n\n{usage_prompt}"

            # 格式化输出
            output = self._format_tool_output(
                result["stdout"], result.get("stderr", "")
            )

            # 检查内容是否过大
            model_group = None
            if agent_instance.model:
                model_group = agent_instance.model.model_group
            is_large_content = is_context_overflow(output, model_group)

            if is_large_content:
                # 创建临时文件
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False
                ) as tmp_file:
                    output_file = tmp_file.name
                    tmp_file.write(output)
                    tmp_file.flush()

                try:
                    if (
                        agent_instance.model
                        and agent_instance.model.support_upload_files()
                    ):
                        summary = agent_instance.generate_summary()
                        agent_instance.clear_history()
                        upload_success = agent_instance.model.upload_files(
                            [output_file]
                        )
                        if upload_success:
                            # 删除args的agent键（保持协议v2.0的“参数与agent分离”在可视化中的一致性）
                            if isinstance(args, dict):
                                args.pop("agent", None)
                            prompt = f"""
以下是之前对话的关键信息总结：

<content>
{summary}
</content>

上传的文件是以下工具执行结果：
{json.dumps({"name":name, "arguments":args, "want":want}, ensure_ascii=False, indent=2)}

请根据以上信息，继续完成任务。
"""
                            return prompt
                    # 使用上传的文件生成摘要
                    return self._truncate_output(output)
                finally:
                    # 清理临时文件
                    try:
                        os.unlink(output_file)
                    except Exception:
                        pass

            return output

        except Exception as e:
            PrettyOutput.print(f"工具执行失败：{str(e)}", OutputType.ERROR)
            try:
                from jarvis.jarvis_agent import Agent  # 延迟导入避免循环依赖
                agent_instance_for_prompt: Agent = agent  # type: ignore
                usage_prompt = agent_instance_for_prompt.get_tool_usage_prompt()
            except Exception:
                usage_prompt = tool_call_help
            return f"工具调用失败: {str(e)}\n\n{usage_prompt}"
