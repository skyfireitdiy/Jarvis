import os
import pickle
import json
import hashlib
from typing import Any, Dict, List, Optional, cast

import chromadb
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi  # type: ignore

from .embedding_manager import EmbeddingManager
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


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
        PrettyOutput.print(
            f"ChromaDB 客户端已在 '{db_path}' 初始化，集合为 '{collection_name}'。",
            OutputType.SUCCESS,
        )

        # BM25索引设置
        self.bm25_index_path = os.path.join(self.db_path, f"{collection_name}_bm25.pkl")
        self._load_or_initialize_bm25()
        # 清单文件用于检测源文件的变更/删除
        self.manifest_path = os.path.join(
            self.db_path, f"{collection_name}_manifest.json"
        )

    def _load_or_initialize_bm25(self):
        """从磁盘加载BM25索引或初始化一个新索引。"""
        if os.path.exists(self.bm25_index_path):
            PrettyOutput.print("正在加载现有的 BM25 索引...", OutputType.INFO)
            with open(self.bm25_index_path, "rb") as f:
                data = pickle.load(f)
                self.bm25_corpus = data["corpus"]
                self.bm25_index = BM25Okapi(self.bm25_corpus)
            PrettyOutput.print("BM25 索引加载成功。", OutputType.SUCCESS)
        else:
            PrettyOutput.print(
                "未找到 BM25 索引，将初始化一个新的。", OutputType.WARNING
            )
            self.bm25_corpus = []
            self.bm25_index = None

    def _save_bm25_index(self):
        """将BM25索引保存到磁盘。"""
        if self.bm25_index:
            PrettyOutput.print("正在保存 BM25 索引...", OutputType.INFO)
            with open(self.bm25_index_path, "wb") as f:
                pickle.dump({"corpus": self.bm25_corpus, "index": self.bm25_index}, f)
            PrettyOutput.print("BM25 索引保存成功。", OutputType.SUCCESS)

    def _load_manifest(self) -> Dict[str, Dict[str, Any]]:
        """加载已索引文件清单，用于变更检测。"""
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data  # type: ignore[return-value]
            except Exception:
                pass
        return {}

    def _save_manifest(self, manifest: Dict[str, Dict[str, Any]]) -> None:
        """保存已索引文件清单。"""
        try:
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
        except Exception as e:
            PrettyOutput.print(f"保存索引清单失败: {e}", OutputType.WARNING)

    def _compute_md5(
        self, file_path: str, chunk_size: int = 1024 * 1024
    ) -> Optional[str]:
        """流式计算文件的MD5，避免占用过多内存。失败时返回None。"""
        try:
            md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                while True:
                    data = f.read(chunk_size)
                    if not data:
                        break
                    md5.update(data)
            return md5.hexdigest()
        except Exception:
            return None

    def _update_manifest_with_sources(self, sources: List[str]) -> None:
        """根据本次新增文档的来源，更新索引清单（记录mtime与size）。"""
        manifest = self._load_manifest()
        updated = 0
        for src in set(sources):
            try:
                if isinstance(src, str) and os.path.exists(src):
                    st = os.stat(src)
                    entry: Dict[str, Any] = {
                        "mtime": float(st.st_mtime),
                        "size": int(st.st_size),
                    }
                    md5sum = self._compute_md5(src)
                    if md5sum:
                        entry["md5"] = md5sum
                    manifest[src] = entry  # type: ignore[dict-item]
                    updated += 1
            except Exception:
                continue
        if updated > 0:
            self._save_manifest(manifest)
            PrettyOutput.print(
                f"已更新索引清单，记录 {updated} 个源文件状态。", OutputType.INFO
            )

    def _detect_changed_or_deleted(self) -> Dict[str, List[str]]:
        """检测已记录的源文件是否发生变化或被删除。"""
        manifest = self._load_manifest()
        changed: List[str] = []
        deleted: List[str] = []
        for src, info in manifest.items():
            try:
                if not os.path.exists(src):
                    deleted.append(src)
                    continue
                st = os.stat(src)
                size_changed = int(info.get("size", -1)) != int(st.st_size)
                if size_changed:
                    changed.append(src)
                    continue
                md5_old = info.get("md5")
                if md5_old:
                    # 仅在mtime变化时计算md5以降低开销
                    mtime_changed = (
                        abs(float(info.get("mtime", 0.0)) - float(st.st_mtime)) >= 1e-6
                    )
                    if mtime_changed:
                        md5_new = self._compute_md5(src)
                        if not md5_new or md5_new != md5_old:
                            changed.append(src)
                else:
                    # 没有记录md5，回退使用mtime判断
                    mtime_changed = (
                        abs(float(info.get("mtime", 0.0)) - float(st.st_mtime)) >= 1e-6
                    )
                    if mtime_changed:
                        changed.append(src)
            except Exception:
                # 无法读取文件状态，视为发生变化
                changed.append(src)
        return {"changed": changed, "deleted": deleted}

    def _warn_if_sources_changed(self) -> None:
        """如发现已索引文件变化或删除，给出提醒。"""
        result = self._detect_changed_or_deleted()
        changed = result["changed"]
        deleted = result["deleted"]
        if not changed and not deleted:
            return
        # 为避免在循环中逐条打印，先拼接后统一打印
        lines: list[str] = []
        if changed:
            lines.append(
                f"检测到 {len(changed)} 个已索引文件发生变化，建议重新索引以保证检索准确性。"
            )
            lines.extend([f"  变更: {p}" for p in changed[:5]])
            if len(changed) > 5:
                lines.append(f"  ... 以及另外 {len(changed) - 5} 个文件")
        if deleted:
            lines.append(
                f"检测到 {len(deleted)} 个已索引文件已被删除，建议清理并重新索引。"
            )
            lines.extend([f"  删除: {p}" for p in deleted[:5]])
            if len(deleted) > 5:
                lines.append(f"  ... 以及另外 {len(deleted) - 5} 个文件")
        lines.append(
            "提示：请使用 'jarvis-rag add <路径>' 重新索引相关文件，以更新向量库与BM25索引。"
        )
        PrettyOutput.print("\n".join(lines), OutputType.WARNING)

    def detect_index_changes(self) -> Dict[str, List[str]]:
        """
        公共方法：检测索引变更（变更与删除）。
        返回:
            {'changed': List[str], 'deleted': List[str]}
        """
        return self._detect_changed_or_deleted()

    def _remove_sources_from_manifest(self, sources: List[str]) -> None:
        """从manifest中移除指定源文件记录并保存。"""
        if not sources:
            return
        manifest = self._load_manifest()
        removed = 0
        for src in set(sources):
            if src in manifest:
                manifest.pop(src, None)
                removed += 1
        if removed > 0:
            self._save_manifest(manifest)
            PrettyOutput.print(
                f"已从索引清单中移除 {removed} 个已删除的源文件记录。", OutputType.INFO
            )

    def update_index_for_changes(self, changed: List[str], deleted: List[str]) -> None:
        """
        公共方法：根据变更与删除列表更新索引。
        - 对 deleted: 从向量库按 metadata.source 删除
        - 对 changed: 先删除旧条目，再从源文件重建并添加
        - 最后：从集合重建BM25索引，更新manifest
        """
        changed = list(
            dict.fromkeys([p for p in (changed or []) if isinstance(p, str)])
        )
        deleted = list(
            dict.fromkeys([p for p in (deleted or []) if isinstance(p, str)])
        )

        if not changed and not deleted:
            return

        # 先处理删除
        delete_errors: list[str] = []
        for src in deleted:
            try:
                self.collection.delete(where={"source": src})  # type: ignore[arg-type]
            except Exception as e:
                delete_errors.append(f"删除源 '{src}' 时出错: {e}")
        if delete_errors:
            PrettyOutput.print("\n".join(delete_errors), OutputType.WARNING)

        # 再处理变更（重建）
        docs_to_add: List[Document] = []
        rebuild_errors: list[str] = []
        for src in changed:
            try:
                # 删除旧条目
                try:
                    self.collection.delete(where={"source": src})  # type: ignore[arg-type]
                except Exception:
                    pass
                # 读取源文件内容（作为单文档载入，由 add_documents 进行拆分与嵌入）
                with open(src, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                docs_to_add.append(
                    Document(page_content=content, metadata={"source": src})
                )
            except Exception as e:
                rebuild_errors.append(f"重建源 '{src}' 内容时出错: {e}")
        if rebuild_errors:
            PrettyOutput.print("\n".join(rebuild_errors), OutputType.WARNING)

        if docs_to_add:
            try:
                # 复用现有拆分与嵌入逻辑
                self.add_documents(docs_to_add)
            except Exception as e:
                PrettyOutput.print(f"添加变更文档到索引时出错: {e}", OutputType.ERROR)

        # 重建BM25索引，确保删除后的语料被清理
        try:
            all_docs_in_collection = self.collection.get()
            all_documents = all_docs_in_collection.get("documents") or []
            self.bm25_corpus = [str(text).split() for text in all_documents if text]
            self.bm25_index = BM25Okapi(self.bm25_corpus) if self.bm25_corpus else None
            self._save_bm25_index()
        except Exception as e:
            PrettyOutput.print(f"重建BM25索引失败: {e}", OutputType.WARNING)

        # 更新manifest：变更文件更新状态；删除文件从清单中移除
        try:
            if changed:
                self._update_manifest_with_sources(changed)
            if deleted:
                self._remove_sources_from_manifest(deleted)
        except Exception as e:
            PrettyOutput.print(f"更新索引清单时出错: {e}", OutputType.WARNING)

        PrettyOutput.print(
            f"索引已更新：变更 {len(changed)} 个，删除 {len(deleted)} 个。",
            OutputType.SUCCESS,
        )

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

        PrettyOutput.print(
            f"已将 {len(documents)} 个文档拆分为 {len(chunks)} 个块。",
            OutputType.INFO,
        )

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
        PrettyOutput.print(
            f"成功将 {len(chunks)} 个块添加到 ChromaDB 集合中。",
            OutputType.SUCCESS,
        )

        # 更新并保存BM25索引
        tokenized_chunks = [doc.split() for doc in chunk_texts]
        self.bm25_corpus.extend(tokenized_chunks)
        self.bm25_index = BM25Okapi(self.bm25_corpus)
        self._save_bm25_index()
        # 更新索引清单（用于检测源文件变更/删除）
        source_list = [
            md.get("source")
            for md in metadatas
            if md and isinstance(md.get("source"), str)
        ]
        self._update_manifest_with_sources(cast(List[str], source_list))

    def retrieve(
        self, query: str, n_results: int = 5, use_bm25: bool = True
    ) -> List[Document]:
        """
        使用向量搜索和BM25执行混合检索，然后使用倒数排序融合（RRF）
        对结果进行融合。
        """
        # 在检索前检查源文件变更/删除并提醒
        self._warn_if_sources_changed()
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
