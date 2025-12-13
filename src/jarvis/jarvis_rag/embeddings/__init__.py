"""
嵌入模型实现模块。

包含本地和在线嵌入模型的实现，支持动态加载自定义模型。
"""

from .base import OnlineEmbeddingModel  # noqa: F401
from .local import LocalEmbeddingModel
from .registry import EmbeddingRegistry

# 向后兼容别名
EmbeddingManager = LocalEmbeddingModel

# 在线模型实现（可选导入）
try:
    from .cohere import CohereEmbeddingModel  # noqa: F401
    from .edgefn import EdgeFnEmbeddingModel  # noqa: F401
    from .openai import OpenAIEmbeddingModel  # noqa: F401

    _base_exports = [
        "OnlineEmbeddingModel",
        "LocalEmbeddingModel",
        "EmbeddingManager",  # 向后兼容
        "EmbeddingRegistry",
        "OpenAIEmbeddingModel",
        "CohereEmbeddingModel",
        "EdgeFnEmbeddingModel",
    ]
except ImportError:
    _base_exports = [
        "OnlineEmbeddingModel",
        "LocalEmbeddingModel",
        "EmbeddingManager",  # 向后兼容
        "EmbeddingRegistry",
    ]

# 动态加载的模型（通过 registry）
_registry = EmbeddingRegistry.get_global_registry()
_dynamic_exports = _registry.get_available_embeddings()

__all__ = _base_exports + _dynamic_exports
