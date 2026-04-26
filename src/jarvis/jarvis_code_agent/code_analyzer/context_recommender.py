"""上下文推荐数据结构和基础工具。

保留推荐结果的数据结构和格式化方法。
"""

from dataclasses import dataclass
from typing import List

from .symbol_extractor import Symbol


@dataclass
class ContextRecommendation:
    """上下文推荐结果

    推荐符号在文件中的位置信息。
    """

    recommended_symbols: List[Symbol]  # 推荐的符号列表（包含文件路径和行号）
