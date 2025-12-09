"""
Jarvis RAG 框架

一个灵活的RAG管道，具有可插拔的远程LLM和本地/在线嵌入模型和重排模型。
"""

from .rag_pipeline import JarvisRAGPipeline
from .llm_interface import LLMInterface
from .embedding_interface import EmbeddingInterface
from .reranker_interface import RerankerInterface

# 从新的目录结构导入
from .embeddings import (
    EmbeddingManager,  # 向后兼容别名
    LocalEmbeddingModel,
    EmbeddingRegistry,
)
from .rerankers import (
    Reranker,  # 向后兼容别名
    LocalReranker,
    RerankerRegistry,
)

# 在线模型实现（可选导入）
try:
    from .embeddings import (
        OnlineEmbeddingModel,
        OpenAIEmbeddingModel,
        CohereEmbeddingModel,
        EdgeFnEmbeddingModel,
    )
    from .rerankers import (
        OnlineReranker,
        CohereReranker,
        JinaReranker,
        EdgeFnReranker,
    )

    __all__ = [
        "JarvisRAGPipeline",
        "LLMInterface",
        "EmbeddingInterface",
        "EmbeddingManager",  # 向后兼容别名
        "LocalEmbeddingModel",
        "EmbeddingRegistry",
        "RerankerInterface",
        "Reranker",  # 向后兼容别名
        "LocalReranker",
        "RerankerRegistry",
        "OnlineEmbeddingModel",
        "OpenAIEmbeddingModel",
        "CohereEmbeddingModel",
        "EdgeFnEmbeddingModel",
        "OnlineReranker",
        "CohereReranker",
        "JinaReranker",
        "EdgeFnReranker",
    ]
except ImportError:
    # 如果在线模型依赖未安装，只导出基础接口
    __all__ = [
        "JarvisRAGPipeline",
        "LLMInterface",
        "EmbeddingInterface",
        "EmbeddingManager",  # 向后兼容别名
        "LocalEmbeddingModel",
        "EmbeddingRegistry",
        "RerankerInterface",
        "Reranker",  # 向后兼容别名
        "LocalReranker",
        "RerankerRegistry",
    ]
