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
    # 使用集合去重
    processed_tags = set()
    # 处理每个标记
    for tag in special_tags:
        if tag in processed_tags:
            continue
        processed_tags.add(tag)

        if tag in replace_map:
            if tag in ["Summary", "Clear"]:
                # 特殊处理需要立即返回的标记
                user_input = user_input.replace(f"'<{tag}>'", "")
                if tag == "Summary":
                    agent._summarize_and_clear_history()
                elif tag == "Clear":
                    agent.clear()
                if not user_input.strip():
                    return "", True
            else:
                # 统一使用预定义的模板
                user_input = user_input.replace(f"'<{tag}>'", "")
                user_input += replace_map[tag]
        # 移除对未知标记的警告输出

    return user_input, False
