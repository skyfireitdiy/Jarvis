"""
重排模型实现模块。

包含本地和在线重排模型的实现，支持动态加载自定义模型。
"""

from .base import OnlineReranker  # noqa: F401
from .local import LocalReranker
from .registry import RerankerRegistry

# 向后兼容别名
Reranker = LocalReranker

# 在线模型实现（可选导入）
try:
    from .cohere import CohereReranker  # noqa: F401
    from .edgefn import EdgeFnReranker  # noqa: F401
    from .jina import JinaReranker  # noqa: F401

    _base_exports = [
        "OnlineReranker",
        "LocalReranker",
        "Reranker",  # 向后兼容
        "RerankerRegistry",
        "CohereReranker",
        "JinaReranker",
        "EdgeFnReranker",
    ]
except ImportError:
    _base_exports = [
        "OnlineReranker",
        "LocalReranker",
        "Reranker",  # 向后兼容
        "RerankerRegistry",
    ]

# 动态加载的模型（通过 registry）
_registry = RerankerRegistry.get_global_registry()
_dynamic_exports = _registry.get_available_rerankers()

__all__ = _base_exports + _dynamic_exports
