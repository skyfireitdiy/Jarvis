from typing import List

from langchain.docstore.document import Document
from sentence_transformers.cross_encoder import (  # type: ignore
    CrossEncoder,
)


class Reranker:
    """
    A reranker class that uses a Cross-Encoder model to re-score and sort
    documents based on their relevance to a given query.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-base"):
        """
        Initializes the Reranker.

        Args:
            model_name (str): The name of the Cross-Encoder model to use.
        """
        print(f"🔍 正在初始化重排模型: {model_name}...")
        self.model = CrossEncoder(model_name)
        print("✅ 重排模型初始化成功。")

    def rerank(
        self, query: str, documents: List[Document], top_n: int = 5
    ) -> List[Document]:
        """
        Reranks a list of documents based on their relevance to the query.

        Args:
            query (str): The user's query.
            documents (List[Document]): The list of documents retrieved from the initial search.
            top_n (int): The number of top documents to return after reranking.

        Returns:
            List[Document]: A sorted list of the most relevant documents.
        """
        if not documents:
            return []

        # Create pairs of [query, document_content] for scoring
        pairs = [[query, doc.page_content] for doc in documents]

        # Get scores from the Cross-Encoder model
        scores = self.model.predict(pairs)

        # Combine documents with their scores and sort
        doc_with_scores = list(zip(documents, scores))
        doc_with_scores.sort(key=lambda x: x[1], reverse=True)

        # Return the top N documents
        reranked_docs = [doc for doc, score in doc_with_scores[:top_n]]

        return reranked_docs
