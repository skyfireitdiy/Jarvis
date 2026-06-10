import json
import os
import re
import sys
import tempfile
import threading
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

import yaml  # type: ignore[import-untyped]

from jarvis.jarvis_mcp import McpClient
from jarvis.jarvis_mcp.sse_mcp_client import SSEMcpClient
from jarvis.jarvis_mcp.stdio_mcp_client import StdioMcpClient
from jarvis.jarvis_mcp.streamable_mcp_client import StreamableMcpClient
from jarvis.jarvis_tools.base import Tool
from jarvis.jarvis_utils.config import calculate_token_limit
from jarvis.jarvis_utils.config import read_text_file
from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.config import get_tool_load_dirs

# -*- coding: utf-8 -*-
from jarvis.jarvis_utils.jsonnet_compat import loads as json_loads
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.utils import daily_check_git_updates
from jarvis.jarvis_utils.utils import extract_json_from_text
from jarvis.jarvis_utils.utils import is_context_overflow


tool_call_help = """
## 工具调用指南（Markdown）

**工具调用格式（Json）**
```json
{
  "want": "想要从执行结果中获取到的信息",
  "name": "工具名称",
  "arguments": {
    "param1": "值1",
    "param2": "值2"
  }
}
```

**定时执行（可选）**
在 arguments 中添加以下任一参数可创建定时任务：
- `after`: 延时执行（秒），例如 `"after": 10` 表示10秒后执行
- `at`: 定时执行（ISO格式时间），例如 `"at": "2024-12-31T23:59:59"`
- `loop`: 循环执行（秒），例如 `"loop": 60` 表示每60秒执行一次

```json
// 示例：10秒后执行脚本
{
  "name": "execute_script",
  "arguments": {
    "script_content": "echo hello",
    "after": 10
  }
}
```

**Json格式特性**
- 字符串引号：可使用双引号或单引号
- 尾随逗号：对象/数组最后一个元素后可添加逗号
- 注释：支持 // 单行或 /* */ 多行注释

**关键规则**
1. 每次只使用一个工具，等待结果后再进行下一步
2. 信息不足时询问用户，不要在没有完整信息的情况下继续
3. 定时参数（after/at/loop）会自动创建定时任务，工具不会立即执行

**多个工具调用**
- 支持一次调用多个工具，每个工具调用是一个独立的 JSON 对象：
  ```json
  {"name": "tool1", "arguments": {...}}
  ```
  ```json
  {"name": "tool2", "arguments": {...}}
  ```
- **重要限制**：多个工具调用之间必须**没有相互依赖关系**
  - 工具A的执行结果不能作为工具B的输入参数
  - 工具B不能依赖工具A产生的副作用（如文件创建、状态修改等）
  - 如果工具之间存在依赖关系，必须分多次调用，先执行依赖的工具，等待结果后再执行后续工具
- 多个工具调用会按顺序执行，每个工具的执行结果会合并返回

**常见错误**
- 同时调用多个有依赖关系的工具（违反无依赖要求）
- 假设工具结果
- Json格式错误
- JSON对象缺少 name 或 arguments 字段
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
        # 第一层：严格JSON解析——如果文本中包含带 name 和 arguments 字段的JSON对象，认为可以处理
        for i, ch in enumerate(response):
            if ch == "{":
                json_str, _ = extract_json_from_text(response, i)
                if json_str:
                    try:
                        parsed = json_loads(json_str)
                        if (
                            isinstance(parsed, dict)
                            and "name" in parsed
                            and "arguments" in parsed
                        ):
                            return True
                    except Exception:
                        continue

        # 第二层：严格格式检测——必须是标准的工具调用格式
        # 条件 2：工具名必须以 "name": "tool_name" 标准格式出现，且包含 arguments 字段
        if self.tools:
            for tool_name in self.tools.keys():
                # 必须同时满足："name": "tool_name" 和 "arguments" 字段
                if (
                    f'"name": "{tool_name}"' in response
                    or f'"name":"{tool_name}"' in response
                ):
                    if '"arguments"' in response or '"arguments":' in response:
                        return True

        # 条件 3：工具调用标记 + 完整 JSON 结构——常见标记且包含 name 和 arguments 字段
        tool_call_markers = ["<TOOL_CALL>", "tool_call", "```json"]
        for marker in tool_call_markers:
            if marker in response:
                # 必须同时包含 name 和 arguments 关键字，且格式正确
                if '"name"' in response and '"arguments"' in response:
                    return True

        # 条件4：response 中同时包含 "name" 关键字和工具名（工具名不加引号），且其参数名以引号包裹形式出现
        if self.tools:
            for tool_name, tool_info in self.tools.items():
                # "name" 和工具名分别独立出现在 response 中即可
                if '"name"' in response and f"{tool_name}" in response:
                    # 工具名以标准格式出现，再检查其参数名是否也以引号包裹形式出现
                    parameters = (
                        tool_info.parameters
                        if hasattr(tool_info, "parameters")
                        else tool_info.get("parameters", {})
                    )
                    if isinstance(parameters, dict):
                        properties = parameters.get("properties", {})
                        if isinstance(properties, dict):
                            for param_name in properties:
                                if f'"{param_name}"' in response:
                                    return True

        # 条件5：扁平格式工具调用——JSON中没有name字段，但顶层key与已注册工具的参数名匹配
        # 例如：{"files": [...]} 匹配 read_code，{"interpreter": "bash", "script_content": "..."} 匹配 execute_script
        if self.tools:
            for i, ch in enumerate(response):
                if ch == "{":
                    json_str, _ = extract_json_from_text(response, i)
                    if json_str:
                        try:
                            parsed = json_loads(json_str)
                            if isinstance(parsed, dict) and "name" not in parsed:
                                json_keys = set(parsed.keys())
                                matched_tools = []
                                for tool_name, tool_info in self.tools.items():
                                    parameters = (
                                        tool_info.parameters
                                        if hasattr(tool_info, "parameters")
                                        else tool_info.get("parameters", {})
                                    )
                                    if isinstance(parameters, dict):
                                        properties = parameters.get("properties", {})
                                        required = parameters.get("required", [])
                                        if isinstance(properties, dict) and isinstance(
                                            required, list
                                        ):
                                            param_keys = set(properties.keys())
                                            # 所有required参数必须存在于JSON的key中，且JSON的key必须是工具参数的子集
                                            if (
                                                required
                                                and all(
                                                    r in json_keys for r in required
                                                )
                                                and json_keys.issubset(param_keys)
                                            ):
                                                matched_tools.append(tool_name)
                                # 只有唯一匹配时才判定为工具调用，避免误判
                                if len(matched_tools) == 1:
                                    return True
                        except Exception:
                            continue

        # 条件6：特征组合检测——工具调用标记 + 已注册工具名同时出现
        # 当response中同时包含工具调用标记和具体工具名时，判定为工具调用意图
        # 这能识别非标准格式的工具调用，如 "tool_call: read_code\npath: App.vue"
        tool_call_markers = ["tool_call", "<TOOL_CALL>", "function_call", "action_call"]
        has_tool_call_marker = any(marker in response for marker in tool_call_markers)
        if has_tool_call_marker and self.tools:
            for tool_name in self.tools.keys():
                if tool_name in response:
                    return True

        return False

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

    def handle(self, response: str, agent: Any) -> Tuple[bool, Any]:
        try:
            # 传递 agent 给_extract_tool_calls，以便在解析失败时调用大模型修复
            tool_calls, err_msg, auto_completed = self._extract_tool_calls(
                response, agent
            )
            if err_msg:
                # 只要工具解析错误，追加工具使用帮助信息（相当于一次 <ToolUsage>）
                try:
                    from jarvis.jarvis_agent import Agent

                    agent_obj: Agent = agent
                    tool_usage = agent_obj.get_tool_usage_prompt()
                    return False, f"{err_msg}\n\n{tool_usage}"
                except Exception:
                    # 兼容处理：无法获取 Agent 或 ToolUsage 时，至少返回工具系统帮助信息
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
                        result = self.handle_multiple_tool_calls(tool_calls, agent)
                    else:
                        # 可能是格式错误，尝试作为单个工具调用处理
                        result = self.handle_tool_calls(tool_calls, agent)
                elif len(tool_calls) == 1:
                    # 单个键，检查值是否是工具调用信息字典
                    first_value = list(tool_calls.values())[0]
                    if (
                        isinstance(first_value, dict)
                        and "name" in first_value
                        and "arguments" in first_value
                    ):
                        # 多个工具调用格式，但只有一个
                        result = self.handle_tool_calls(first_value, agent)
                    elif "name" in tool_calls and "arguments" in tool_calls:
                        # 单个工具调用格式（直接包含 name 和 arguments）
                        result = self.handle_tool_calls(tool_calls, agent)
                    else:
                        # 向后兼容：尝试作为单个工具调用处理
                        result = self.handle_tool_calls(tool_calls, agent)
                elif "name" in tool_calls and "arguments" in tool_calls:
                    # 单个工具调用格式（直接包含 name 和 arguments，但 len == 0 的情况不应该发生）
                    result = self.handle_tool_calls(tool_calls, agent)
                else:
                    # 空字典或格式错误
                    result = self.handle_tool_calls(tool_calls, agent)
            else:
                # 非字典格式，直接调用 handle_tool_calls
                result = self.handle_tool_calls(tool_calls, agent)

            # auto_completed 逻辑已移除（不再需要自动补全标签）
            return False, result
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 工具调用处理失败：{str(e)}")
            from jarvis.jarvis_agent import Agent

            agent_final: Agent = agent
            return (
                False,
                f"工具调用处理失败：{str(e)}\n\n{agent_final.get_tool_usage_prompt()}",
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

    def use_tools(self, name: List[str]) -> None:
        """使用指定工具

        参数:
            name: 要使用的工具名称列表
        """
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
        # 保存所有工具的完整副本，用于 execute_tool 时直接查找（不经过过滤）
        self._all_tools = self.tools.copy()

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
                content = read_text_file(str(file_path))
                config = yaml.safe_load(content)
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

        # --- 全局每日更新检查（后台线程执行，避免阻塞）---
        def check_tool_updates() -> None:
            try:
                daily_check_git_updates(tool_dirs, "tools")
            except Exception:
                # 静默失败，不影响正常使用
                pass

        threading.Thread(target=check_tool_updates, daemon=True).start()

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
        """检查内容中是否包含工具调用 JSON"""
        return '"name"' in content and '"arguments"' in content

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
    def _fuzzy_extract_tool_json(content: str) -> List[str]:
        """宽泛提取：从全文中搜索JSON对象，检查是否包含name和arguments字段

        兼容不按规范输出标签的模型（如GLM输出<TOOL_CALL>前缀而非标准JSON）

        参数:
            content: 要搜索的文本内容

        返回:
            List[str]: 提取到的有效工具调用JSON字符串列表
        """
        results = []
        for i, ch in enumerate(content):
            if ch == "{":
                json_str, end_pos = extract_json_from_text(content, i)
                if json_str is None:
                    continue
                try:
                    json_str = ToolRegistry._clean_extra_markers(json_str)
                    parsed = json_loads(json_str)
                    if (
                        isinstance(parsed, dict)
                        and "name" in parsed
                        and "arguments" in parsed
                    ):
                        results.append(json_str)
                except Exception:
                    continue
        return results

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
    def _parse_tool_call_format(content: str) -> list:
        """解析 <tool_call>工具名称 参数JSON 格式"""
        ret: list = []
        tool_call_pattern = r"<tool_call>\s*(\w+)\s+"
        matches = re.finditer(tool_call_pattern, content)

        for match in matches:
            tool_name = match.group(1)
            json_start = match.end()
            while json_start < len(content) and content[json_start].isspace():
                json_start += 1

            if json_start < len(content) and content[json_start] == "{":
                json_str, end_pos = extract_json_from_text(content, json_start)
                if json_str:
                    try:
                        arguments = json_loads(json_str)
                        tool_call = {"name": tool_name, "arguments": arguments}
                        ret.append(tool_call)
                    except Exception:
                        continue
        return ret

    @staticmethod
    def _parse_special_marker_format(content: str) -> list:
        """解析特殊标记格式: <|tool_call_begin|>functions.tool_name:index<|tool_call_argument_begin|>JSON<|tool_call_end|>"""
        ret: list = []
        # 匹配 <|tool_call_begin|>functions.{tool_name}:{index}<|tool_call_argument_begin|>
        pattern = r"<\|tool_call_begin\|>functions\.([a-zA-Z_][a-zA-Z0-9_]*):\d+<\|tool_call_argument_begin\|>"
        matches = re.finditer(pattern, content)

        for match in matches:
            tool_name = match.group(1)  # 提取实际工具名
            json_start = match.end()

            # 查找 <|tool_call_end|> 标记来确定JSON结束位置
            end_marker = "<|tool_call_end|>"
            end_pos = content.find(end_marker, json_start)
            if end_pos == -1:
                # 如果没有结束标记，尝试从当前位置提取JSON
                if json_start < len(content) and content[json_start] == "{":
                    json_str, _ = extract_json_from_text(content, json_start)
                    if json_str:
                        try:
                            arguments = json_loads(json_str)
                            tool_call = {"name": tool_name, "arguments": arguments}
                            ret.append(tool_call)
                        except Exception:
                            continue
            else:
                # 有结束标记，提取标记之间的内容
                json_content = content[json_start:end_pos].strip()
                if json_content.startswith("{"):
                    try:
                        arguments = json_loads(json_content)
                        tool_call = {"name": tool_name, "arguments": arguments}
                        ret.append(tool_call)
                    except Exception:
                        # JSON解析失败，尝试使用extract_json_from_text
                        if json_start < len(content) and content[json_start] == "{":
                            json_str, _ = extract_json_from_text(content, json_start)
                            if json_str:
                                try:
                                    arguments = json_loads(json_str)
                                    tool_call = {
                                        "name": tool_name,
                                        "arguments": arguments,
                                    }
                                    ret.append(tool_call)
                                except Exception:
                                    continue
        return ret

    @staticmethod
    def _parse_function_call_format(content: str) -> list:
        """解析函数调用格式: 工具名(JSON参数)

        格式示例:
        read_code({"files": [{"path": "src/file.py"}]})
        """
        ret: list = []
        # 匹配 工具名(JSON对象) 格式，支持跨行JSON
        pattern = r"(\w+)\s*\(\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})\s*\)"
        matches = re.finditer(pattern, content, re.DOTALL)

        for match in matches:
            tool_name = match.group(1)
            json_str = match.group(2).strip()
            try:
                arguments = json_loads(json_str)
                tool_call = {"name": tool_name, "arguments": arguments}
                ret.append(tool_call)
            except Exception:
                continue
        return ret

    @staticmethod
    def _parse_xml_tag_format(content: str, existing: list) -> list:
        """解析 XML 标签格式: <name>...</name><arguments>...</arguments>"""
        ret: list = []
        xml_name_pattern = r"<name>\s*(\w+)\s*</name>"
        xml_name_matches = list(re.finditer(xml_name_pattern, content))

        for name_match in xml_name_matches:
            xml_tool_name = name_match.group(1)
            search_start = name_match.end()
            xml_args_pattern = r"<arguments>\s*"
            args_match = re.search(xml_args_pattern, content[search_start:])
            if args_match:
                args_content_start = search_start + args_match.end()
                close_tag_pos = content.find("</arguments>", args_content_start)
                if close_tag_pos != -1:
                    args_content = content[args_content_start:close_tag_pos].strip()
                    try:
                        arguments = json_loads(args_content)
                        tool_call = {"name": xml_tool_name, "arguments": arguments}
                        already_found = False
                        for ex in existing:
                            if isinstance(ex, dict) and ex.get("name") == xml_tool_name:
                                already_found = True
                                break
                        if not already_found:
                            ret.append(tool_call)
                    except Exception:
                        pass
        return ret

    @staticmethod
    def _parse_arg_key_value_format(content: str, existing: list) -> list:
        """解析 [TOOL_CALL] 标记 + arg_key/arg_value 标签格式

        格式示例:
        [TOOL_CALL]
        read_code
        <arg_key>files</arg_key><arg_value>[{"path": "src/file.py"}]</arg_value>
        """
        ret: list = []

        # 匹配 [TOOL_CALL] 标记
        tool_call_marker_pattern = r"\[TOOL_CALL\]\s*\n(\w+)"
        marker_matches = list(re.finditer(tool_call_marker_pattern, content))

        for match in marker_matches:
            tool_name = match.group(1)
            search_start = match.end()

            # 检查是否已经找到过该工具
            already_found = False
            for ex in existing:
                if isinstance(ex, dict) and ex.get("name") == tool_name:
                    already_found = True
                    break
            if already_found:
                continue

            # 提取所有 arg_key 和 arg_value 对
            arg_pattern = r"<arg_key>(\w+)</arg_key>\s*<arg_value>(.*?)</arg_value>"
            arg_matches = list(
                re.finditer(arg_pattern, content[search_start:], re.DOTALL)
            )

            if arg_matches:
                arguments = {}
                for arg_match in arg_matches:
                    key = arg_match.group(1)
                    value_str = arg_match.group(2).strip()

                    # 尝试解析值为JSON
                    try:
                        value = json_loads(value_str)
                    except Exception:
                        # 如果不是有效的JSON，保持为字符串
                        value = value_str

                    arguments[key] = value

                tool_call = {"name": tool_name, "arguments": arguments}
                ret.append(tool_call)

        return ret

    @staticmethod
    def _parse_code_block_format(content: str, existing: list) -> Tuple[list, bool]:
        """解析 工具名 + markdown代码块 格式"""
        ret: list = []
        auto_completed = False
        code_block_pattern = r"(?:^|\n)(\w+)\s*\n```[a-zA-Z]*\n(.*?)\n```"
        code_block_matches = re.finditer(code_block_pattern, content, re.DOTALL)

        for match in code_block_matches:
            tool_name = match.group(1)
            code_content = match.group(2).strip()

            already_found = False
            for ex in existing:
                if isinstance(ex, dict) and ex.get("name") == tool_name:
                    already_found = True
                    break
            if already_found:
                continue

            try:
                parsed_content = json_loads(code_content)
                if isinstance(parsed_content, dict):
                    if "name" in parsed_content and "arguments" in parsed_content:
                        ret.append(parsed_content)
                    else:
                        tool_call = {"name": tool_name, "arguments": parsed_content}
                        ret.append(tool_call)
                    auto_completed = True
                    continue
            except Exception:
                pass

            tool_call = {"name": tool_name, "arguments": {"content": code_content}}
            ret.append(tool_call)
            auto_completed = True
        return ret, auto_completed

    @staticmethod
    def _parse_embedded_json_format(content: str) -> list:
        """从全文扫描JSON对象，提取含name+arguments的标准格式"""
        ret: list = []
        used_ranges: list = []
        for i, ch in enumerate(content):
            if ch == "{":
                in_used = False
                for start, end in used_ranges:
                    if start <= i <= end:
                        in_used = True
                        break
                if in_used:
                    continue

                json_str, end_pos = extract_json_from_text(content, i)
                if json_str:
                    try:
                        parsed = json_loads(json_str)
                        if (
                            isinstance(parsed, dict)
                            and "name" in parsed
                            and "arguments" in parsed
                        ):
                            ret.append(parsed)
                            used_ranges.append((i, end_pos))
                    except Exception:
                        continue
        return ret

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
                - 第二个元素是错误消息字符串（成功时为""）
                - 第三个元素保留为False（不再需要自动补全标签）

        异常:
            Exception: 如果工具调用缺少必要字段
        """
        auto_completed = False
        ret: list = []

        # 1. 解析 <tool_call>工具名称 参数JSON 格式
        ret.extend(ToolRegistry._parse_tool_call_format(content))

        # 1.5. 解析特殊标记格式: <|tool_call_begin|>functions.tool_name:index<|tool_call_argument_begin|>
        ret.extend(ToolRegistry._parse_special_marker_format(content))

        # 1.6. 解析函数调用格式: 工具名(JSON参数)
        ret.extend(ToolRegistry._parse_function_call_format(content))

        # 2.5. 解析 [TOOL_CALL]标记+<arg_key>/<arg_value>标签格式
        ret.extend(ToolRegistry._parse_arg_key_value_format(content, ret))
        # 2. 解析 XML 标签格式: <name>...</name><arguments>...</arguments>
        ret.extend(ToolRegistry._parse_xml_tag_format(content, ret))

        # 3. 解析 "工具名 + markdown代码块" 格式
        code_block_results, auto_completed = ToolRegistry._parse_code_block_format(
            content, ret
        )
        ret.extend(code_block_results)

        # 4. 从全文扫描JSON对象，提取含name+arguments的标准格式
        ret.extend(ToolRegistry._parse_embedded_json_format(content))

        # 5. 宽泛提取作为兜底
        if not ret:
            fuzzy_results = ToolRegistry._fuzzy_extract_tool_json(content)
            if fuzzy_results:
                for fuzzy_item in fuzzy_results:
                    try:
                        fuzzy_msg = json_loads(fuzzy_item)
                        if (
                            isinstance(fuzzy_msg, dict)
                            and "name" in fuzzy_msg
                            and "arguments" in fuzzy_msg
                        ):
                            ret.append(fuzzy_msg)
                            auto_completed = True
                    except Exception:
                        pass

        # 如果仍然没有数据，尝试使用大模型修复
        if not ret:
            long_hint = ToolRegistry._get_long_response_hint(content)
            error_msg = f"工具调用格式错误：无法解析工具调用内容。请检查是否输出了包含name和arguments字段的JSON对象。\n{tool_call_help}{long_hint}"

            # 如果提供了agent且long_hint为空，尝试使用大模型修复
            if agent is not None and not long_hint:
                llm_fixed_content: Optional[str] = ToolRegistry._try_llm_fix(
                    content, agent, error_msg
                )
                if llm_fixed_content is not None:
                    return ToolRegistry._extract_tool_calls(llm_fixed_content, None)

            return (
                {},
                error_msg,
                False,
            )

        # 处理解析结果
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
        tool = Tool(name, description, parameters, func, protocol_version)
        self.tools[name] = tool
        # 同时更新 _all_tools，确保新注册的工具可以被调用
        if hasattr(self, "_all_tools"):
            self._all_tools[name] = tool

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
        tool = self._all_tools.get(name)
        if tool is None:
            return {
                "success": False,
                "stderr": f"工具 {name} 不存在，可用的工具有: {', '.join(self._all_tools.keys())}",
                "stdout": "",
            }

        # 根据工具实现声明的协议版本分发调用方式
        try:
            result = None
            if getattr(tool, "protocol_version", "1.0") == "2.0":
                # v2.0: agent与参数分离传递
                # 尝试使用agent作为第二个参数，如果不兼容则回退到旧方式
                try:
                    # v2.0协议：传递arguments和agent两个参数
                    # 使用type: ignore来抑制类型检查器的警告
                    result = tool.func(arguments, agent)  # type: ignore
                except Exception:
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
                    return f"工具参数格式无效: {name}。arguments 应为可解析的 Jsonnet 或对象，请按工具调用格式提供。\n\n{usage_prompt}"

            # 检查是否包含定时参数（after/at/loop）
            if isinstance(args, dict):
                timer_params = {}
                if "after" in args:
                    timer_params["time_type"] = "relative"
                    timer_params["time_value"] = args.pop("after")
                elif "at" in args:
                    timer_params["time_type"] = "absolute"
                    timer_params["time_value"] = args.pop("at")
                elif "loop" in args:
                    timer_params["time_type"] = "interval"
                    timer_params["time_value"] = args.pop("loop")
                    timer_params["interval_seconds"] = timer_params["time_value"]

                # 如果包含定时参数，创建定时任务而不是立即执行
                if timer_params:
                    from jarvis.jarvis_tools.timer import get_timer_manager

                    timer_manager = get_timer_manager()
                    try:
                        task = timer_manager.add_task(
                            task_type="tool_call",
                            time_type=timer_params["time_type"],
                            time_value=timer_params["time_value"],
                            tool_name=name,
                            tool_args=args,
                            interval_seconds=timer_params.get("interval_seconds"),
                        )
                        time_desc = ""
                        if timer_params["time_type"] == "relative":
                            time_desc = f"{timer_params['time_value']}秒后"
                        elif timer_params["time_type"] == "absolute":
                            time_desc = f"在 {timer_params['time_value']}"
                        elif timer_params["time_type"] == "interval":
                            time_desc = f"每 {timer_params['time_value']}秒"

                        msg = f"✅ 已创建定时任务 #{task.task_id}：{time_desc}执行工具 {name}"
                        PrettyOutput.auto_print(msg)
                        return msg
                    except Exception as e:
                        error_msg = f"❌ 创建定时任务失败: {e}"
                        PrettyOutput.auto_print(error_msg)
                        return error_msg

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
            tool_name = (
                tool_call.get("name", "unknown")
                if "tool_call" in locals()
                else "unknown"
            )
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
            PrettyOutput.auto_print(f"[{idx}/{total_count}] 执行工具: {name}")

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

        PrettyOutput.auto_print(f"✅ 完成 {total_count} 个工具调用")

        return combined_result
