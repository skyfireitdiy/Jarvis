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
以下是你可用的操作：
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
# ❗ 重要规则（严格遵守，违反易出错）
1. **工具调用**：
   - 一次可调用一个或多个工具
   - **多工具限制**：若一次调用多个工具，它们之间必须**互不依赖**
     * 工具 A 的结果不能作为工具 B 的输入
     * 工具 B 不能依赖工具 A 的副作用（如建文件、改状态等）
     * 若工具之间有依赖，必须分多次调用：先执行被依赖的工具，等结果后再调用后面的
2. **禁止虚构结果**：一切结论以工具实际返回为准，禁止推测、假设或编造；等工具执行完拿到真实结果，再走下一步。
3. **等结果再继续**：继续前先看当前工具返回，不要凭空猜它的结果。
4. **先消化结果**：完整处理当前工具返回（包括错误信息、输出文本），再决定下一步。
5. **遵守各工具的格式**：按每个工具要求的格式调用，包括参数类型、必填字段等。
6. 不清楚某个操作的用法时，先问清楚
7. **技能/规则不足时**：如果当前工具无法胜任或缺少相关知识，用 `auto_select_rule` 加载相关规则与技能——它会根据任务自动挑选最合适的规则（最多 5 个）。
"""

    action_prompt += "</rules>\n</actions>\n"
    return action_prompt
