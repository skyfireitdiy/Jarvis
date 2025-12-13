"""
在线重排模型的基类实现。
"""

import os
from typing import List
from typing import Optional

from langchain.docstore.document import Document

from ..reranker_interface import RerankerInterface


class OnlineReranker(RerankerInterface):
    """
    在线重排模型的基类实现。

    这是一个抽象基类，定义了在线重排模型的基本结构。
    子类需要实现具体的API调用逻辑。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_key_env: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        top_n: int = 5,
        max_length: Optional[int] = None,
        **kwargs,
    ):
        """
        初始化在线重排模型。

        参数:
            api_key: API密钥。如果为None，将从环境变量中读取。
            api_key_env: 用于读取API密钥的环境变量名。
            base_url: API的基础URL。
            model_name: 要使用的模型名称。
            top_n: 默认返回的顶部文档数。
            max_length: 模型的最大输入长度（token数），用于文档处理。
            **kwargs: 其他配置参数（可能包含从 reranker_config 传入的配置）。
        """
        # 优先从 kwargs 中读取 api_key（可能来自 reranker_config）
        # 如果没有，则使用传入的 api_key 参数
        # 最后才从环境变量读取（向后兼容）
        self.api_key = (
            kwargs.get("api_key")
            or api_key
            or (os.getenv(api_key_env) if api_key_env else None)
        )
        if not self.api_key:
            raise ValueError(
                f"API密钥未提供。请通过api_key参数、reranker_config配置或环境变量{api_key_env}提供。"
            )

        # 如果 base_url 在 kwargs 中，优先使用
        if "base_url" in kwargs and kwargs["base_url"]:
            self.base_url = kwargs["base_url"]
        else:
            self.base_url = base_url

        self.model_name = model_name
        self.default_top_n = top_n
        self.max_length = max_length

    def _call_api(self, query: str, documents: List[str]) -> List[tuple[int, float]]:
        """
        调用在线API获取重排分数。

        参数:
            query: 查询文本。
            documents: 文档文本列表。

        返回:
            包含 (索引, 分数) 元组的列表，按分数降序排序。

        注意:
            子类必须实现此方法。
        """
        raise NotImplementedError("子类必须实现 _call_api 方法")

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
        if not documents:
            return []

        # 提取文档内容
        doc_texts = [doc.page_content for doc in documents]

        # 调用API获取重排分数
        scored_indices = self._call_api(query, doc_texts)

        # 根据分数排序并返回前top_n个文档
        reranked_docs = [documents[idx] for idx, _ in scored_indices[:top_n]]

        return reranked_docs
