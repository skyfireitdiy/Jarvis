# -*- coding: utf-8 -*-
from typing import Any, Tuple


def builtin_input_handler(user_input: str, agent_: Any) -> Tuple[str, bool]:
    """
    内置输入处理器，处理特殊标记和替换
    """
    agent = agent_
    # 定义特殊标记的处理
    special_tags = [
        "Summary",
        "Clear",
        "ToolUsage",
        "ReloadConfig",
        "SaveSession",
        "RestoreSession",
    ]
    replace_map = {
        "Thinking": {
            "template": "\n请再仔细思考并分析一下，找出可能的错误和问题。",
            "append": True,
        },
        "DirectAnswer": {
            "template": "\n请不要执行任何操作，直接对问题进行回答。",
            "append": True,
        },
    }

    # 从用户输入中提取标记
    import re

    pattern = r"'<(\w+)>'"
    tags = re.findall(pattern, user_input)

    processed_tag = []

    # 处理每个标记
    for tag in special_tags:
        # 优先处理特殊标记
        if tag == "Summary":
            agent._summarize_and_clear_history()
            return "", True
        elif tag == "Clear":
            agent.clear()
            return "", True
        elif tag == "ToolUsage":
            agent.set_addon_prompt(agent.get_tool_usage_prompt())
            return "", False
        elif tag == "ReloadConfig":
            from jarvis.jarvis_utils.utils import load_config

            load_config()
            return "", True
        elif tag == "SaveSession":
            if agent.save_session():
                from jarvis.jarvis_utils.output import OutputType, PrettyOutput

                PrettyOutput.print("会话已保存", OutputType.SYSTEM)
            else:
                from jarvis.jarvis_utils.output import OutputType, PrettyOutput

                PrettyOutput.print("会话保存失败", OutputType.ERROR)
            return "", True
        elif tag == "RestoreSession":
            if agent.restore_session():
                from jarvis.jarvis_utils.output import OutputType, PrettyOutput

                PrettyOutput.print("会话已恢复", OutputType.SYSTEM)
            else:
                from jarvis.jarvis_utils.output import OutputType, PrettyOutput

                PrettyOutput.print("会话恢复失败", OutputType.ERROR)
            return "", True

    add_on_prompt = ""
    for tag in tags:
        if tag in replace_map:
            if (
                replace_map[tag].get("append", False)
                and replace_map[tag]["append"]
                and tag not in processed_tag
            ):
                user_input = user_input.replace(f"'<{tag}>'", "")
                add_on_prompt += replace_map[tag]["template"] + "\n"
            else:
                user_input = user_input.replace(
                    f"'<{tag}>'", replace_map[tag]["template"]
                )

    # 检查工具列表并添加记忆工具相关提示
    tool_registry = agent.get_tool_registry()
    if tool_registry:
        tool_names = [tool.name for tool in tool_registry.tools.values()]

        # 如果有save_memory工具，添加相关提示
        if "save_memory" in tool_names:
            add_on_prompt += "\n如果有关键信息需要记忆，请调用save_memory工具进行记忆。"

        # 如果有retrieve_memory工具，添加相关提示
        if "retrieve_memory" in tool_names:
            add_on_prompt += "\n如果需要检索相关记忆信息，请调用retrieve_memory工具。"

    agent.set_addon_prompt(add_on_prompt)

    return user_input, False
