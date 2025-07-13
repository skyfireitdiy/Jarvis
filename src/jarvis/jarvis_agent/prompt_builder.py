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
# ❗ 重要操作使用规则
1. 一次对话只能使用一个操作，否则会出错
2. 严格按照每个操作的格式执行
3. 等待操作结果后再进行下一个操作
4. 处理完结果后再调用新的操作
5. 如果对操作使用不清楚，请请求帮助
</rules>
</actions>
"""
    return action_prompt
