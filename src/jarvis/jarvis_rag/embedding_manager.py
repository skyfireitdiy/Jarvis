import torch
from typing import List, cast
from langchain_huggingface import HuggingFaceEmbeddings

from .cache import EmbeddingCache


class EmbeddingManager:
    """
    管理本地嵌入模型的加载和使用，并带有缓存功能。

    该类负责从Hugging Face加载指定的模型，并使用基于磁盘的缓存
    来避免为相同文本重新计算嵌入。
    """

    def __init__(self, model_name: str, cache_dir: str):
        """
        初始化EmbeddingManager。

        参数:
            model_name: 要加载的Hugging Face模型的名称。
            cache_dir: 用于存储嵌入缓存的目录。
        """
        self.model_name = model_name

        print(f"🚀 初始化嵌入管理器, 模型: '{self.model_name}'...")

        # 缓存的salt是模型名称，以防止冲突
        self.cache = EmbeddingCache(cache_dir=cache_dir, salt=self.model_name)
        self.model = self._load_model()

    def _load_model(self) -> HuggingFaceEmbeddings:
        """根据配置加载Hugging Face嵌入模型。"""
        model_kwargs = {"device": "cuda" if torch.cuda.is_available() else "cpu"}
        encode_kwargs = {"normalize_embeddings": True}

        try:
            return HuggingFaceEmbeddings(
                model_name=self.model_name,
                model_kwargs=model_kwargs,
                encode_kwargs=encode_kwargs,
                show_progress=True,
            )
        except Exception as e:
            print(f"❌ 加载嵌入模型 '{self.model_name}' 时出错: {e}")
            print("请确保您已安装 'sentence_transformers' 和 'torch'。")
            raise

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        使用缓存为文档列表计算嵌入。

        参数:
            texts: 要嵌入的文档（字符串）列表。

        返回:
            一个嵌入列表，每个文档对应一个嵌入。
        """
        if not texts:
            return []

        # 检查缓存中是否已存在嵌入
        cached_embeddings = self.cache.get_batch(texts)

        texts_to_embed = []
        indices_to_embed = []
        for i, (text, cached) in enumerate(zip(texts, cached_embeddings)):
            if cached is None:
                texts_to_embed.append(text)
                indices_to_embed.append(i)

        # 为不在缓存中的文本计算嵌入
        if texts_to_embed:
            print(
                f"🔎 缓存未命中。正在为 {len(texts_to_embed)}/{len(texts)} 个文档计算嵌入。"
            )
            new_embeddings = self.model.embed_documents(texts_to_embed)

            # 将新的嵌入存储在缓存中
            self.cache.set_batch(texts_to_embed, new_embeddings)

            # 将新的嵌入放回结果列表中
            for i, embedding in zip(indices_to_embed, new_embeddings):
                cached_embeddings[i] = embedding
        else:
            print(f"✅ 缓存命中。所有 {len(texts)} 个文档的嵌入均从缓存中检索。")

        return cast(List[List[float]], cached_embeddings)

    def embed_query(self, text: str) -> List[float]:
        """
        为单个查询计算嵌入。
        查询通常不被缓存，但如果需要可以添加。
        """
        return self.model.embed_query(text)
