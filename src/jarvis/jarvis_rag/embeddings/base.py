"""
在线嵌入模型的基类实现。
"""

import os
from typing import List
from typing import Optional

from ..embedding_interface import EmbeddingInterface


class OnlineEmbeddingModel(EmbeddingInterface):
    """
    在线嵌入模型的基类实现。

    这是一个抽象基类，定义了在线嵌入模型的基本结构。
    子类需要实现具体的API调用逻辑。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_key_env: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: str = "text-embedding-3-small",
        batch_size: int = 100,
        max_length: Optional[int] = None,
        **kwargs,
    ):
        """
        初始化在线嵌入模型。

        参数:
            api_key: API密钥。如果为None，将从环境变量中读取。
            api_key_env: 用于读取API密钥的环境变量名。
            base_url: API的基础URL。
            model_name: 要使用的模型名称。
            batch_size: 批量处理时的批次大小。
            max_length: 模型的最大输入长度（token数），用于文档分割。
            **kwargs: 其他配置参数（可能包含从 embedding_config 传入的配置）。
        """
        # 优先从 kwargs 中读取 api_key（可能来自 embedding_config）
        # 如果没有，则使用传入的 api_key 参数
        # 最后才从环境变量读取（向后兼容）
        self.api_key = (
            kwargs.get("api_key")
            or api_key
            or (os.getenv(api_key_env) if api_key_env else None)
        )
        if not self.api_key:
            raise ValueError(
                f"API密钥未提供。请通过api_key参数、embedding_config配置或环境变量{api_key_env}提供。"
            )

        # 如果 base_url 在 kwargs 中，优先使用
        if "base_url" in kwargs and kwargs["base_url"]:
            self.base_url = kwargs["base_url"]
        else:
            self.base_url = base_url

        self.model_name = model_name
        self.batch_size = batch_size
        self.max_length = max_length

    def _call_api(self, texts: List[str], is_query: bool = False) -> List[List[float]]:
        """
        调用在线API获取嵌入。

        参数:
            texts: 要嵌入的文本列表。
            is_query: 是否为查询（某些API对查询和文档有不同的端点）。

        返回:
            嵌入向量列表。

        注意:
            子类必须实现此方法。
        """
        raise NotImplementedError("子类必须实现 _call_api 方法")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        为文档列表计算嵌入。

        参数:
            texts: 要嵌入的文档（字符串）列表。

        返回:
            一个嵌入列表，每个文档对应一个嵌入向量。
        """
        if not texts:
            return []

        # 批量处理以优化API调用
        all_embeddings = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            batch_embeddings = self._call_api(batch, is_query=False)
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    def embed_query(self, text: str) -> List[float]:
        """
        为单个查询计算嵌入。

        参数:
            text: 要嵌入的查询文本。

        返回:
            查询的嵌入向量。
        """
        embeddings = self._call_api([text], is_query=True)
        return embeddings[0] if embeddings else []
