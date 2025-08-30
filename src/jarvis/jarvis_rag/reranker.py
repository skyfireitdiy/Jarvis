from typing import List
import os

from langchain.docstore.document import Document
from sentence_transformers.cross_encoder import (  # type: ignore
    CrossEncoder,
)
from huggingface_hub import snapshot_download
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from contextlib import contextmanager

@contextmanager
def _enforce_hf_offline():
    old_hf = os.environ.get("HF_HUB_OFFLINE")
    old_tf = os.environ.get("TRANSFORMERS_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        yield
    finally:
        if old_hf is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = old_hf
        if old_tf is None:
            os.environ.pop("TRANSFORMERS_OFFLINE", None)
        else:
            os.environ["TRANSFORMERS_OFFLINE"] = old_tf


class Reranker:
    """
    一个重排器类，使用Cross-Encoder模型根据文档与给定查询的相关性
    对文档进行重新评分和排序。
    """

    def __init__(self, model_name: str):
        """
        初始化重排器。

        参数:
            model_name (str): 要使用的Cross-Encoder模型的名称。
        """
        PrettyOutput.print(f"正在初始化重排模型: {model_name}...", OutputType.INFO)
        try:
            local_dir = None
            # Prefer explicit local dir via env or direct path
            explicit_local = os.environ.get("JARVIS_RAG_RERANK_LOCAL_DIR", "").strip()
            if explicit_local and os.path.isdir(explicit_local):
                with _enforce_hf_offline():
                    self.model = CrossEncoder(explicit_local)
                PrettyOutput.print("重排模型初始化成功。", OutputType.SUCCESS)
                return
            if os.path.isdir(model_name):
                with _enforce_hf_offline():
                    self.model = CrossEncoder(model_name)
                PrettyOutput.print("重排模型初始化成功。", OutputType.SUCCESS)
                return
            try:
                # Prefer local cache; avoid any network access
                local_dir = snapshot_download(repo_id=model_name, local_files_only=True)
            except Exception:
                local_dir = None

            if local_dir:
                with _enforce_hf_offline():
                    self.model = CrossEncoder(local_dir)
            else:
                # Determine offline mode; if offline, do not attempt remote
                offline = (
                    os.environ.get("HF_HUB_OFFLINE", "").lower() in {"1", "true", "yes"}
                    or os.environ.get("JARVIS_OFFLINE", "").lower() in {"1", "true", "yes"}
                )
                if offline:
                    raise RuntimeError(
                        "离线模式已启用，但未在本地缓存中找到重排模型。请预先下载模型或设置 HF_HOME/HUGGINGFACE_HUB_CACHE 指向包含该模型缓存的目录。"
                    )
                # Fallback to remote if not offline
                self.model = CrossEncoder(model_name)

            PrettyOutput.print("重排模型初始化成功。", OutputType.SUCCESS)
        except Exception as e:
            PrettyOutput.print(f"初始化重排模型失败: {e}", OutputType.ERROR)
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
        doc_with_scores.sort(key=lambda x: x[1], reverse=True)  # type: ignore

        # 返回前N个文档
        reranked_docs = [doc for doc, score in doc_with_scores[:top_n]]

        return reranked_docs
