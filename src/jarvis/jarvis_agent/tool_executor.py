# -*- coding: utf-8 -*-
import json
import re
from typing import TYPE_CHECKING
from typing import Any
from typing import Dict
from typing import List
from typing import Tuple
from typing import Union

from jarvis.jarvis_utils.input import user_confirm
from jarvis.jarvis_utils.output import PrettyOutput

if TYPE_CHECKING:
    from jarvis.jarvis_agent import Agent


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

    # 如果需要确认，先打印工具详情
    if agent.execute_tool_confirm:
        # 解析工具调用信息（可能包含多个工具调用）
        tool_infos = _parse_tool_call_info(response, tool_to_execute.name())
        if isinstance(tool_infos, list):
            # 多个工具调用
            PrettyOutput.auto_print(f"🔧 准备执行 {len(tool_infos)} 个工具调用:")
            for idx, tool_info in enumerate(tool_infos, 1):
                PrettyOutput.auto_print(
                    f"  [{idx}] {tool_info.get('name', '未知工具')}"
                )
                if tool_info.get("param_summary"):
                    PrettyOutput.auto_print(f"      参数: {tool_info['param_summary']}")
        elif tool_infos:
            # 单个工具调用
            PrettyOutput.auto_print(f"🔧 准备执行工具: {tool_infos['name']}")
            if tool_infos.get("param_summary"):
                PrettyOutput.auto_print(f"   参数: {tool_infos['param_summary']}")
        else:
            # 解析失败时至少显示工具名称
            PrettyOutput.auto_print(f"🔧 准备执行工具: {tool_to_execute.name()}")

    if not agent.execute_tool_confirm or user_confirm(
        f"需要执行{tool_to_execute.name()}确认执行？", True
    ):
        try:
            result = tool_to_execute.handle(response, agent)
            return result
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 工具执行失败: {str(e)}")
            return False, str(e)

    return False, ""


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
        # 使用 ToolRegistry 的提取逻辑
        from jarvis.jarvis_utils.tag import ct, ot

        # 尝试提取所有工具调用块
        pattern = (
            rf"(?msi){re.escape(ot('TOOL_CALL'))}(.*?)^{re.escape(ct('TOOL_CALL'))}"
        )
        matches = re.findall(pattern, response)

        if not matches:
            return {"name": handler_name}

        # 解析所有工具调用
        tool_infos = []
        for match_content in matches:
            try:
                # 解析 JSON
                try:
                    from jarvis.jarvis_utils.jsonnet_compat import loads as json_loads

                    tool_call = json_loads(match_content)
                except Exception:
                    tool_call = json.loads(match_content)

                name = tool_call.get("name", handler_name)
                args = tool_call.get("arguments", {})

                # 生成参数摘要
                param_summary = _generate_param_summary(args)

                tool_infos.append({"name": name, "param_summary": param_summary})
            except Exception:
                # 单个工具调用解析失败，跳过
                continue

        if len(tool_infos) == 0:
            return {"name": handler_name}
        elif len(tool_infos) == 1:
            return tool_infos[0]
        else:
            return tool_infos
    except Exception:
        # 解析失败，返回 handler 名称
        return {"name": handler_name}


def _generate_param_summary(args: Dict[str, Any]) -> str:
    """生成参数摘要，过滤敏感信息

    Args:
        args: 工具参数字典

    Returns:
        str: 参数摘要字符串
    """
    if not isinstance(args, dict) or not args:
        return ""

    # 敏感字段列表
    sensitive_keys = {"password", "token", "key", "secret", "auth", "credential"}

    summary_parts = []
    for key, value in args.items():
        if key.lower() in sensitive_keys:
            summary_parts.append(f"{key}='***'")
        elif isinstance(value, (dict, list)):
            summary_parts.append(f"{key}={type(value).__name__}({len(value)} items)")
        elif isinstance(value, str) and len(value) > 50:
            summary_parts.append(f"{key}='{value[:47]}...'")
        else:
            summary_parts.append(f"{key}={repr(value)}")

    if summary_parts:
        # 将参数值中的换行符替换为空格，避免摘要中出现换行
        cleaned_parts = [
            part.replace("\n", " ").replace("\r", " ") for part in summary_parts
        ]
        return " | ".join(cleaned_parts)

    return ""
