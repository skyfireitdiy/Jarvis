from abc import ABC
from abc import abstractmethod
from typing import List


class EmbeddingInterface(ABC):
    """
    嵌入模型接口的抽象基类。

    该类定义了嵌入模型的标准接口，支持本地模型和在线模型（API）的实现。
    任何嵌入模型提供商（如HuggingFace本地模型、OpenAI API、Cohere API等）
    都应作为该接口的子类来实现。
    """

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        为文档列表计算嵌入。

        参数:
            texts: 要嵌入的文档（字符串）列表。

        返回:
            一个嵌入列表，每个文档对应一个嵌入向量。
        """
        pass

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """
        为单个查询计算嵌入。

        参数:
            text: 要嵌入的查询文本。

        返回:
            查询的嵌入向量。
        """
        pass
