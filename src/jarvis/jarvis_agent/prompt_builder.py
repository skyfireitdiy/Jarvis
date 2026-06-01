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
1. **工具调用规则**：
   - 支持一次调用单个或多个工具
   - **多个工具调用限制**：如果一次调用多个工具，这些工具之间必须**没有相互依赖关系**
     * 工具A的执行结果不能作为工具B的输入参数
     * 工具B不能依赖工具A产生的副作用（如文件创建、状态修改等）
     * 如果工具之间存在依赖关系，必须分多次调用，先执行依赖的工具，等待结果后再执行后续工具
2. **禁止虚构结果**：所有操作必须基于实际执行结果，禁止推测、假设或虚构任何执行结果。必须等待工具执行完成并获得实际结果后再进行下一步。
3. **等待操作结果**：在继续下一步之前，必须等待当前工具的执行结果，不能假设工具执行的结果。
4. **处理完结果后再调用新的操作**：必须完整处理当前工具的执行结果，包括错误信息、输出内容等，然后再决定下一步操作。
5. **严格按照每个操作的格式执行**：必须遵循每个工具调用的格式要求，包括参数类型、必需字段等。
6. 如果对操作使用不清楚，请请求帮助
"""

    action_prompt += "</rules>\n</actions>\n"
    return action_prompt
