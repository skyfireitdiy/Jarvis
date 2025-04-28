def ot(tag_name: str) -> str:
    """生成HTML标签开始标记

    参数：
    tag_name -- HTML标签名称

    返回：
    格式化的开始标签字符串
    """
    return f"<{tag_name}>"

def ct(tag_name: str) -> str:
    """生成HTML标签结束标记

    参数：
    tag_name -- HTML标签名称

    返回：
    格式化的结束标签字符串
    """
    return f"</{tag_name}>"