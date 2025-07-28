import os
from typing import List, Optional

from langchain.docstore.document import Document

from .embedding_manager import EmbeddingManager
from .llm_interface import JarvisPlatform_LLM, LLMInterface, ToolAgent_LLM
from .query_rewriter import QueryRewriter
from .reranker import Reranker
from .retriever import ChromaRetriever
from jarvis.jarvis_utils.config import (
    get_rag_embedding_model,
    get_rag_rerank_model,
    get_rag_vector_db_path,
    get_rag_embedding_cache_path,
)


class JarvisRAGPipeline:
    """
    RAG管道的主要协调器。

    该类集成了嵌入管理器、检索器和LLM，为添加文档和查询
    提供了一个完整的管道。
    """

    def __init__(
        self,
        llm: Optional[LLMInterface] = None,
        embedding_model: Optional[str] = None,
        db_path: Optional[str] = None,
        collection_name: str = "jarvis_rag_collection",
        use_bm25: bool = True,
        use_rerank: bool = True,
    ):
        """
        初始化RAG管道。

        参数:
            llm: 实现LLMInterface接口的类的实例。
                 如果为None，则默认为ToolAgent_LLM。
            embedding_model: 嵌入模型的名称。如果为None，则使用配置值。
            db_path: 持久化向量数据库的路径。如果为None，则使用配置值。
            collection_name: 向量数据库中集合的名称。
            use_bm25: 是否在检索中使用BM25。
            use_rerank: 是否在检索后使用重排器。
        """
        # 确定嵌入模型以隔离数据路径
        model_name = embedding_model or get_rag_embedding_model()
        sanitized_model_name = model_name.replace("/", "_").replace("\\", "_")

        # 如果给定了特定的db_path，则使用它。否则，创建一个特定于模型的路径。
        _final_db_path = (
            str(db_path)
            if db_path
            else os.path.join(get_rag_vector_db_path(), sanitized_model_name)
        )
        # 始终创建一个特定于模型的缓存路径。
        _final_cache_path = os.path.join(
            get_rag_embedding_cache_path(), sanitized_model_name
        )

        # 存储初始化参数以供延迟加载
        self.llm = llm if llm is not None else ToolAgent_LLM()
        self.embedding_model_name = embedding_model or get_rag_embedding_model()
        self.db_path = db_path
        self.collection_name = collection_name
        self.use_bm25 = use_bm25
        self.use_rerank = use_rerank

        # 延迟加载的组件
        self._embedding_manager: Optional[EmbeddingManager] = None
        self._retriever: Optional[ChromaRetriever] = None
        self._reranker: Optional[Reranker] = None
        self._query_rewriter: Optional[QueryRewriter] = None

        print("✅ JarvisRAGPipeline 初始化成功 (模型按需加载).")

    def _get_embedding_manager(self) -> EmbeddingManager:
        if self._embedding_manager is None:
            sanitized_model_name = self.embedding_model_name.replace("/", "_").replace(
                "\\", "_"
            )
            _final_cache_path = os.path.join(
                get_rag_embedding_cache_path(), sanitized_model_name
            )
            self._embedding_manager = EmbeddingManager(
                model_name=self.embedding_model_name,
                cache_dir=_final_cache_path,
            )
        return self._embedding_manager

    def _get_retriever(self) -> ChromaRetriever:
        if self._retriever is None:
            sanitized_model_name = self.embedding_model_name.replace("/", "_").replace(
                "\\", "_"
            )
            _final_db_path = (
                str(self.db_path)
                if self.db_path
                else os.path.join(get_rag_vector_db_path(), sanitized_model_name)
            )
            self._retriever = ChromaRetriever(
                embedding_manager=self._get_embedding_manager(),
                db_path=_final_db_path,
                collection_name=self.collection_name,
            )
        return self._retriever

    def _get_collection(self):
        """
        在不加载嵌入模型的情况下，直接获取并返回Chroma集合对象。
        这对于仅需要访问集合元数据（如列出文档）而无需嵌入功能的操作非常有用。
        """
        # 为了避免初始化embedding_manager，我们直接构建db_path
        if self._retriever:
            return self._retriever.collection

        sanitized_model_name = self.embedding_model_name.replace("/", "_").replace(
            "\\", "_"
        )
        _final_db_path = (
            str(self.db_path)
            if self.db_path
            else os.path.join(get_rag_vector_db_path(), sanitized_model_name)
        )

        # 直接创建ChromaRetriever所使用的chroma_client，但绕过embedding_manager
        import chromadb

        chroma_client = chromadb.PersistentClient(path=_final_db_path)
        return chroma_client.get_collection(name=self.collection_name)

    def _get_reranker(self) -> Reranker:
        if self._reranker is None:
            self._reranker = Reranker(model_name=get_rag_rerank_model())
        return self._reranker

    def _get_query_rewriter(self) -> QueryRewriter:
        if self._query_rewriter is None:
            # 使用标准LLM执行查询重写任务，而不是代理
            self._query_rewriter = QueryRewriter(JarvisPlatform_LLM())
        return self._query_rewriter

    def add_documents(self, documents: List[Document]):
        """
        将文档添加到向量知识库。

        参数:
            documents: 要添加的LangChain文档对象列表。
        """
        self._get_retriever().add_documents(documents)

    def _create_prompt(self, query: str, context_docs: List[Document]) -> str:
        """为LLM或代理创建最终的提示。"""
        context_details = []
        for doc in context_docs:
            source = doc.metadata.get("source", "未知来源")
            content = doc.page_content
            context_details.append(f"来源: {source}\n\n---\n{content}\n---")
        context = "\n\n".join(context_details)

        prompt_template = f"""
        你是一个专家助手。请根据用户的问题，结合下面提供的参考信息来回答。

        **重要**: 提供的上下文**仅供参考**，可能不完整或已过时。在回答前，你应该**优先使用工具（如 read_code）来获取最新、最准确的信息**。

        参考上下文:
        ---
        {context}
        ---

        问题: {query}

        回答:
        """
        return prompt_template.strip()

    def query(self, query_text: str, n_results: int = 5) -> str:
        """
        使用多查询检索和重排管道对知识库执行查询。

        参数:
            query_text: 用户的原始问题。
            n_results: 要检索的最终相关块的数量。

        返回:
            由LLM生成的答案。
        """
        # 1. 将原始查询重写为多个查询
        rewritten_queries = self._get_query_rewriter().rewrite(query_text)

        # 2. 为每个重写的查询检索初始候选文档
        all_candidate_docs = []
        for q in rewritten_queries:
            print(f"🔍 正在为查询变体 '{q}' 进行混合检索...")
            candidates = self._get_retriever().retrieve(
                q, n_results=n_results * 2, use_bm25=self.use_bm25
            )
            all_candidate_docs.extend(candidates)

        # 对候选文档进行去重
        unique_docs_dict = {doc.page_content: doc for doc in all_candidate_docs}
        unique_candidate_docs = list(unique_docs_dict.values())

        if not unique_candidate_docs:
            return "我在提供的文档中找不到任何相关信息来回答您的问题。"

        # 3. 根据*原始*查询对统一的候选池进行重排
        if self.use_rerank:
            print(f"🔍 正在对 {len(unique_candidate_docs)} 个候选文档进行重排（基于原始问题）...")
            retrieved_docs = self._get_reranker().rerank(
                query_text, unique_candidate_docs, top_n=n_results
            )
        else:
            retrieved_docs = unique_candidate_docs[:n_results]

        if not retrieved_docs:
            return "我在提供的文档中找不到任何相关信息来回答您的问题。"

        # 打印最终检索到的文档的来源
        sources = sorted(
            list(
                {
                    doc.metadata["source"]
                    for doc in retrieved_docs
                    if "source" in doc.metadata
                }
            )
        )
        if sources:
            print(f"📚 根据以下文档回答:")
            for source in sources:
                print(f"  - {source}")

        # 4. 创建最终提示并生成答案
        # 我们使用原始的query_text作为给LLM的最终提示
        prompt = self._create_prompt(query_text, retrieved_docs)

        print("🤖 正在从LLM生成答案...")
        answer = self.llm.generate(prompt)

        return answer

    def retrieve_only(self, query_text: str, n_results: int = 5) -> List[Document]:
        """
        仅执行检索和重排，不生成答案。

        参数:
            query_text: 用户的原始问题。
            n_results: 要检索的最终相关块的数量。

        返回:
            检索到的文档列表。
        """
        # 1. 重写查询
        rewritten_queries = self._get_query_rewriter().rewrite(query_text)

        # 2. 检索候选文档
        all_candidate_docs = []
        for q in rewritten_queries:
            print(f"🔍 正在为查询变体 '{q}' 进行混合检索...")
            candidates = self._get_retriever().retrieve(
                q, n_results=n_results * 2, use_bm25=self.use_bm25
            )
            all_candidate_docs.extend(candidates)

        unique_docs_dict = {doc.page_content: doc for doc in all_candidate_docs}
        unique_candidate_docs = list(unique_docs_dict.values())

        if not unique_candidate_docs:
            return []

        # 3. 重排
        if self.use_rerank:
            print(f"🔍 正在对 {len(unique_candidate_docs)} 个候选文档进行重排...")
            retrieved_docs = self._get_reranker().rerank(
                query_text, unique_candidate_docs, top_n=n_results
            )
        else:
            retrieved_docs = unique_candidate_docs[:n_results]

        return retrieved_docs
