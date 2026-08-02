# -*- coding: utf-8 -*-
from typing import List
from typing import Optional

from jarvis.jarvis_agent.protocols import OutputHandlerProtocol
from jarvis.jarvis_tools.registry import ToolRegistry


def get_tool_registry(
    output_handlers: List[OutputHandlerProtocol],
) -> Optional[ToolRegistry]:
    """Get the ToolRegistry instance from output handlers."""
    for handler in output_handlers:
        if isinstance(handler, ToolRegistry):
            return handler
    return None


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
以下为汝可用之操作：
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
# ❗ 重要之操作规（必严遵，违则致误）
1. **工具调用之规**：
   - 可一次调用单或多个工具
   - **多工具调用之限**：若一次调用多工具，此等工具之间必**无相互依赖**
     * 工具A之果不得为工具B之入
     * 工具B不得依工具A之副效（如建文、改态等）
     * 若工具间有相依，必分次调用，先执所依之工具，待其果后再行其后
2. **禁虚构结果**：一切操作必据实果，禁推测、假设或虚构。必待工具毕而获实果后，方行下步。
3. **待操作果**：续行之前，必待现工具之果，不得臆其果。
4. **尽果后再调新操作**：必全理现工具之果，含误讯、出文等，再决下步。
5. **严依每操作之式**：必循每工具调用之格式求，含参型、必字段等。
6. 若不明操作之用，请求助
7. **技不足之处理**：若现工具不能任事或乏相关之技，请用 `auto_select_rule` 工具载学相关之规与技。此工具会据任述自择最合之规（至多 5 个），助汝掌完任所需之知。
"""

    action_prompt += "</rules>\n</actions>\n"
    return action_prompt
