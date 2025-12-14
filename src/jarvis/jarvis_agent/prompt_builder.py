# -*- coding: utf-8 -*-
from typing import List

from jarvis.jarvis_agent.protocols import OutputHandlerProtocol


def build_action_prompt(output_handlers: List[OutputHandlerProtocol]) -> str:
    """
    Builds the action prompt string from a list of output handlers.

    Args:
        output_handlers: A list of output handler instances.

    Returns:
        A formatted string containing the action prompt.
    """
    action_prompt = """
<actions>
# 🧰 可用操作
以下是您可以使用的操作：
"""

    # Add tool list overview
    action_prompt += "\n<overview>\n## Action List\n"
    action_prompt += (
        "[" + ", ".join([handler.name() for handler in output_handlers]) + "]"
    )
    action_prompt += "\n</overview>"

    # Add details for each tool
    action_prompt += "\n\n<details>\n# 📝 Action Details\n"
    for handler in output_handlers:
        action_prompt += f"\n<tool>\n## {handler.name()}\n"
        # Get the handler's prompt and ensure correct formatting
        handler_prompt = handler.prompt().strip()
        # Adjust indentation to maintain hierarchy
        handler_prompt = "\n".join(
            "   " + line if line.strip() else line
            for line in handler_prompt.split("\n")
        )
        action_prompt += handler_prompt + "\n</tool>\n"

    # Add tool usage summary
    action_prompt += """
</details>

<rules>
# ❗ 重要操作使用规则（必须严格遵守，违反将导致错误）
1. **一次对话只能使用一个操作**：每个响应必须包含且仅包含一个工具调用（任务完成时除外）。同时调用多个工具会导致系统错误。
2. **禁止虚构结果**：所有操作必须基于实际执行结果，禁止推测、假设或虚构任何执行结果。必须等待工具执行完成并获得实际结果后再进行下一步。
3. **等待操作结果**：在继续下一步之前，必须等待当前工具的执行结果，不能假设工具执行的结果。
4. **处理完结果后再调用新的操作**：必须完整处理当前工具的执行结果，包括错误信息、输出内容等，然后再决定下一步操作。
5. **严格按照每个操作的格式执行**：必须遵循每个工具调用的格式要求，包括参数类型、必需字段等。
6. 如果对操作使用不清楚，请请求帮助
</rules>
</actions>
"""
    return action_prompt
