"""
向后兼容模块：保持 Reranker 的导入路径。

新的实现已移动到 rerankers/ 目录。
"""

from .rerankers.local import LocalReranker

# 向后兼容：保持 Reranker 作为 LocalReranker 的别名
Reranker = LocalReranker
