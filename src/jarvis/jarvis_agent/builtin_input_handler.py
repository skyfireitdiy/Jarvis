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
            # 先执行标记替换
            user_input = user_input.replace(f"'<{tag}>'", replace_map[tag])
            
            # 特殊处理逻辑（独立判断）
            if tag == "Summary":
                agent._summarize_and_clear_history()
            elif tag == "Clear":
                agent.clear()
            
            if (tag == "Summary" or tag == "Clear") and not user_input.strip():
                return "", True

    return user_input, False
