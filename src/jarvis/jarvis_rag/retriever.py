import os
import pickle
from typing import Any, Dict, List, cast

import chromadb
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi  # type: ignore

from .embedding_manager import EmbeddingManager


class ChromaRetriever:
    """
    一个检索器类，它结合了密集向量搜索（ChromaDB）和稀疏关键字搜索（BM25）
    以实现混合检索。
    """

    def __init__(
        self,
        embedding_manager: EmbeddingManager,
        db_path: str,
        collection_name: str = "jarvis_rag_collection",
    ):
        """
        初始化ChromaRetriever。

        参数:
            embedding_manager: EmbeddingManager的实例。
            db_path: ChromaDB持久化存储的文件路径。
            collection_name: ChromaDB中集合的名称。
        """
        self.embedding_manager = embedding_manager
        self.db_path = db_path
        self.collection_name = collection_name

        # 初始化ChromaDB客户端
        self.client = chromadb.PersistentClient(path=self.db_path)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name
        )
        print(f"✅ ChromaDB 客户端已在 '{db_path}' 初始化，集合为 '{collection_name}'。")

        # BM25索引设置
        self.bm25_index_path = os.path.join(self.db_path, f"{collection_name}_bm25.pkl")
        self._load_or_initialize_bm25()

    def _load_or_initialize_bm25(self):
        """从磁盘加载BM25索引或初始化一个新索引。"""
        if os.path.exists(self.bm25_index_path):
            print("🔍 正在加载现有的 BM25 索引...")
            with open(self.bm25_index_path, "rb") as f:
                data = pickle.load(f)
                self.bm25_corpus = data["corpus"]
                self.bm25_index = BM25Okapi(self.bm25_corpus)
            print("✅ BM25 索引加载成功。")
        else:
            print("⚠️ 未找到 BM25 索引，将初始化一个新的。")
            self.bm25_corpus = []
            self.bm25_index = None

    def _save_bm25_index(self):
        """将BM25索引保存到磁盘。"""
        if self.bm25_index:
            print("💾 正在保存 BM25 索引...")
            with open(self.bm25_index_path, "wb") as f:
                pickle.dump({"corpus": self.bm25_corpus, "index": self.bm25_index}, f)
            print("✅ BM25 索引保存成功。")

    def add_documents(
        self, documents: List[Document], chunk_size=1000, chunk_overlap=100
    ):
        """
        将文档拆分、嵌入，并添加到ChromaDB和BM25索引中。
        """
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        chunks = text_splitter.split_documents(documents)

        print(f"📄 已将 {len(documents)} 个文档拆分为 {len(chunks)} 个块。")

        if not chunks:
            return

        # 提取内容、元数据并生成ID
        chunk_texts = [chunk.page_content for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]
        start_id = self.collection.count()
        ids = [f"doc_{i}" for i in range(start_id, start_id + len(chunks))]

        # 添加到ChromaDB
        embeddings = self.embedding_manager.embed_documents(chunk_texts)
        self.collection.add(
            ids=ids,
            embeddings=cast(Any, embeddings),
            documents=chunk_texts,
            metadatas=cast(Any, metadatas),
        )
        print(f"✅ 成功将 {len(chunks)} 个块添加到 ChromaDB 集合中。")

        # 更新并保存BM25索引
        tokenized_chunks = [doc.split() for doc in chunk_texts]
        self.bm25_corpus.extend(tokenized_chunks)
        self.bm25_index = BM25Okapi(self.bm25_corpus)
        self._save_bm25_index()

    def retrieve(
        self, query: str, n_results: int = 5, use_bm25: bool = True
    ) -> List[Document]:
        """
        使用向量搜索和BM25执行混合检索，然后使用倒数排序融合（RRF）
        对结果进行融合。
        """
        # 1. 向量搜索 (ChromaDB)
        query_embedding = self.embedding_manager.embed_query(query)
        vector_results = self.collection.query(
            query_embeddings=cast(Any, [query_embedding]),
            n_results=n_results * 2,  # 检索更多结果用于融合
        )

        # 2. 关键字搜索 (BM25)
        bm25_docs = []
        if self.bm25_index and use_bm25:
            tokenized_query = query.split()
            doc_scores = self.bm25_index.get_scores(tokenized_query)

            # 从Chroma获取所有文档以匹配BM25分数
            all_docs_in_collection = self.collection.get()
            all_documents = all_docs_in_collection.get("documents")
            all_metadatas = all_docs_in_collection.get("metadatas")

            bm25_results_with_docs = []
            if all_documents and all_metadatas:
                # 创建从索引到文档的映射
                bm25_results_with_docs = [
                    (
                        all_documents[i],
                        all_metadatas[i],
                        score,
                    )
                    for i, score in enumerate(doc_scores)
                    if score > 0
                ]

            # 按分数排序并取最高结果
            bm25_results_with_docs.sort(key=lambda x: x[2], reverse=True)  # type: ignore

            for doc_text, metadata, _ in bm25_results_with_docs[: n_results * 2]:
                bm25_docs.append(Document(page_content=doc_text, metadata=metadata))

        # 3. 倒数排序融合 (RRF)
        fused_scores: Dict[str, float] = {}
        k = 60  # RRF排名常数

        # 处理向量结果
        if vector_results and vector_results["ids"] and vector_results["documents"]:
            vec_ids = vector_results["ids"][0]
            vec_texts = vector_results["documents"][0]

            for rank, doc_id in enumerate(vec_ids):
                fused_scores[doc_id] = fused_scores.get(doc_id, 0) + 1 / (k + rank)

            # 为BM25融合创建从文档文本到其ID的映射
            doc_text_to_id = {text: doc_id for text, doc_id in zip(vec_texts, vec_ids)}

            for rank, doc in enumerate(bm25_docs):
                bm25_doc_id = doc_text_to_id.get(doc.page_content)
                if bm25_doc_id:
                    fused_scores[bm25_doc_id] = fused_scores.get(bm25_doc_id, 0) + 1 / (
                        k + rank
                    )

        # 对融合结果进行排序
        sorted_fused_results = sorted(
            fused_scores.items(), key=lambda x: x[1], reverse=True
        )

        # 根据融合排名从ChromaDB获取最终文档
        final_doc_ids = [item[0] for item in sorted_fused_results[:n_results]]

        if not final_doc_ids:
            return []

        final_docs_data = self.collection.get(ids=final_doc_ids)

        retrieved_docs = []
        if final_docs_data:
            final_documents = final_docs_data.get("documents")
            final_metadatas = final_docs_data.get("metadatas")

            if final_documents and final_metadatas:
                for doc_text, metadata in zip(final_documents, final_metadatas):
                    if doc_text is not None and metadata is not None:
                        retrieved_docs.append(
                            Document(
                                page_content=cast(str, doc_text), metadata=metadata
                            )
                        )

        return retrieved_docs
