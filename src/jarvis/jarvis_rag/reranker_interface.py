from abc import ABC
from abc import abstractmethod
from typing import List

from langchain.docstore.document import Document


class RerankerInterface(ABC):
    """
    重排模型接口的抽象基类。

    该类定义了重排模型的标准接口，支持本地模型和在线模型（API）的实现。
    任何重排模型提供商（如sentence-transformers CrossEncoder、Cohere Rerank API等）
    都应作为该接口的子类来实现。
    """

    @abstractmethod
    def rerank(
        self, query: str, documents: List[Document], top_n: int = 5
    ) -> List[Document]:
        """
        根据文档与查询的相关性对文档列表进行重排。

        参数:
            query: 用户的查询。
            documents: 从初始搜索中检索到的文档列表。
            top_n: 重排后要返回的顶部文档数。

        返回:
            一个已排序的最相关文档列表。
        """
        pass
