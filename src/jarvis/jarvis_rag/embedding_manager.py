"""
向后兼容模块：保持 EmbeddingManager 的导入路径。

新的实现已移动到 embeddings/ 目录。
"""

from .embeddings.local import LocalEmbeddingModel

# 向后兼容：保持 EmbeddingManager 作为 LocalEmbeddingModel 的别名
EmbeddingManager = LocalEmbeddingModel
