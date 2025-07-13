# -*- coding: utf-8 -*-
from typing import Any, Tuple, TYPE_CHECKING

from jarvis.jarvis_utils.input import user_confirm
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

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

    if len(tool_list) > 1:
        error_message = (
            f"操作失败：检测到多个操作。一次只能执行一个操作。"
            f"尝试执行的操作：{', '.join([handler.name() for handler in tool_list])}"
        )
        PrettyOutput.print(error_message, OutputType.WARNING)
        return False, error_message

    if not tool_list:
        return False, ""

    tool_to_execute = tool_list[0]
    if not agent.execute_tool_confirm or user_confirm(
        f"需要执行{tool_to_execute.name()}确认执行？", True
    ):
        print(f"🔧 正在执行{tool_to_execute.name()}...")
        result = tool_to_execute.handle(response, agent)
        print(f"✅ {tool_to_execute.name()}执行完成")
        return result

    return False, ""
