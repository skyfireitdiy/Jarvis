import re
from typing import Any, Tuple
from jarvis.jarvis_utils.config import get_replace_map



def builtin_input_handler(user_input: str, agent: Any) -> Tuple[str, bool]:
    """
    处理内置的特殊输入标记，并追加相应的提示词

    参数：
        user_input: 用户输入
        agent: 代理对象

    返回：
        Tuple[str, bool]: 处理后的输入和是否需要进一步处理
    """
    # 查找特殊标记
    special_tags = re.findall(r"'<([^>]+)>'", user_input)

    if not special_tags:
        return user_input, False

    # 获取替换映射表
    replace_map = get_replace_map()
    # 处理每个标记
    for tag in special_tags:

        # 优先处理特殊标记
        if tag == "Summary":
            agent._summarize_and_clear_history()
            return "", True
        elif tag == "Clear":
            agent.clear()
            return "", True

        # 处理普通替换标记
        if tag in replace_map:
            user_input = user_input.replace(f"'<{tag}>'", replace_map[tag]["template"])

    return user_input, False
