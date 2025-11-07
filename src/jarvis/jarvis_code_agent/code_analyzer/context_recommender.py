"""上下文推荐数据结构和基础工具。

保留推荐结果的数据结构和格式化方法。
"""

from dataclasses import dataclass
from typing import List

from .symbol_extractor import Symbol


@dataclass
class ContextRecommendation:
    """上下文推荐结果"""
    recommended_files: List[str]  # 推荐的文件列表
    recommended_symbols: List[Symbol]  # 推荐的符号列表
    related_tests: List[str]  # 相关的测试文件
    reason: str  # 推荐原因
