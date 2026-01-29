import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Protocol
from typing import Tuple
from typing import Set
from typing import cast

import yaml

from jarvis.jarvis_mcp import McpClient
from jarvis.jarvis_mcp.sse_mcp_client import SSEMcpClient
from jarvis.jarvis_mcp.stdio_mcp_client import StdioMcpClient
from jarvis.jarvis_mcp.streamable_mcp_client import StreamableMcpClient
from jarvis.jarvis_tools.base import Tool
from jarvis.jarvis_utils.config import calculate_token_limit
from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.config import get_tool_load_dirs

# -*- coding: utf-8 -*-
from jarvis.jarvis_utils.jsonnet_compat import loads as json_loads
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.tag import ct
from jarvis.jarvis_utils.tag import ot
from jarvis.jarvis_utils.utils import daily_check_git_updates
from jarvis.jarvis_utils.utils import is_context_overflow

_multiline_example = """  {
    "multiline_str": |||
      第一行：直接换行，无需 \\n
      第二行：包含"双引号"，无需转义
      第三行：包含'单引号'，直接写
      第四行：支持缩进保留
    |||
  }
  
  或使用 ``` 代替 |||：
  {
    "multiline_str": ```
      第一行：直接换行，无需 \\n
      第二行：包含"双引号"，无需转义
      第三行：包含'单引号'，直接写
      第四行：支持缩进保留
    ```
  }"""

tool_call_help = f"""
## 工具调用指南（Markdown）

**工具调用格式（Jsonnet）**
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

**Jsonnet格式特性**
- 字符串引号：可使用双引号或单引号
- 多行字符串：推荐使用 ||| 或 ``` 分隔符包裹多行字符串，直接换行无需转义，支持保留缩进
  示例：
{_multiline_example}
- 尾随逗号：对象/数组最后一个元素后可添加逗号
- 注释：支持 // 单行或 /* */ 多行注释

**关键规则**
1. 每次只使用一个工具，等待结果后再进行下一步
2. {ot("TOOL_CALL")} 和 {ct("TOOL_CALL")} 必须出现在行首
3. 多行字符串参数推荐使用 ||| 或 ``` 分隔符包裹，直接换行无需转义，支持保留缩进
4. 等待执行结果，不要假设或创建虚假响应
5. 信息不足时询问用户，不要在没有完整信息的情况下继续

**多个工具调用**
- 支持一次调用多个工具，格式如下：
  {ot("TOOL_CALL")}
  {{"name": "tool1", "arguments": {{...}}}}
  {ct("TOOL_CALL")}
  
  {ot("TOOL_CALL")}
  {{"name": "tool2", "arguments": {{...}}}}
  {ct("TOOL_CALL")}
- **重要限制**：多个工具调用之间必须**没有相互依赖关系**
  - 工具A的执行结果不能作为工具B的输入参数
  - 工具B不能依赖工具A产生的副作用（如文件创建、状态修改等）
  - 如果工具之间存在依赖关系，必须分多次调用，先执行依赖的工具，等待结果后再执行后续工具
- 多个工具调用会按顺序执行，每个工具的执行结果会合并返回

**常见错误**
- 同时调用多个有依赖关系的工具（违反无依赖要求）
- 假设工具结果
- Jsonnet格式错误
- 缺少行首的开始/结束标签
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
        has_tool_call = (
            re.search(rf"(?mi){re.escape(ot('TOOL_CALL'))}", response) is not None
        )
        return has_tool_call

    def prompt(self) -> str:
        """加载工具"""
        tools = self.get_all_tools()
        if tools:
            tools_prompt = "## 可用工具\n"
            for tool in tools:
                try:
                    tools_prompt += f"- **名称**: {tool['name']}\n"
                    tools_prompt += f"  - 描述: {tool['description']}\n"
                    tools_prompt += "  - 参数:\n"
                    tools_prompt += "```json\n"

                    # 生成格式化的JSON参数
                    json_params = json.dumps(
                        tool["parameters"],
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=False,
                    )

                    # 添加缩进并移除尾部空格
                    for line in json_params.split("\n"):
                        tools_prompt += f"{line.rstrip()}\n"

                    tools_prompt += "```\n"

                except Exception as e:
                    PrettyOutput.auto_print(
                        f"❌ 工具 {tool['name']} 参数序列化失败: {str(e)}"
                    )
                    continue

            tools_prompt += tool_call_help.rstrip()  # 移除帮助文本尾部空格
            return tools_prompt
        return ""

    def handle(self, response: str, agent_: Any) -> Tuple[bool, Any]:
        try:
            # 传递agent给_extract_tool_calls，以便在解析失败时调用大模型修复
            tool_calls, err_msg, auto_completed = self._extract_tool_calls(
                response, agent_
            )
            if err_msg:
                # 只要工具解析错误，追加工具使用帮助信息（相当于一次 <ToolUsage>）
                try:
                    from jarvis.jarvis_agent import Agent

                    agent_obj: Agent = agent_
                    tool_usage = agent_obj.get_tool_usage_prompt()
                    return False, f"{err_msg}\n\n{tool_usage}"
                except Exception:
                    # 兼容处理：无法获取Agent或ToolUsage时，至少返回工具系统帮助信息
                    return False, f"{err_msg}\n\n{tool_call_help}"

            # 处理多个工具调用
            # 检查是否是多个工具调用的格式（字典的键是工具名称，值是工具调用信息）
            # 单个工具调用时，返回的是 {"name": ..., "arguments": ...}
            # 多个工具调用时，返回的是 {tool_name: {"name": ..., "arguments": ...}, ...}
            if isinstance(tool_calls, dict):
                # 检查是否是多个工具调用的格式
                # 判断标准：如果字典的值是字典且包含 "name" 和 "arguments"，则是多个工具调用格式
                # 否则，如果字典直接包含 "name" 和 "arguments"，则是单个工具调用格式
                if len(tool_calls) > 1:
                    # 多个键，检查第一个值是否是工具调用信息字典
                    first_value = list(tool_calls.values())[0]
                    if (
                        isinstance(first_value, dict)
                        and "name" in first_value
                        and "arguments" in first_value
                    ):
                        # 多个工具调用格式
                        result = self.handle_multiple_tool_calls(tool_calls, agent_)
                    else:
                        # 可能是格式错误，尝试作为单个工具调用处理
                        result = self.handle_tool_calls(tool_calls, agent_)
                elif len(tool_calls) == 1:
                    # 单个键，检查值是否是工具调用信息字典
                    first_value = list(tool_calls.values())[0]
                    if (
                        isinstance(first_value, dict)
                        and "name" in first_value
                        and "arguments" in first_value
                    ):
                        # 多个工具调用格式，但只有一个
                        result = self.handle_tool_calls(first_value, agent_)
                    elif "name" in tool_calls and "arguments" in tool_calls:
                        # 单个工具调用格式（直接包含 name 和 arguments）
                        result = self.handle_tool_calls(tool_calls, agent_)
                    else:
                        # 向后兼容：尝试作为单个工具调用处理
                        result = self.handle_tool_calls(tool_calls, agent_)
                elif "name" in tool_calls and "arguments" in tool_calls:
                    # 单个工具调用格式（直接包含 name 和 arguments，但 len == 0 的情况不应该发生）
                    result = self.handle_tool_calls(tool_calls, agent_)
                else:
                    # 空字典或格式错误
                    result = self.handle_tool_calls(tool_calls, agent_)
            else:
                # 非字典格式，直接调用 handle_tool_calls
                result = self.handle_tool_calls(tool_calls, agent_)

            if auto_completed:
                # 如果自动补全了结束标签，在结果中添加说明信息
                result = f"检测到工具调用缺少结束标签，已自动补全{ct('TOOL_CALL')}。请确保后续工具调用包含完整的开始和结束标签。\n\n{result}"
            return False, result
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 工具调用处理失败: {str(e)}")
            from jarvis.jarvis_agent import Agent

            agent_final: Agent = agent_
            return (
                False,
                f"工具调用处理失败: {str(e)}\n\n{agent_final.get_tool_usage_prompt()}",
            )

    def __init__(self) -> None:
        """初始化工具注册表"""
        self.tools: Dict[str, Tool] = {}
        # 记录内置工具名称，用于区分内置工具和用户自定义工具
        self._builtin_tool_names: Set[str] = set()
        # 定义必选工具列表（这些工具将始终可用）
        self._required_tools: List[str] = ["execute_script"]
        # 加载内置工具和外部工具
        self._load_builtin_tools()
        self._load_external_tools()
        self._load_mcp_tools()
        # 应用工具配置组过滤
        self._apply_tool_config_filter()

    def _get_tool_stats(self) -> Dict[str, int]:
        """从数据目录获取工具调用统计（已废弃，jarvis-stats功能已移除）"""
        # jarvis-stats 功能已移除，返回空字典
        return {}

    def _update_tool_stats(self, name: str) -> None:
        """更新工具调用统计（已废弃，jarvis-stats功能已移除）"""
        # jarvis-stats 功能已移除，此函数不再执行任何操作
        pass

    def use_tools(self, name: List[str]) -> None:
        """使用指定工具

        参数:
            name: 要使用的工具名称列表
        """
        missing_tools = [tool_name for tool_name in name if tool_name not in self.tools]
        if missing_tools:
            PrettyOutput.auto_print(
                f"⚠️ 工具 {missing_tools} 不存在，可用的工具有: {', '.join(self.tools.keys())}"
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
        # 过滤掉必选工具，确保它们不会被移除
        filtered_names = [name for name in names if name not in self._required_tools]
        if filtered_names != names:
            removed_required = [name for name in names if name in self._required_tools]
            PrettyOutput.auto_print(
                f"⚠️ 警告: 无法移除必选工具: {', '.join(removed_required)}"
            )
        self.tools = {
            name: tool
            for name, tool in self.tools.items()
            if name not in filtered_names
        }

    def _apply_tool_config_filter(self) -> None:
        """应用工具配置组的过滤规则"""
        from jarvis.jarvis_utils.config import get_tool_dont_use_list
        from jarvis.jarvis_utils.config import get_tool_use_list

        # 在过滤前保存必选工具的引用
        required_tools_backup: Dict[str, Tool] = {}
        for tool_name in self._required_tools:
            if tool_name in self.tools:
                required_tools_backup[tool_name] = self.tools[tool_name]

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
                PrettyOutput.auto_print(
                    "⚠️ 警告: 配置的工具不存在: "
                    + ", ".join(f"'{name}'" for name in missing)
                )
            self.tools = filtered_tools

        # 如果配置了 dont_use 列表，排除列表中的工具（但必选工具除外）
        if dont_use_list:
            for tool_name in dont_use_list:
                if tool_name in self.tools and tool_name not in self._required_tools:
                    del self.tools[tool_name]

        # 确保必选工具始终被包含（如果它们之前被加载过）
        for tool_name in self._required_tools:
            if tool_name in required_tools_backup:
                self.tools[tool_name] = required_tools_backup[tool_name]
            elif tool_name not in self.tools:
                PrettyOutput.auto_print(
                    f"⚠️ 警告: 必选工具 '{tool_name}' 未加载，可能无法正常工作"
                )

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
        PrettyOutput.auto_print(
            "⚠️ 警告: 从文件目录加载MCP工具的方式将在未来版本中废弃，请尽快迁移到mcp配置方式"
        )

        # 遍历目录中的所有.yaml文件
        error_lines = []
        for file_path in mcp_tools_dir.glob("*.yaml"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                self.register_mcp_tool_by_config(config)
            except Exception as e:
                error_lines.append(f"文件 {file_path} 加载失败: {str(e)}")
        if error_lines:
            PrettyOutput.auto_print("⚠️ " + "\n⚠️ ".join(error_lines))

    def _load_builtin_tools(self) -> None:
        """从内置工具目录加载工具"""
        tools_dir = Path(__file__).parent

        # 遍历目录中的所有.py文件
        for file_path in tools_dir.glob("*.py"):
            # 跳过base.py和__init__.py
            if file_path.name in ["base.py", "__init__.py", "registry.py"]:
                continue

            self.register_tool_by_file(str(file_path))

        # 记录当前已加载的工具名称为内置工具
        self._builtin_tool_names = set(self.tools.keys())

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
                            ["git", "clone", central_repo, central_repo_path],
                            check=True,
                        )
                    except Exception as e:
                        PrettyOutput.auto_print(f"❌ 克隆中心工具仓库失败: {str(e)}")

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
                PrettyOutput.auto_print(f"⚠️ 配置{config.get('name', '')}缺少type字段")
                return False

            # 检查enable标志
            if not config.get("enable", True):
                return False

            name = config.get("name", "mcp")

            # 注册资源工具
            def create_resource_list_func(
                client: McpClient,
            ) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
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

            def create_resource_get_func(
                client: McpClient,
            ) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
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

            def create_mcp_execute_func(
                tool_name: str, client: McpClient
            ) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
                def execute(arguments: Dict[str, Any]) -> Dict[str, Any]:
                    args = arguments.copy()
                    args.pop("agent", None)
                    args.pop("want", None)
                    ret = client.execute(tool_name, args)

                    return ret

                return execute

            if config["type"] == "stdio":
                if "command" not in config:
                    PrettyOutput.auto_print(
                        f"⚠️ 配置{config.get('name', '')}缺少command字段"
                    )
                    return False
            elif config["type"] == "sse":
                if "base_url" not in config:
                    PrettyOutput.auto_print(
                        f"⚠️ 配置{config.get('name', '')}缺少base_url字段"
                    )
                    return False
            elif config["type"] == "streamable":
                if "base_url" not in config:
                    PrettyOutput.auto_print(
                        f"⚠️ 配置{config.get('name', '')}缺少base_url字段"
                    )
                    return False
            else:
                PrettyOutput.auto_print(f"⚠️ 不支持的MCP客户端类型: {config['type']}")
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
                PrettyOutput.auto_print(
                    f"⚠️ 从配置{config.get('name', '')}获取工具列表失败"
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
            PrettyOutput.auto_print(
                f"⚠️ MCP配置{config.get('name', '')}加载失败: {str(e)}"
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
                PrettyOutput.auto_print(f"❌ 文件不存在: {p_file_path}")
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
            PrettyOutput.auto_print(
                f"❌ 从 {Path(file_path).name} 加载工具失败: {str(e)}"
            )
            return False

    @staticmethod
    def _has_tool_calls_block(content: str) -> bool:
        """从内容中提取工具调用块（仅匹配行首标签，忽略大小写）"""
        pattern = (
            rf"(?msi){re.escape(ot('TOOL_CALL'))}(.*?)^{re.escape(ct('TOOL_CALL'))}"
        )
        return re.search(pattern, content) is not None

    @staticmethod
    def _get_long_response_hint(content: str) -> str:
        """生成长响应的提示信息

        参数:
            content: 响应内容

        返回:
            str: 如果响应较长，返回提示信息；否则返回空字符串
        """
        if len(content) > 2048:
            return (
                "\n\n⚠️ 提示：响应内容较长（超过2048字符），可能是上下文溢出导致工具调用解析失败。"
                "如果是修改文件（edit_file）操作，"
                "建议分多次进行，每次处理文件的一部分。"
            )
        return ""

    @staticmethod
    def _extract_json_from_text(
        text: str, start_pos: int = 0
    ) -> Tuple[Optional[str], int]:
        """从文本中提取完整的JSON对象（通过括号匹配）

        参数:
            text: 要提取的文本
            start_pos: 开始搜索的位置

        返回:
            Tuple[Optional[str], int]:
                - 第一个元素是提取的JSON字符串（如果找到），否则为None
                - 第二个元素是JSON结束后的位置
        """
        # 跳过空白字符
        pos = start_pos
        while pos < len(text) and text[pos] in (" ", "\t", "\n", "\r"):
            pos += 1

        if pos >= len(text):
            return None, pos

        # 检查是否以 { 开头
        if text[pos] != "{":
            return None, pos

        # 使用括号匹配找到完整的JSON对象
        brace_count = 0
        in_string = False
        escape_next = False
        string_char = None

        json_start = pos
        for i in range(pos, len(text)):
            char = text[i]

            if escape_next:
                escape_next = False
                continue

            if char == "\\":
                escape_next = True
                continue

            if not in_string:
                if char in ('"', "'"):
                    in_string = True
                    string_char = char
                elif char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        # 找到完整的JSON对象
                        return text[json_start : i + 1], i + 1
            else:
                if char == string_char:
                    in_string = False
                    string_char = None

        return None, len(text)

    @staticmethod
    def _clean_extra_markers(text: str) -> str:
        """清理文本中的额外标记（如 <|tool_call_end|> 等）

        参数:
            text: 要清理的文本

        返回:
            清理后的文本
        """
        # 常见的额外标记模式
        extra_markers = [
            r"<\|tool_call_end\|>",
            r"<\|tool_calls_section_end\|>",
            r"<\|.*?\|>",  # 匹配所有 <|...|> 格式的标记
        ]

        cleaned = text
        for pattern in extra_markers:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        return cleaned.strip()

    @staticmethod
    def _try_llm_fix(content: str, agent: Any, error_msg: str) -> Optional[str]:
        """尝试使用大模型修复工具调用格式

        参数:
            content: 包含错误工具调用的内容
            agent: Agent实例，用于调用大模型
            error_msg: 错误消息

        返回:
            Optional[str]: 修复后的内容，如果修复失败则返回None
        """
        try:
            from jarvis.jarvis_agent.utils import fix_tool_call_with_llm

            # 调用公共函数进行修复
            return fix_tool_call_with_llm(content, agent, error_msg)

        except Exception as e:
            PrettyOutput.auto_print(f"❌ 大模型修复失败：{str(e)}")
            return None

    @staticmethod
    def _check_and_handle_multiple_tool_calls(
        content: str, blocks: List[str]
    ) -> Tuple[Optional[str], bool]:
        """检测并处理多个工具调用的情况

        参数:
            content: 包含工具调用的内容
            blocks: 工具调用块列表

        返回:
            Tuple[Optional[str], bool]:
                - 第一个元素：如果检测到多个工具调用，返回错误消息；否则返回None
                - 第二个元素：是否检测到多个工具调用（现在总是返回False，因为支持多个工具调用）
        """
        # 现在支持多个工具调用，不再返回错误
        return None, False

    @staticmethod
    def _extract_tool_calls(
        content: str,
        agent: Optional[Any] = None,
    ) -> Tuple[Dict[str, Dict[str, Any]], str, bool]:
        """从内容中提取工具调用。

        参数:
            content: 包含工具调用的内容
            agent: 可选的Agent实例，用于在解析失败时调用大模型修复

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
        match = re.search(rf"{close_tag_pattern}$", content.rstrip(), re.IGNORECASE)
        if match:
            pos = match.start()
            if pos > 0 and content[pos - 1] not in ("\n", "\r"):
                content = content[:pos] + "\n" + content[pos:]

        # 首先尝试标准的提取方式（忽略大小写）
        pattern = (
            rf"(?msi){re.escape(ot('TOOL_CALL'))}(.*?)^{re.escape(ct('TOOL_CALL'))}"
        )
        data = re.findall(pattern, content)
        auto_completed = False

        # 如果检测到多个工具调用块，先检查是否是多个独立的工具调用
        if len(data) > 1:
            (
                error_msg,
                has_multiple,
            ) = ToolRegistry._check_and_handle_multiple_tool_calls(content, data)
            if has_multiple:
                return (
                    cast(Dict[str, Dict[str, Any]], {}),
                    error_msg if error_msg else "",
                    False,
                )
            # 如果解析失败，可能是多个工具调用被当作一个 JSON 来解析了
            # 继续执行后续的宽松提取逻辑

        # 如果标准提取失败，尝试更宽松的提取方式
        if not data:
            # can_handle 确保 ot("TOOL_CALL") 在内容中（行首）。
            # 如果数据为空，则表示行首的 ct("TOOL_CALL") 可能丢失。
            has_open_at_bol = (
                re.search(rf"(?mi){re.escape(ot('TOOL_CALL'))}", content) is not None
            )
            has_close_at_bol = (
                re.search(rf"(?mi)^{re.escape(ct('TOOL_CALL'))}", content) is not None
            )

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
                        json_loads(temp_data[0])  # Check if valid JSON
                        data = temp_data
                        auto_completed = True
                    except (Exception, EOFError, KeyboardInterrupt):
                        # Even after fixing, it's not valid JSON, or user cancelled.
                        # Fall through to try more lenient extraction.
                        pass

            # 如果仍然没有数据，尝试更宽松的提取：直接从开始标签后提取JSON
            if not data:
                # 先检查是否有多个工具调用块（可能被当作一个 JSON 来解析导致失败）
                multiple_blocks = re.findall(
                    rf"(?msi){re.escape(ot('TOOL_CALL'))}(.*?){re.escape(ct('TOOL_CALL'))}",
                    content,
                )
                (
                    error_msg,
                    has_multiple,
                ) = ToolRegistry._check_and_handle_multiple_tool_calls(
                    content, multiple_blocks
                )
                if has_multiple:
                    return (
                        cast(Dict[str, Dict[str, Any]], {}),
                        error_msg if error_msg else "",
                        False,
                    )

                # 找到开始标签的位置
                open_tag_match = re.search(
                    rf"(?i){re.escape(ot('TOOL_CALL'))}", content
                )
                if open_tag_match:
                    # 从开始标签后提取JSON
                    start_pos = open_tag_match.end()
                    json_str, end_pos = ToolRegistry._extract_json_from_text(
                        content, start_pos
                    )

                    if json_str:
                        # 清理JSON字符串中的额外标记
                        json_str = ToolRegistry._clean_extra_markers(json_str)

                        # 尝试解析JSON
                        try:
                            parsed = json_loads(json_str)
                            # 验证是否包含必要字段
                            if "name" in parsed and "arguments" in parsed:
                                data = [json_str]
                                auto_completed = True
                            else:
                                # 记录缺少必要字段的错误
                                missing_fields = []
                                if "name" not in parsed:
                                    missing_fields.append("name")
                                if "arguments" not in parsed:
                                    missing_fields.append("arguments")
                                # 不立即返回错误，继续尝试其他方法，但记录信息用于后续错误提示
                                pass
                        except Exception:
                            # JSON解析失败，记录错误信息用于后续错误提示
                            # 不立即返回错误，继续尝试其他方法（如大模型修复）
                            pass
                    else:
                        # JSON提取失败：没有找到有效的JSON对象
                        # 不立即返回错误，继续尝试其他方法（如大模型修复）
                        pass

            # 如果仍然没有数据，尝试使用大模型修复
            if not data:
                long_hint = ToolRegistry._get_long_response_hint(content)
                # 检查是否有开始和结束标签，生成更准确的错误消息
                has_open = (
                    re.search(rf"(?i){re.escape(ot('TOOL_CALL'))}", content) is not None
                )
                has_close = (
                    re.search(rf"(?i){re.escape(ct('TOOL_CALL'))}", content) is not None
                )

                if has_open and has_close:
                    # 有开始和结束标签，但JSON解析失败
                    error_msg = f"工具调用格式错误：检测到{ot('TOOL_CALL')}和{ct('TOOL_CALL')}标签，但JSON解析失败。请检查JSON格式是否正确，确保包含name和arguments字段。\n{tool_call_help}{long_hint}"
                elif has_open and not has_close:
                    # 只有开始标签，没有结束标签
                    error_msg = f"工具调用格式错误：检测到{ot('TOOL_CALL')}标签，但未找到{ct('TOOL_CALL')}标签。请确保工具调用包含完整的开始和结束标签。\n{tool_call_help}{long_hint}"
                else:
                    # 其他情况
                    error_msg = f"工具调用格式错误：无法解析工具调用内容。请检查工具调用格式。\n{tool_call_help}{long_hint}"

                # 如果提供了agent且long_hint为空，尝试使用大模型修复
                if agent is not None and not long_hint:
                    llm_fixed_content: Optional[str] = ToolRegistry._try_llm_fix(
                        content, agent, error_msg
                    )
                    if llm_fixed_content is not None:
                        # 递归调用自身，尝试解析修复后的内容
                        return ToolRegistry._extract_tool_calls(fixed_content, None)

                # 如果大模型修复失败或未提供agent或long_hint不为空，返回错误
                return (
                    {},
                    error_msg,
                    False,
                )

        ret = []
        for item in data:
            try:
                # 清理可能存在的额外标记
                cleaned_item = ToolRegistry._clean_extra_markers(item)
                msg = json_loads(cleaned_item)
            except Exception as e:
                # 如果解析失败，先检查是否是因为有多个工具调用
                # 检查错误信息中是否包含 "expected a comma" 或类似的多对象错误
                error_str = str(e).lower()
                if "expected a comma" in error_str or "multiple" in error_str:
                    # 尝试检测是否有多个工具调用块
                    multiple_blocks = re.findall(
                        rf"(?msi){re.escape(ot('TOOL_CALL'))}(.*?){re.escape(ct('TOOL_CALL'))}",
                        content,
                    )
                    (
                        error_msg,
                        has_multiple,
                    ) = ToolRegistry._check_and_handle_multiple_tool_calls(
                        content, multiple_blocks
                    )
                    if has_multiple:
                        return (
                            cast(Dict[str, Dict[str, Any]], {}),
                            error_msg if error_msg else "",
                            False,
                        )

                long_hint = ToolRegistry._get_long_response_hint(content)
                error_msg = f"""Jsonnet 解析失败：{e}

提示：Jsonnet支持双引号/单引号、尾随逗号、注释。多行字符串推荐使用 ||| 或 ``` 分隔符包裹，直接换行无需转义，支持保留缩进。

{tool_call_help}{long_hint}"""

                # 如果提供了agent且long_hint为空，尝试使用大模型修复
                if agent is not None and not long_hint:
                    retry_fixed_content: Optional[str] = ToolRegistry._try_llm_fix(
                        content, agent, error_msg
                    )
                    if retry_fixed_content is not None:
                        # 递归调用自身，尝试解析修复后的内容
                        return ToolRegistry._extract_tool_calls(
                            retry_fixed_content, None
                        )

                # 如果大模型修复失败或未提供agent或long_hint不为空，返回错误
                return (
                    {},
                    error_msg,
                    False,
                )

            if "name" in msg and "arguments" in msg:
                ret.append(msg)
            else:
                long_hint = ToolRegistry._get_long_response_hint(content)
                error_msg = f"""工具调用格式错误，请检查工具调用格式（缺少name、arguments字段）。

                {tool_call_help}{long_hint}"""

                # 如果提供了agent且long_hint为空，尝试使用大模型修复
                if agent is not None and not long_hint:
                    fixed_content_3: Optional[str] = ToolRegistry._try_llm_fix(
                        content, agent, error_msg
                    )
                    if fixed_content_3 is not None:
                        # 递归调用自身，尝试解析修复后的内容
                        return ToolRegistry._extract_tool_calls(fixed_content_3, None)

                # 如果大模型修复失败或未提供agent或long_hint不为空，返回错误
                return (
                    {},
                    error_msg,
                    False,
                )
        # 支持多个工具调用：返回所有工具调用的字典
        if len(ret) == 0:
            return {}, "", auto_completed
        elif len(ret) == 1:
            return ret[0], "", auto_completed
        else:
            # 多个工具调用：构建字典，键为工具名称，值为工具调用信息
            tool_calls_dict = {}
            for tool_call in ret:
                name = tool_call.get("name", "unknown")
                # 如果同名工具调用多次，使用索引区分
                if name in tool_calls_dict:
                    base_name = name
                    index = 1
                    while f"{base_name}_{index}" in tool_calls_dict:
                        index += 1
                    name = f"{base_name}_{index}"
                tool_calls_dict[name] = tool_call
            return tool_calls_dict, "", auto_completed

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
            PrettyOutput.auto_print(f"⚠️ 警告: 工具 '{name}' 已存在，将被覆盖")
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

    def get_custom_tools(self) -> List[Dict[str, Any]]:
        """获取用户自定义工具（非内置工具）

        返回:
            List[Dict[str, Any]]: 包含用户自定义工具信息的列表
        """
        return [
            tool.to_dict()
            for tool in self.tools.values()
            if tool.name not in self._builtin_tool_names
        ]

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
            result = None
            if getattr(tool, "protocol_version", "1.0") == "2.0":
                # v2.0: agent与参数分离传递
                # 尝试使用agent作为第二个参数，如果不兼容则回退到旧方式
                try:
                    result = tool.func(arguments, agent)  # type: ignore[call-arg]
                except TypeError:
                    # 兼容旧版v2.0工具，只传arguments
                    result = tool.func(arguments)
            else:
                # v1.0: 兼容旧实现，将agent注入到arguments（如果提供）
                args_to_call = arguments.copy() if isinstance(arguments, dict) else {}
                if agent is not None:
                    args_to_call["agent"] = agent
                result = tool.execute(args_to_call)
        except TypeError:
            # 兼容处理：如果函数签名不匹配，回退到旧方式
            args_to_call = arguments.copy() if isinstance(arguments, dict) else {}
            if agent is not None:
                args_to_call["agent"] = agent
            result = tool.execute(args_to_call)
        finally:
            # 记录工具执行耗时（已废弃，jarvis-stats功能已移除）
            pass

        return result

    def _format_tool_output(
        self, stdout: str, stderr: str, platform: Any = None
    ) -> str:
        """格式化工具输出为可读字符串

        Args:
            stdout: 标准输出
            stderr: 标准错误
            platform: 平台实例，用于获取剩余token数

        Returns:
            str: 格式化后的输出
        """
        # 根据剩余token数截断输出
        if platform is not None:
            try:
                remaining_tokens = platform.get_remaining_token_count()
                if remaining_tokens > 0:
                    # 计算允许的最大字符数（与c2rust保持一致：使用calculate_token_limit并乘以4）
                    max_allowed_tokens = calculate_token_limit(remaining_tokens)
                    max_allowed_chars = int(max_allowed_tokens * 4)

                    # 计算stdout和stderr的字符数
                    stdout_len = len(stdout) if stdout else 0
                    stderr_len = len(stderr) if stderr else 0
                    total_len = stdout_len + stderr_len

                    # 如果总字符数超过限制，则截断
                    if total_len > max_allowed_chars:
                        # 计算分配给stdout和stderr的字符数（按比例）
                        if stdout_len > 0 and stderr_len > 0:
                            stdout_ratio = stdout_len / total_len
                            stderr_ratio = stderr_len / total_len
                            max_stdout_chars = int(max_allowed_chars * stdout_ratio)
                            max_stderr_chars = int(max_allowed_chars * stderr_ratio)
                        elif stdout_len > 0:
                            max_stdout_chars = max_allowed_chars
                            max_stderr_chars = 0
                        else:
                            max_stdout_chars = 0
                            max_stderr_chars = max_allowed_chars

                        # 截断stdout和stderr（只保留前面部分，与c2rust保持一致）
                        if stdout and max_stdout_chars > 0:
                            stdout = stdout[:max_stdout_chars]
                            if len(stdout) < stdout_len:
                                stdout += "\n... (输出过长，已截断)"
                        if stderr and max_stderr_chars > 0:
                            stderr = stderr[:max_stderr_chars]
                            if len(stderr) < stderr_len:
                                stderr += "\n... (输出过长，已截断)"

                        PrettyOutput.auto_print(
                            f"⚠️ 工具输出过长（{total_len}字符），已根据剩余token数（{remaining_tokens}）截断"
                        )
            except Exception:
                # 如果获取剩余token数失败，不截断
                pass

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
            PrettyOutput.auto_print("⚠️ 输出太长，截取前后30行")
            return "\n".join(
                lines[:30] + ["\n...内容太长，已截取前后30行...\n"] + lines[-30:]
            )
        return output

    def handle_tool_calls(self, tool_call: Dict[str, Any], agent: Any) -> str:
        try:
            name = tool_call["name"]  # 确保name是str类型
            args = tool_call["arguments"]  # 原始参数（来自外部协议）
            want = tool_call.get("want", "")

            from jarvis.jarvis_agent import Agent

            agent_instance: Agent = agent

            # 如果args是字符串，尝试解析为JSON
            if isinstance(args, str):
                try:
                    args = json_loads(args)
                except Exception:
                    # 返回错误并附带完整的工具使用提示，指导下一次正确调用
                    try:
                        usage_prompt = agent_instance.get_tool_usage_prompt()
                    except Exception:
                        usage_prompt = tool_call_help
                    PrettyOutput.auto_print("❌ 工具参数格式无效")
                    return f"工具参数格式无效: {name}。arguments 应为可解析的 Jsonnet 或对象，请按工具调用格式提供。\n提示：对于多行字符串参数，推荐使用 ||| 或 ``` 分隔符包裹，直接换行无需转义，支持保留缩进。\n\n{usage_prompt}"

            # 生成参数摘要，过滤敏感信息
            param_summary = ""
            if isinstance(args, dict) and args:
                # 敏感字段列表
                sensitive_keys = {
                    "password",
                    "token",
                    "key",
                    "secret",
                    "auth",
                    "credential",
                }
                summary_parts = []

                for key, value in args.items():
                    if key.lower() in sensitive_keys:
                        summary_parts.append(f"{key}='***'")
                    elif isinstance(value, (dict, list)):
                        # 复杂类型简化为类型信息
                        summary_parts.append(
                            f"{key}={type(value).__name__}({len(value)} items)"
                        )
                    elif isinstance(value, str) and len(value) > 50:
                        # 长字符串截断
                        summary_parts.append(f"{key}='{value[:47]}...'")
                    else:
                        summary_parts.append(f"{key}={repr(value)}")

                if summary_parts:
                    # 将参数值中的换行符替换为空格，避免摘要中出现换行
                    cleaned_parts = [
                        part.replace("\n", " ").replace("\r", " ")
                        for part in summary_parts
                    ]
                    param_summary = " | ".join(cleaned_parts)

            # 如果有want字段，先打印出Agent的意图
            if want:
                PrettyOutput.auto_print(f"💡 {want}")

            # 合并为一行输出：执行工具调用和参数摘要
            if param_summary:
                PrettyOutput.auto_print(f"🛠️ 执行工具调用 {name} [{param_summary}]")
            else:
                PrettyOutput.auto_print(f"🛠️ 执行工具调用 {name}")

            # 执行工具调用（根据工具实现的协议版本，由系统在内部决定agent的传递方式）
            start_time = time.time()
            result = self.execute_tool(name, args, agent)
            elapsed_time = time.time() - start_time

            # 打印执行状态
            if result.get("success", False):
                PrettyOutput.auto_print(
                    f"✅ 执行工具调用 {name} 成功 (耗时: {elapsed_time:.2f}s)"
                )
            else:
                # 获取失败原因
                stderr = result.get("stderr", "")
                stdout = result.get("stdout", "")
                error_msg = stderr if stderr else (stdout if stdout else "未知错误")
                PrettyOutput.auto_print(f"❌ 执行工具调用 {name} 失败")
                PrettyOutput.auto_print(f"   失败原因: {error_msg}")

            # 记录本轮实际执行的工具，供上层逻辑（如记忆保存判定）使用
            try:
                from jarvis.jarvis_agent import Agent  # 延迟导入避免循环依赖

                agent_instance_for_record: Agent = agent_instance
                # 记录最后一次执行的工具
                agent_instance_for_record.set_user_data("__last_executed_tool__", name)
                # 记录本轮累计执行的工具列表
                executed_list = agent_instance_for_record.get_user_data(
                    "__executed_tools__"
                )
                if not isinstance(executed_list, list):
                    executed_list = []
                executed_list.append(name)
                agent_instance_for_record.set_user_data(
                    "__executed_tools__", executed_list
                )
            except Exception:
                pass

            # 如果执行失败，附带工具使用提示返回
            if not result.get("success", False):
                try:
                    usage_prompt = agent_instance.get_tool_usage_prompt()
                except Exception:
                    usage_prompt = tool_call_help
                platform = agent_instance.model if agent_instance.model else None
                err_output = self._format_tool_output(
                    result.get("stdout", ""), result.get("stderr", ""), platform
                )
                return f"{err_output}\n\n{usage_prompt}"

            # 格式化输出
            platform = agent_instance.model if agent_instance.model else None
            output = self._format_tool_output(
                result["stdout"], result.get("stderr", ""), platform
            )

            # 添加执行时间信息供LLM参考
            if elapsed_time > 0:
                execution_time_info = f"\n\n<execution_time>\n工具名称: {name}\n执行耗时: {elapsed_time:.2f}秒\n</execution_time>"
                output = output + execution_time_info

            # 检查内容是否过大
            # 使用当前模型组（不再从 agent 继承）
            platform = agent_instance.model if agent_instance.model else None
            is_large_content = is_context_overflow(output, platform)

            if is_large_content:
                # 创建临时文件
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False
                ) as tmp_file:
                    output_file = tmp_file.name
                    tmp_file.write(output)
                    tmp_file.flush()

                try:
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
            # 尝试获取工具名称（如果已定义）
            tool_name = ""
            try:
                if "name" in locals():
                    tool_name = name
            except Exception:
                pass
            if tool_name:
                PrettyOutput.auto_print(f"❌ 执行工具调用 {tool_name} 失败：{str(e)}")
            else:
                PrettyOutput.auto_print(f"❌ 工具调用失败：{str(e)}")
            try:
                from jarvis.jarvis_agent import Agent  # 延迟导入避免循环依赖

                agent_instance_for_prompt: Agent = agent
                usage_prompt = agent_instance_for_prompt.get_tool_usage_prompt()
            except Exception:
                usage_prompt = tool_call_help
            return f"工具调用失败: {str(e)}\n\n{usage_prompt}"

    def handle_multiple_tool_calls(
        self, tool_calls: Dict[str, Dict[str, Any]], agent: Any
    ) -> str:
        """处理多个工具调用

        参数:
            tool_calls: 工具调用字典，键为工具名称（可能带索引），值为工具调用信息
            agent: Agent实例

        返回:
            str: 所有工具调用的结果，用分隔符连接
        """
        results = []
        total_count = len(tool_calls)

        PrettyOutput.auto_print(f"🛠️ 准备执行 {total_count} 个工具调用")

        for idx, (tool_key, tool_call) in enumerate(tool_calls.items(), 1):
            name = tool_call.get("name", tool_key)
            PrettyOutput.auto_print(f"\n[{idx}/{total_count}] 执行工具: {name}")

            try:
                result = self.handle_tool_calls(tool_call, agent)
                results.append(
                    f"=== 工具调用 {idx}/{total_count}: {name} ===\n{result}"
                )
            except Exception as e:
                error_msg = f"工具调用 {name} 执行失败: {str(e)}"
                PrettyOutput.auto_print(f"❌ {error_msg}")
                results.append(
                    f"=== 工具调用 {idx}/{total_count}: {name} ===\n❌ {error_msg}"
                )

        # 合并所有结果
        separator = "\n\n" + "=" * 80 + "\n\n"
        combined_result = separator.join(results)

        PrettyOutput.auto_print(f"\n✅ 完成 {total_count} 个工具调用")

        return combined_result
