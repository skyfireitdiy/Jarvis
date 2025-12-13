"""
本地重排模型实现。
"""

from jarvis.jarvis_utils.output import PrettyOutput

import os
from typing import List
from typing import Optional

from huggingface_hub import snapshot_download
from langchain.docstore.document import Document
from sentence_transformers.cross_encoder import CrossEncoder

from ..reranker_interface import RerankerInterface


class LocalReranker(RerankerInterface):
    """
    一个重排器类，使用Cross-Encoder模型根据文档与给定查询的相关性
    对文档进行重新评分和排序。

    这是 RerankerInterface 的本地实现，使用 sentence-transformers CrossEncoder。
    """

    def __init__(self, model_name: str, max_length: Optional[int] = None):
        """
        初始化重排器。

        参数:
            model_name (str): 要使用的Cross-Encoder模型的名称。
            max_length: 模型的最大输入长度（token数），用于文档处理。
        """
        self.max_length = max_length
        PrettyOutput.auto_print(f"ℹ️ 正在初始化重排模型: {model_name}...")
        try:
            local_dir = None

            if os.path.isdir(model_name):
                self.model = CrossEncoder(model_name)
                PrettyOutput.auto_print("✅ 重排模型初始化成功。")
                return
            try:
                # Prefer local cache; avoid any network access
                local_dir = snapshot_download(repo_id=model_name, local_files_only=True)
            except Exception:
                local_dir = None

            if local_dir:
                self.model = CrossEncoder(local_dir)
            else:
                self.model = CrossEncoder(model_name)

            PrettyOutput.auto_print("✅ 重排模型初始化成功。")
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 初始化重排模型失败: {e}")
            raise

    def rerank(
        self, query: str, documents: List[Document], top_n: int = 5
    ) -> List[Document]:
        """
        根据文档与查询的相关性对文档列表进行重排。

        参数:
            query (str): 用户的查询。
            documents (List[Document]): 从初始搜索中检索到的文档列表。
            top_n (int): 重排后要返回的顶部文档数。

        返回:
            List[Document]: 一个已排序的最相关文档列表。
        """
        if not documents:
            return []

        # 创建 [查询, 文档内容] 对用于评分
        pairs = [[query, doc.page_content] for doc in documents]

        # 从Cross-Encoder模型获取分数
        scores = self.model.predict(pairs)

        # 将文档与它们的分数结合并排序
        doc_with_scores = list(zip(documents, scores))
        doc_with_scores.sort(key=lambda x: x[1], reverse=True)

        # 返回前N个文档
        reranked_docs = [doc for doc, score in doc_with_scores[:top_n]]

        return reranked_docs
