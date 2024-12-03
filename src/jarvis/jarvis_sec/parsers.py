# -*- coding: utf-8 -*-
"""解析模块 - 用于解析Agent返回的JSON格式摘要"""

from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from jarvis.jarvis_utils.jsonnet_compat import loads as json_loads


def parse_clusters_from_text(
    text: str,
) -> tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """解析聚类文本，返回(解析结果, 错误信息)"""
    try:
        import re as _re

        # 使用正则表达式进行大小写不敏感的匹配
        pattern = r"<CLUSTERS>([\s\S]*?)</CLUSTERS>"
        match = _re.search(pattern, text, flags=_re.IGNORECASE)
        if not match:
            # 如果正则匹配失败，尝试直接查找（大小写敏感）
            start = text.find("<CLUSTERS>")
            end = text.find("</CLUSTERS>")
            if start == -1 or end == -1 or end <= start:
                return None, "未找到 <CLUSTERS> 或 </CLUSTERS> 标签，或标签顺序错误"
            content = text[start + len("<CLUSTERS>") : end].strip()
        else:
            content = match.group(1).strip()

        if not content:
            return None, "JSON 内容为空"
        try:
            data = json_loads(content)
        except Exception as json_err:
            error_msg = f"JSON 解析失败: {str(json_err)}"
            return None, error_msg
        if isinstance(data, list):
            return data, None
        return None, f"JSON 解析结果不是数组，而是 {type(data).__name__}"
    except Exception as e:
        return None, f"解析过程发生异常: {str(e)}"


def try_parse_summary_report(text: str) -> tuple[Optional[object], Optional[str]]:
    """
    从摘要文本中提取 <REPORT>...</REPORT> 内容，并解析为对象（dict 或 list，使用 JSON）。
    返回(解析结果, 错误信息)
    如果解析成功，返回(data, None)
    如果解析失败，返回(None, 错误信息)
    """
    try:
        import re as _re

        # 使用正则表达式进行大小写不敏感的匹配
        pattern = r"<REPORT>([\s\S]*?)</REPORT>"
        match = _re.search(pattern, text, flags=_re.IGNORECASE)
        if not match:
            # 如果正则匹配失败，尝试直接查找（大小写敏感）
            start = text.find("<REPORT>")
            end = text.find("</REPORT>")
            if start == -1 or end == -1 or end <= start:
                return None, "未找到 <REPORT> 或 </REPORT> 标签，或标签顺序错误"
            content = text[start + len("<REPORT>") : end].strip()
        else:
            content = match.group(1).strip()

        if not content:
            return None, "JSON 内容为空"
        try:
            data = json_loads(content)
        except Exception as json_err:
            error_msg = f"JSON 解析失败: {str(json_err)}"
            return None, error_msg
        if isinstance(data, (dict, list)):
            return data, None
        return None, f"JSON 解析结果不是字典或数组，而是 {type(data).__name__}"
    except Exception as e:
        return None, f"解析过程发生异常: {str(e)}"
