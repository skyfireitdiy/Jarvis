from typing import List, Literal, cast
from langchain_huggingface import HuggingFaceEmbeddings

from jarvis.jarvis_utils.config import (
    get_rag_embedding_models,
    get_rag_embedding_cache_path,
)
from .cache import EmbeddingCache


class EmbeddingManager:
    """
    Manages the loading and usage of local embedding models with caching.

    This class handles the selection of embedding models based on a specified
    mode ('performance' or 'accuracy'), loads the model from Hugging Face,
    and uses a disk-based cache to avoid re-computing embeddings for the
    same text.
    """

    def __init__(
        self,
        mode: Literal["performance", "accuracy"],
        cache_dir: str,
    ):
        """
        Initializes the EmbeddingManager.

        Args:
            mode: The desired mode, either 'performance' or 'accuracy'.
            cache_dir: The directory to store the embedding cache.
        """
        self.mode = mode
        self.embedding_models = get_rag_embedding_models()
        if mode not in self.embedding_models:
            raise ValueError(
                f"Invalid mode '{mode}'. Must be one of {list(self.embedding_models.keys())}"
            )

        self.model_config = self.embedding_models[self.mode]
        self.model_name = self.model_config["model_name"]

        print(f"🚀 初始化嵌入管理器，模式: '{self.mode}', 模型: '{self.model_name}'...")

        # The salt for the cache is the model name to prevent collisions
        self.cache = EmbeddingCache(cache_dir=cache_dir, salt=str(self.model_name))
        self.model = self._load_model()

    def _load_model(self) -> HuggingFaceEmbeddings:
        """Loads the Hugging Face embedding model based on the configuration."""
        try:
            return HuggingFaceEmbeddings(
                model_name=self.model_name,
                model_kwargs=self.model_config.get("model_kwargs"),
                encode_kwargs=self.model_config.get("encode_kwargs"),
                show_progress=self.model_config.get("show_progress", False),
            )
        except Exception as e:
            print(f"❌ 加载嵌入模型 '{self.model_name}' 时出错: {e}")
            print("请确保您已安装 'sentence_transformers' 和 'torch'。")
            raise

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Computes embeddings for a list of documents, using the cache.

        Args:
            texts: A list of documents (strings) to embed.

        Returns:
            A list of embeddings, one for each document.
        """
        if not texts:
            return []

        # Check cache for existing embeddings
        cached_embeddings = self.cache.get_batch(texts)

        texts_to_embed = []
        indices_to_embed = []
        for i, (text, cached) in enumerate(zip(texts, cached_embeddings)):
            if cached is None:
                texts_to_embed.append(text)
                indices_to_embed.append(i)

        # Compute embeddings for texts that were not in the cache
        if texts_to_embed:
            print(
                f"🔎 缓存未命中。正在为 {len(texts_to_embed)}/{len(texts)} 个文档计算嵌入。"
            )
            new_embeddings = self.model.embed_documents(texts_to_embed)

            # Store new embeddings in the cache
            self.cache.set_batch(texts_to_embed, new_embeddings)

            # Place new embeddings back into the results list
            for i, embedding in zip(indices_to_embed, new_embeddings):
                cached_embeddings[i] = embedding
        else:
            print(f"✅ 缓存命中。所有 {len(texts)} 个文档的嵌入均从缓存中检索。")

        return cast(List[List[float]], cached_embeddings)

    def embed_query(self, text: str) -> List[float]:
        """
        Computes the embedding for a single query.
        Queries are typically not cached, but we can add it if needed.
        """
        return self.model.embed_query(text)
