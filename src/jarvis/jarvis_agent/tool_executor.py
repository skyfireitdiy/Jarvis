# -*- coding: utf-8 -*-
import json
from typing import TYPE_CHECKING
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

from jarvis.jarvis_utils.input import user_confirm
from jarvis.jarvis_utils.output import PrettyOutput

if TYPE_CHECKING:
    from jarvis.jarvis_agent import Agent


TERMINAL_SCREEN_COLUMNS = 300
TERMINAL_SCREEN_LINES = 100000


def _normalize_terminal_output(output_text: str) -> str:
    """将终端输出归一化为用户最终可见的文本。"""
    if not output_text:
        return output_text

    try:
        import pyte

        screen = pyte.Screen(TERMINAL_SCREEN_COLUMNS, TERMINAL_SCREEN_LINES)
        stream = pyte.Stream(screen)
        stream.feed(output_text)

        visible_lines: List[str] = []
        for row_index in range(screen.lines):
            row = screen.buffer[row_index]
            rendered_line = "".join(char.data for char in row.values()).rstrip()
            if rendered_line:
                visible_lines.append(rendered_line)

        normalized_output = "\n".join(visible_lines).strip()
        return normalized_output or output_text.strip()
    except Exception:
        return output_text.strip()


def _normalize_tool_result(tool_result: Any) -> Any:
    """清理工具结果中的终端控制输出，优先保持现有返回协议不变。"""
    if not isinstance(tool_result, tuple) or len(tool_result) != 2:
        return tool_result

    should_return, payload = tool_result
    if isinstance(payload, str):
        return should_return, _normalize_terminal_output(payload)

    return tool_result


def execute_tool_call(response: str, agent: "Agent") -> Tuple[bool, Any]:
    """
    Parses the model's response, identifies the appropriate tool, and executes it.

    Args:
        response: The response string from the model, potentially containing a tool call.
        agent: The agent instance, providing context like output handlers and settings.

    Returns:
        A tuple containing:
        - A boolean indicating if the tool's result should be returned to the user.
        - The result of the tool execution or an error message.
    """
    tool_list = []
    for handler in agent.output_handler:
        if handler.can_handle(response):
            tool_list.append(handler)

    # 如果检测到多个不同类型的 handler（如 TOOL_CALL 和其他类型），仍然报错
    # 但如果只有一个 handler（通常是 ToolRegistry），允许它处理多个工具调用
    if len(tool_list) > 1:
        error_message = (
            f"操作失败：检测到多个不同类型的操作。一次只能执行一种类型的操作。"
            f"尝试执行的操作：{', '.join([handler.name() for handler in tool_list])}"
        )
        PrettyOutput.auto_print(f"⚠️ {error_message}")
        return False, error_message

    if not tool_list:
        return False, ""

    tool_to_execute = tool_list[0]

    # 始终打印工具调用详情（人类友好格式），便于用户了解正在执行什么
    _print_tool_calls(response, tool_to_execute.name())

    if not agent.execute_tool_confirm or user_confirm(
        f"需要执行{tool_to_execute.name()}确认执行？", True
    ):
        try:
            result = tool_to_execute.handle(response, agent)
            return _normalize_tool_result(result)  # type: ignore[no-any-return]
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 工具执行失败: {str(e)}")
            return False, str(e)

    return False, ""


def _parse_tool_call_args(response: str) -> List[Dict[str, Any]]:
    """从响应文本中提取所有工具调用的名称与完整参数。

    与 ``_parse_tool_call_info`` 的区别：本函数保留原始 arguments 字典，
    用于人类友好展示（而非压缩成单行摘要）。

    Args:
        response: 包含工具调用的响应字符串

    Returns:
        List[Dict]: 每项形如 {"name": str, "arguments": dict}；解析失败返回空列表
    """
    try:
        from jarvis.jarvis_utils.utils import extract_json_from_text
        from jarvis.jarvis_utils.jsonnet_compat import loads as json_loads

        found: List[Dict[str, Any]] = []
        for i, ch in enumerate(response):
            if ch not in ("{", "["):
                continue
            json_str, _ = extract_json_from_text(response, i)
            if not json_str:
                continue
            try:
                tool_call = json_loads(json_str)
            except Exception:
                tool_call = json.loads(json_str)
            if not isinstance(tool_call, dict):
                continue
            name = tool_call.get("name")
            # 只认顶层工具调用：必须同时有 name 与 arguments 键，
            # 否则会把参数里的内层 JSON（如 {"name": "windows.script.exec"}）误判为工具调用
            if not name or "arguments" not in tool_call:
                continue
            args = tool_call.get("arguments")
            found.append(
                {"name": name, "arguments": args if isinstance(args, dict) else {}}
            )
        return found
    except Exception:
        return []


def _print_tool_calls(response: str, fallback_name: str) -> None:
    """打印本次响应中的工具调用详情（人类友好格式，始终输出）。

    解析失败时至少打印工具名称，保证用户知道正在执行什么。

    Args:
        response: 包含工具调用的响应字符串
        fallback_name: 解析失败时使用的工具名称
    """
    calls = _parse_tool_call_args(response)
    if not calls:
        PrettyOutput.auto_print(format_tool_call(fallback_name, {}))
        return
    if len(calls) == 1:
        PrettyOutput.auto_print(
            format_tool_call(calls[0]["name"], calls[0]["arguments"])
        )
        return
    for idx, call in enumerate(calls, 1):
        PrettyOutput.auto_print(
            format_tool_call(call["name"], call["arguments"], index=idx)
        )


def _parse_tool_call_info(
    response: str, handler_name: str
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """从响应中解析工具调用信息

    Args:
        response: 包含工具调用的响应字符串
        handler_name: handler名称（用于回退）

    Returns:
        Dict 或 List[Dict]: 单个工具调用时返回字典，多个工具调用时返回列表
    """
    try:
        # 使用纯 JSON 扫描提取工具调用
        from jarvis.jarvis_utils.utils import extract_json_from_text
        from jarvis.jarvis_utils.jsonnet_compat import loads as json_loads

        # 解析所有工具调用：扫描文本中每个 JSON 对象起始位置并逐个提取
        tool_infos = []
        for i, ch in enumerate(response):
            if ch not in ("{", "["):
                continue
            json_str, _ = extract_json_from_text(response, i)
            if not json_str:
                continue
            try:
                tool_call = json_loads(json_str)
            except Exception:
                tool_call = json.loads(json_str)
            if not isinstance(tool_call, dict):
                continue
            name = tool_call.get("name", handler_name)
            args = tool_call.get("arguments", {})
            # 生成参数摘要
            param_summary = _generate_param_summary(args)
            tool_infos.append({"name": name, "param_summary": param_summary})

        if len(tool_infos) == 0:
            return {"name": handler_name}
        elif len(tool_infos) == 1:
            return tool_infos[0]
        else:
            return tool_infos
    except Exception:
        # 解析失败，返回 handler 名称
        return {"name": handler_name}


# 敏感字段名（子串匹配，覆盖 api_key/access_token 等复合键）
_SENSITIVE_KEYS = ("password", "token", "key", "secret", "auth", "credential")

# 单行值最大展示长度（超出截断并标注原长度）
_MAX_VALUE_LEN = 200
# 嵌套结构最大递归深度（按"容器嵌套层数"计，标量容器不再额外消耗一层）
_MAX_DEPTH = 4
# 列表最多展示的元素个数
_MAX_LIST_ITEMS = 10


def _is_sensitive_key(key: Any) -> bool:
    """判断键名是否含敏感词（子串匹配，覆盖 api_key/access_token 等复合键）。"""
    lowered = str(key).lower()
    return any(s in lowered for s in _SENSITIVE_KEYS)


def _one_line(value: Any) -> str:
    """把任意值压成单行文本：多行折叠为 ``⏎``，过长截断并标注原长度。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    total = len(text)
    # 多行折叠：保留可读性，同时避免摘要刷屏
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", " ⏎ ")
    text = " ".join(text.split())
    if len(text) > _MAX_VALUE_LEN:
        text = f"{text[:_MAX_VALUE_LEN]}…(共 {total} 字符)"
    return text


def _has_nested_container(value: Any) -> bool:
    """判断容器内是否还有非空子容器（用于深度上限判定）。

    标量容器（如 ``{"c": 2}``、``[1, 2]``）继续展开不会产生更深的层级，
    因此不计入深度限制，避免常见参数结构被过早压成 repr。
    """
    if isinstance(value, dict):
        children: Any = value.values()
    elif isinstance(value, (list, tuple)):
        children = value
    else:
        return False
    return any(isinstance(v, (dict, list, tuple)) and v for v in children)


def _render_value(
    value: Any, indent: int, depth: int = 0, in_list: bool = False
) -> List[str]:
    """把参数值渲染为人类友好的多行文本（缩进对齐，嵌套结构展开）。

    Args:
        value: 待渲染的值
        indent: 当前缩进空格数
        depth: 当前递归深度
        in_list: 是否处于列表项内部（列表项首行已带 ``[i]`` 前缀，需补齐对齐空格）

    Returns:
        List[str]: 每行一个字符串（不含行尾换行符）
    """
    pad = " " * indent
    # 列表项内部：首行已由调用方写了 "[i] " 前缀，后续行需补齐同样宽度以对齐
    cont_pad = pad + "    " if in_list else pad
    # 嵌套过深时退化为单行，避免无限展开；标量容器（元素全为标量）不消耗深度
    if depth >= _MAX_DEPTH and _has_nested_container(value):
        return [f"{pad}{_one_line(value)}"]

    if isinstance(value, dict):
        if not value:
            return [f"{pad}(空)"]
        lines: List[str] = []
        for idx, (k, v) in enumerate(value.items()):
            item_pad = pad if idx == 0 else cont_pad
            if _is_sensitive_key(k):
                lines.append(f"{item_pad}{k} = ***")
            elif isinstance(v, (dict, list)) and v:
                lines.append(f"{item_pad}{k}:")
                lines.extend(_render_value(v, indent + 2, depth + 1, in_list))
            else:
                lines.append(f"{item_pad}{k} = {_one_line(v)}")
        return lines

    if isinstance(value, (list, tuple)):
        if not value:
            return [f"{pad}(空)"]
        lines = []
        shown = value[:_MAX_LIST_ITEMS]
        for idx, item in enumerate(shown):
            item_pad = pad if idx == 0 else cont_pad
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{item_pad}[{idx}]:")
                # 子项首行已带 "[idx]: "（4 字符）前缀，后续行需缩进对齐
                lines.extend(_render_value(item, indent + 4, depth + 1, in_list=True))
            else:
                lines.append(f"{item_pad}[{idx}] {_one_line(item)}")
        if len(value) > len(shown):
            lines.append(f"{cont_pad}… 另有 {len(value) - len(shown)} 项未显示")
        return lines

    return [f"{pad}{_one_line(value)}"]


def format_tool_call(name: str, args: Any, index: Optional[int] = None) -> str:
    """把一次工具调用渲染为人类友好的多行文本（供 auto_print 直接输出）。

    输出形如::

        🔧 执行工具 daemon_call
           session_id = 932f0ba7-...
           name = windows.script.exec
           params:
             interpreter = powershell
             script = Get-CimInstance Win32_LogicalDisk ...

    Args:
        name: 工具名称
        args: 工具参数字典（非 dict 时按单值处理）
        index: 批量调用时的序号（从 1 开始），None 表示单次调用

    Returns:
        str: 可直接交给 PrettyOutput.auto_print 的文本
    """
    title = f"🔧 执行工具 {name or '未知工具'}"
    if index is not None:
        title = f"🔧 执行工具 [{index}] {name or '未知工具'}"

    if not isinstance(args, dict) or not args:
        return title

    lines = [title]
    for key, value in args.items():
        if _is_sensitive_key(key):
            lines.append(f"   {key} = ***")
        elif isinstance(value, (dict, list)) and value:
            lines.append(f"   {key}:")
            lines.extend(_render_value(value, 5))
        else:
            lines.append(f"   {key} = {_one_line(value)}")
    return "\n".join(lines)


def _generate_param_summary(args: Dict[str, Any]) -> str:
    """生成参数摘要（单行，保留供确认提示使用，过滤敏感信息）

    Args:
        args: 工具参数字典

    Returns:
        str: 参数摘要字符串
    """
    if not isinstance(args, dict) or not args:
        return ""

    summary_parts = []
    for key, value in args.items():
        if _is_sensitive_key(key):
            summary_parts.append(f"{key}='***'")
        elif isinstance(value, (dict, list)):
            summary_parts.append(f"{key}={type(value).__name__}({len(value)} items)")
        else:
            summary_parts.append(f"{key}={_one_line(value)}")

    return " | ".join(summary_parts)
