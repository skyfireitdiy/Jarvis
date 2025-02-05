import os
import numpy as np
import faiss
from typing import List, Tuple, Optional, Dict
import pickle
from jarvis.utils import OutputType, PrettyOutput, get_file_md5, get_max_context_length, load_embedding_model, load_rerank_model
from jarvis.utils import load_env_from_file
from dataclasses import dataclass
from tqdm import tqdm
import fitz  # PyMuPDF for PDF files
from docx import Document as DocxDocument  # python-docx for DOCX files
from pathlib import Path
from jarvis.models.registry import PlatformRegistry
import shutil
from datetime import datetime
import lzma  # 添加 lzma 导入
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

@dataclass
class Document:
    """文档类，用于存储文档内容和元数据"""
    content: str  # 文档内容
    metadata: Dict  # 元数据(文件路径、位置等)
    md5: str = ""  # 文件MD5值，用于增量更新检测

class FileProcessor:
    """文件处理器基类"""
    @staticmethod
    def can_handle(file_path: str) -> bool:
        """判断是否可以处理该文件"""
        raise NotImplementedError
        
    @staticmethod
    def extract_text(file_path: str) -> str:
        """提取文件文本内容"""
        raise NotImplementedError

class TextFileProcessor(FileProcessor):
    """文本文件处理器"""
    ENCODINGS = ['utf-8', 'gbk', 'gb2312', 'latin1']
    SAMPLE_SIZE = 8192  # 读取前8KB来检测编码
    
    @staticmethod
    def can_handle(file_path: str) -> bool:
        """判断文件是否为文本文件，通过尝试解码来判断"""
        try:
            # 读取文件开头的一小部分来检测
            with open(file_path, 'rb') as f:
                sample = f.read(TextFileProcessor.SAMPLE_SIZE)
                
            # 检查是否包含空字节（通常表示二进制文件）
            if b'\x00' in sample:
                return False
                
            # 检查是否包含过多的非打印字符（通常表示二进制文件）
            non_printable = sum(1 for byte in sample if byte < 32 and byte not in (9, 10, 13))  # tab, newline, carriage return
            if non_printable / len(sample) > 0.3:  # 如果非打印字符超过30%，认为是二进制文件
                return False
                
            # 尝试用不同编码解码
            for encoding in TextFileProcessor.ENCODINGS:
                try:
                    sample.decode(encoding)
                    return True
                except UnicodeDecodeError:
                    continue
                    
            return False
            
        except Exception:
            return False
    
    @staticmethod
    def extract_text(file_path: str) -> str:
        """提取文本内容，使用检测到的正确编码"""
        detected_encoding = None
        try:
            # 首先尝试检测编码
            with open(file_path, 'rb') as f:
                raw_data = f.read()
                
            # 尝试不同的编码
            for encoding in TextFileProcessor.ENCODINGS:
                try:
                    raw_data.decode(encoding)
                    detected_encoding = encoding
                    break
                except UnicodeDecodeError:
                    continue
                    
            if not detected_encoding:
                raise UnicodeDecodeError(f"无法用支持的编码解码文件: {file_path}")
                
            # 使用检测到的编码读取文件
            with open(file_path, 'r', encoding=detected_encoding, errors='replace') as f:
                content = f.read()
                
            # 规范化Unicode字符
            import unicodedata
            content = unicodedata.normalize('NFKC', content)
            
            return content
            
        except Exception as e:
            raise Exception(f"读取文件失败: {str(e)}")

class PDFProcessor(FileProcessor):
    """PDF文件处理器"""
    @staticmethod
    def can_handle(file_path: str) -> bool:
        return Path(file_path).suffix.lower() == '.pdf'
    
    @staticmethod
    def extract_text(file_path: str) -> str:
        text_parts = []
        with fitz.open(file_path) as doc:
            for page in doc:
                text_parts.append(page.get_text())
        return "\n".join(text_parts)

class DocxProcessor(FileProcessor):
    """DOCX文件处理器"""
    @staticmethod
    def can_handle(file_path: str) -> bool:
        return Path(file_path).suffix.lower() == '.docx'
    
    @staticmethod
    def extract_text(file_path: str) -> str:
        doc = DocxDocument(file_path)
        return "\n".join([paragraph.text for paragraph in doc.paragraphs])

class RAGTool:
    def __init__(self, root_dir: str):
        """初始化RAG工具
        
        Args:
            root_dir: 项目根目录
        """
        load_env_from_file()
        self.root_dir = root_dir
        os.chdir(self.root_dir)
        
        # 初始化配置
        self.min_paragraph_length = int(os.environ.get("JARVIS_MIN_PARAGRAPH_LENGTH", "50"))  # 最小段落长度
        self.max_paragraph_length = int(os.environ.get("JARVIS_MAX_PARAGRAPH_LENGTH", "1000"))  # 最大段落长度
        self.context_window = int(os.environ.get("JARVIS_CONTEXT_WINDOW", "5"))  # 上下文窗口大小，默认前后各5个片段
        self.max_context_length = int(get_max_context_length() * 0.8)
        
        # 初始化数据目录
        self.data_dir = os.path.join(self.root_dir, ".jarvis-rag")
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            
        # 初始化嵌入模型
        try:
            self.embedding_model = load_embedding_model()
            self.vector_dim = self.embedding_model.get_sentence_embedding_dimension()
            PrettyOutput.print("模型加载完成", output_type=OutputType.SUCCESS)
        except Exception as e:
            PrettyOutput.print(f"加载模型失败: {str(e)}", output_type=OutputType.ERROR)
            raise

        # 初始化缓存和索引
        self.cache_path = os.path.join(self.data_dir, "cache.pkl")
        self.documents: List[Document] = []
        self.index = None  # 用于搜索的IVF索引
        self.flat_index = None  # 用于存储原始向量
        self.file_md5_cache = {}  # 用于存储文件的MD5值
        
        # 加载缓存
        self._load_cache()

        # 注册文件处理器
        self.file_processors = [
            TextFileProcessor(),
            PDFProcessor(),
            DocxProcessor()
        ]

        # 添加线程相关配置
        self.thread_count = int(os.environ.get("JARVIS_THREAD_COUNT", os.cpu_count() or 4))
        self.vector_lock = Lock()  # 用于保护向量列表的并发访问

    def _load_cache(self):
        """加载缓存数据"""
        if os.path.exists(self.cache_path):
            try:
                with lzma.open(self.cache_path, 'rb') as f:
                    cache_data = pickle.load(f)
                    self.documents = cache_data["documents"]
                    vectors = cache_data["vectors"]
                    self.file_md5_cache = cache_data.get("file_md5_cache", {})  # 加载MD5缓存
                    
                # 重建索引
                if vectors is not None:
                    self._build_index(vectors)
                PrettyOutput.print(f"加载了 {len(self.documents)} 个文档片段", 
                                output_type=OutputType.INFO)
            except Exception as e:
                PrettyOutput.print(f"加载缓存失败: {str(e)}", 
                                output_type=OutputType.WARNING)
                self.documents = []
                self.index = None
                self.flat_index = None
                self.file_md5_cache = {}

    def _save_cache(self, vectors: np.ndarray):
        """优化缓存保存"""
        try:
            cache_data = {
                "version": "1.0",
                "timestamp": datetime.now().isoformat(),
                "documents": self.documents,
                "vectors": vectors.copy() if vectors is not None else None,  # 创建数组的副本
                "file_md5_cache": dict(self.file_md5_cache),  # 创建字典的副本
                "metadata": {
                    "vector_dim": self.vector_dim,
                    "total_docs": len(self.documents),
                    "model_name": self.embedding_model.__class__.__name__
                }
            }
            
            # 先将数据序列化为字节流
            data = pickle.dumps(cache_data, protocol=pickle.HIGHEST_PROTOCOL)
            
            # 然后使用 LZMA 压缩字节流
            with lzma.open(self.cache_path, 'wb') as f:
                f.write(data)
            
            # 创建备份
            backup_path = f"{self.cache_path}.backup"
            shutil.copy2(self.cache_path, backup_path)
            
            PrettyOutput.print(f"缓存已保存: {len(self.documents)} 个文档片段", 
                            output_type=OutputType.INFO)
        except Exception as e:
            PrettyOutput.print(f"保存缓存失败: {str(e)}", 
                            output_type=OutputType.ERROR)
            raise

    def _build_index(self, vectors: np.ndarray):
        """构建FAISS索引"""
        if vectors.shape[0] == 0:
            self.index = None
            self.flat_index = None
            return
            
        # 创建扁平索引存储原始向量，用于重建
        self.flat_index = faiss.IndexFlatIP(self.vector_dim)
        self.flat_index.add(vectors)
        
        # 创建IVF索引用于快速搜索
        nlist = max(4, int(vectors.shape[0] / 1000))  # 每1000个向量一个聚类中心
        quantizer = faiss.IndexFlatIP(self.vector_dim)
        self.index = faiss.IndexIVFFlat(quantizer, self.vector_dim, nlist, faiss.METRIC_INNER_PRODUCT)
        
        # 训练并添加向量
        self.index.train(vectors)
        self.index.add(vectors)
        # 设置搜索时探测的聚类数
        self.index.nprobe = min(nlist, 10)

    def _split_text(self, text: str) -> List[str]:
        """使用更智能的分块策略"""
        # 添加重叠分块以保持上下文连贯性
        overlap_size = min(200, self.max_paragraph_length // 4)
        
        paragraphs = []
        current_chunk = []
        current_length = 0
        
        # 首先按句子分割
        sentences = []
        current_sentence = []
        sentence_ends = {'。', '！', '？', '…', '.', '!', '?'}
        
        for char in text:
            current_sentence.append(char)
            if char in sentence_ends:
                sentence = ''.join(current_sentence)
                if sentence.strip():
                    sentences.append(sentence)
                current_sentence = []
        
        if current_sentence:
            sentence = ''.join(current_sentence)
            if sentence.strip():
                sentences.append(sentence)
        
        # 基于句子构建重叠块
        for sentence in sentences:
            if current_length + len(sentence) > self.max_paragraph_length:
                if current_chunk:
                    chunk_text = ' '.join(current_chunk)
                    if len(chunk_text) >= self.min_paragraph_length:
                        paragraphs.append(chunk_text)
                        
                    # 保留部分内容作为重叠
                    overlap_text = ' '.join(current_chunk[-2:])  # 保留最后两句
                    current_chunk = []
                    if overlap_text:
                        current_chunk.append(overlap_text)
                        current_length = len(overlap_text)
                    else:
                        current_length = 0
                        
            current_chunk.append(sentence)
            current_length += len(sentence)
        
        # 处理最后一个chunk
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            if len(chunk_text) >= self.min_paragraph_length:
                paragraphs.append(chunk_text)
        
        return paragraphs

    def _get_embedding(self, text: str) -> np.ndarray:
        """获取文本的向量表示"""
        embedding = self.embedding_model.encode(text, 
                                            normalize_embeddings=True,
                                            show_progress_bar=False)
        return np.array(embedding, dtype=np.float32)

    def _get_embedding_batch(self, texts: List[str]) -> np.ndarray:
        """批量获取文本的向量表示
        
        Args:
            texts: 文本列表
            
        Returns:
            np.ndarray: 向量表示数组
        """
        try:
            embeddings = self.embedding_model.encode(texts, 
                                                normalize_embeddings=True,
                                                show_progress_bar=False,
                                                batch_size=32)  # 使用批处理提高效率
            return np.array(embeddings, dtype=np.float32)
        except Exception as e:
            PrettyOutput.print(f"获取向量表示失败: {str(e)}", 
                            output_type=OutputType.ERROR)
            return np.zeros((len(texts), self.vector_dim), dtype=np.float32)

    def _process_document_batch(self, documents: List[Document]) -> List[np.ndarray]:
        """处理一批文档的向量化
        
        Args:
            documents: 文档列表
            
        Returns:
            List[np.ndarray]: 向量列表
        """
        texts = []
        for doc in documents:
            # 组合文档信息
            combined_text = f"""
文件: {doc.metadata['file_path']}
内容: {doc.content}
"""
            texts.append(combined_text)
            
        return self._get_embedding_batch(texts)

    def _process_file(self, file_path: str) -> List[Document]:
        """处理单个文件"""
        try:
            # 计算文件MD5
            current_md5 = get_file_md5(file_path)
            if not current_md5:
                return []

            # 检查文件是否需要重新处理
            if file_path in self.file_md5_cache and self.file_md5_cache[file_path] == current_md5:
                return []

            # 查找合适的处理器
            processor = None
            for p in self.file_processors:
                if p.can_handle(file_path):
                    processor = p
                    break
                    
            if not processor:
                # 如果找不到合适的处理器，则返回一个空的文档
                return []
            
            # 提取文本内容
            content = processor.extract_text(file_path)
            if not content.strip():
                return []
            
            # 分割文本
            chunks = self._split_text(content)
            
            # 创建文档对象
            documents = []
            for i, chunk in enumerate(chunks):
                doc = Document(
                    content=chunk,
                    metadata={
                        "file_path": file_path,
                        "file_type": Path(file_path).suffix.lower(),
                        "chunk_index": i,
                        "total_chunks": len(chunks)
                    },
                    md5=current_md5
                )
                documents.append(doc)
            
            # 更新MD5缓存
            self.file_md5_cache[file_path] = current_md5
            return documents
            
        except Exception as e:
            PrettyOutput.print(f"处理文件失败 {file_path}: {str(e)}", 
                            output_type=OutputType.ERROR)
            return []

    def build_index(self, dir: str):
        """构建文档索引"""
        # 获取所有文件
        all_files = []
        for root, _, files in os.walk(dir):
            if any(ignored in root for ignored in ['.git', '__pycache__', 'node_modules']) or \
               any(part.startswith('.jarvis-') for part in root.split(os.sep)):
                continue
            for file in files:
                if file.startswith('.jarvis-'):
                    continue
                    
                file_path = os.path.join(root, file)
                if os.path.getsize(file_path) > 100 * 1024 * 1024:  # 100MB
                    PrettyOutput.print(f"跳过大文件: {file_path}", 
                                    output_type=OutputType.WARNING)
                    continue
                all_files.append(file_path)

        # 清理已删除文件的缓存
        deleted_files = set(self.file_md5_cache.keys()) - set(all_files)
        for file_path in deleted_files:
            del self.file_md5_cache[file_path]
            # 移除相关的文档
            self.documents = [doc for doc in self.documents if doc.metadata['file_path'] != file_path]

        # 检查文件变化
        files_to_process = []
        unchanged_files = []
        
        with tqdm(total=len(all_files), desc="检查文件状态") as pbar:
            for file_path in all_files:
                current_md5 = get_file_md5(file_path)
                if current_md5:  # 只处理能成功计算MD5的文件
                    if file_path in self.file_md5_cache and self.file_md5_cache[file_path] == current_md5:
                        # 文件未变化，记录但不重新处理
                        unchanged_files.append(file_path)
                    else:
                        # 新文件或已修改的文件
                        files_to_process.append(file_path)
                pbar.update(1)

        # 保留未变化文件的文档
        unchanged_documents = [doc for doc in self.documents 
                            if doc.metadata['file_path'] in unchanged_files]

        # 处理新文件和修改的文件
        new_documents = []
        if files_to_process:
            with tqdm(total=len(files_to_process), desc="处理文件") as pbar:
                for file_path in files_to_process:
                    try:
                        docs = self._process_file(file_path)
                        if len(docs) > 0:
                            new_documents.extend(docs)
                    except Exception as e:
                        PrettyOutput.print(f"处理文件失败 {file_path}: {str(e)}", 
                                        output_type=OutputType.ERROR)
                    pbar.update(1)

        # 更新文档列表
        self.documents = unchanged_documents + new_documents

        if not self.documents:
            PrettyOutput.print("没有需要处理的文档", output_type=OutputType.WARNING)
            return

        # 只对新文档进行向量化
        if new_documents:
            PrettyOutput.print(f"开始处理 {len(new_documents)} 个新文档", 
                            output_type=OutputType.INFO)
            
            # 使用线程池并发处理向量化
            batch_size = 32
            new_vectors = []
            
            with tqdm(total=len(new_documents), desc="生成向量") as pbar:
                with ThreadPoolExecutor(max_workers=self.thread_count) as executor:
                    for i in range(0, len(new_documents), batch_size):
                        batch = new_documents[i:i + batch_size]
                        future = executor.submit(self._process_document_batch, batch)
                        batch_vectors = future.result()
                        
                        with self.vector_lock:
                            new_vectors.extend(batch_vectors)
                        
                        pbar.update(len(batch))

            # 合并新旧向量
            if self.flat_index is not None:
                # 获取未变化文档的向量
                unchanged_vectors = []
                for doc in unchanged_documents:
                    # 从现有索引中提取向量
                    doc_idx = next((i for i, d in enumerate(self.documents) 
                                if d.metadata['file_path'] == doc.metadata['file_path']), None)
                    if doc_idx is not None:
                        # 从扁平索引中重建向量
                        vector = np.zeros((1, self.vector_dim), dtype=np.float32)
                        self.flat_index.reconstruct(doc_idx, vector.ravel())
                        unchanged_vectors.append(vector)
                
                if unchanged_vectors:
                    unchanged_vectors = np.vstack(unchanged_vectors)
                    vectors = np.vstack([unchanged_vectors, np.vstack(new_vectors)])
                else:
                    vectors = np.vstack(new_vectors)
            else:
                vectors = np.vstack(new_vectors)

            # 构建索引
            self._build_index(vectors)
            # 保存缓存
            self._save_cache(vectors)
        
        PrettyOutput.print(f"成功索引了 {len(self.documents)} 个文档片段 (新增/修改: {len(new_documents)}, 未变化: {len(unchanged_documents)})", 
                        output_type=OutputType.SUCCESS)

    def search(self, query: str, top_k: int = 30) -> List[Tuple[Document, float]]:
        """优化搜索策略"""
        if not self.index:
            PrettyOutput.print("索引未构建，正在构建...", output_type=OutputType.INFO)
            self.build_index(self.root_dir)
        
        # 实现MMR (Maximal Marginal Relevance) 来增加结果多样性
        def mmr(query_vec, doc_vecs, doc_ids, lambda_param=0.5, n_docs=top_k):
            selected = []
            selected_ids = []
            
            while len(selected) < n_docs and len(doc_ids) > 0:
                best_score = -1
                best_idx = -1
                
                for i, (doc_vec, doc_id) in enumerate(zip(doc_vecs, doc_ids)):
                    # 计算与查询的相似度
                    query_sim = float(np.dot(query_vec, doc_vec))
                    
                    # 计算与已选文档的最大相似度
                    if selected:
                        doc_sims = [float(np.dot(doc_vec, selected_doc)) for selected_doc in selected]
                        max_doc_sim = max(doc_sims)
                    else:
                        max_doc_sim = 0
                    
                    # MMR score
                    score = lambda_param * query_sim - (1 - lambda_param) * max_doc_sim
                    
                    if score > best_score:
                        best_score = score
                        best_idx = i
                
                if best_idx == -1:
                    break
                
                selected.append(doc_vecs[best_idx])
                selected_ids.append(doc_ids[best_idx])
                doc_vecs = np.delete(doc_vecs, best_idx, axis=0)
                doc_ids = np.delete(doc_ids, best_idx)
            
            return selected_ids
        
        # 获取查询向量
        query_vector = self._get_embedding(query)
        query_vector = query_vector.reshape(1, -1)
        
        # 初始搜索更多结果用于MMR
        initial_k = min(top_k * 2, len(self.documents))
        distances, indices = self.index.search(query_vector, initial_k)
        
        # 获取有效结果
        valid_indices = indices[0][indices[0] != -1]
        valid_vectors = np.vstack([self._get_embedding(self.documents[idx].content) for idx in valid_indices])
        
        # 应用MMR
        final_indices = mmr(query_vector[0], valid_vectors, valid_indices, n_docs=top_k)
        
        # 构建结果
        results = []
        for idx in final_indices:
            doc = self.documents[idx]
            similarity = 1.0 / (1.0 + float(distances[0][np.where(indices[0] == idx)[0][0]]))
            results.append((doc, similarity))
        
        return results

    def _rerank_results(self, query: str, initial_results: List[Tuple[Document, float]]) -> List[Tuple[Document, float]]:
        """使用 rerank 模型重新排序搜索结果"""
        try:
            import torch
            model, tokenizer = load_rerank_model()
            
            # 准备数据
            pairs = []
            for doc, _ in initial_results:
                # 组合文档信息
                doc_content = f"""
文件: {doc.metadata['file_path']}
内容: {doc.content}
"""
                pairs.append([query, doc_content])
                
            # 对每个文档对进行打分
            scores = []
            batch_size = 8
            
            with torch.no_grad():
                for i in range(0, len(pairs), batch_size):
                    batch_pairs = pairs[i:i + batch_size]
                    encoded = tokenizer(
                        batch_pairs,
                        padding=True,
                        truncation=True,
                        max_length=512,
                        return_tensors='pt'
                    )
                    
                    if torch.cuda.is_available():
                        encoded = {k: v.cuda() for k, v in encoded.items()}
                        
                    outputs = model(**encoded)
                    batch_scores = outputs.logits.squeeze(-1).cpu().numpy()
                    scores.extend(batch_scores.tolist())
            
            # 归一化分数到 0-1 范围
            if scores:
                min_score = min(scores)
                max_score = max(scores)
                if max_score > min_score:
                    scores = [(s - min_score) / (max_score - min_score) for s in scores]
            
            # 将分数与文档组合并排序
            scored_results = []
            for (doc, _), score in zip(initial_results, scores):
                if score >= 0.5:  # 只保留关联度大于 0.5 的结果
                    scored_results.append((doc, float(score)))
                    
            # 按分数降序排序
            scored_results.sort(key=lambda x: x[1], reverse=True)
            
            return scored_results
            
        except Exception as e:
            PrettyOutput.print(f"重排序失败，使用原始排序: {str(e)}", output_type=OutputType.WARNING)
            return initial_results

    def is_index_built(self):
        """检查索引是否已构建"""
        return self.index is not None

    def query(self, query: str) -> List[Document]:
        """查询相关文档
        
        Args:
            query: 查询文本
            
        Returns:
            相关文档列表，包含上下文
        """
        results = self.search(query)
        return [doc for doc, _ in results]

    def ask(self, question: str) -> Optional[str]:
        """询问关于文档的问题
        
        Args:
            question: 用户问题
            
        Returns:
            模型回答，如果失败则返回 None
        """
        try:
            # 搜索相关文档片段
            results = self.query(question)
            if not results:
                return None
            
            # 显示找到的文档片段
            for doc in results:
                PrettyOutput.print(f"文件: {doc.metadata['file_path']}", output_type=OutputType.INFO)
                PrettyOutput.print(f"片段 {doc.metadata['chunk_index'] + 1}/{doc.metadata['total_chunks']}", 
                                output_type=OutputType.INFO)
                PrettyOutput.print("\n内容:", output_type=OutputType.INFO)
                content = doc.content.encode('utf-8', errors='replace').decode('utf-8')
                PrettyOutput.print(content, output_type=OutputType.INFO)

            # 构建基础提示词
            base_prompt = f"""请基于以下文档片段回答用户的问题。如果文档内容不足以完整回答问题，请明确指出。

用户问题: {question}

相关文档片段:
"""
            end_prompt = "\n请提供准确、简洁的回答，如果文档内容不足以完整回答问题，请明确指出。"
            
            # 计算可用于文档内容的最大长度
            # 预留一些空间给模型回答
            available_length = self.max_context_length - len(base_prompt) - len(end_prompt) - 500
            
            # 构建上下文，同时控制总长度
            context = []
            current_length = 0
            
            for doc in results:
                # 计算这个文档片段的内容长度
                doc_content = f"""
来源文件: {doc.metadata['file_path']}
内容:
{doc.content}
---
"""
                content_length = len(doc_content)
                
                # 如果添加这个片段会超出限制，就停止添加
                if current_length + content_length > available_length:
                    PrettyOutput.print("由于上下文长度限制，部分相关文档片段被省略", 
                                    output_type=OutputType.WARNING)
                    break
                    
                context.append(doc_content)
                current_length += content_length

            # 构建完整的提示词
            prompt = base_prompt + ''.join(context) + end_prompt
            
            # 获取模型实例并生成回答
            model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
            response = model.chat(prompt)
            
            return response
            
        except Exception as e:
            PrettyOutput.print(f"问答失败: {str(e)}", output_type=OutputType.ERROR)
            return None

def main():
    """主函数"""
    import argparse
    import sys
    
    # 设置标准输出编码为UTF-8
    if sys.stdout.encoding != 'utf-8':
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    
    parser = argparse.ArgumentParser(description='文档检索和分析工具')
    parser.add_argument('--dir', type=str, help='要处理的文档目录')
    parser.add_argument('--build', action='store_true', help='构建文档索引')
    parser.add_argument('--search', type=str, help='搜索文档内容')
    parser.add_argument('--ask', type=str, help='询问关于文档的问题')
    args = parser.parse_args()

    try:
        current_dir = os.getcwd()
        rag = RAGTool(current_dir)

        if not args.dir:
            args.dir = current_dir

        if args.dir and args.build:
            PrettyOutput.print(f"正在处理目录: {args.dir}", output_type=OutputType.INFO)
            rag.build_index(args.dir)
            return 0

        if args.search or args.ask:

            if args.search:
                results = rag.query(args.search)
                if not results:
                    PrettyOutput.print("未找到相关内容", output_type=OutputType.WARNING)
                    return 1
                    
                for doc in results:
                    PrettyOutput.print(f"\n文件: {doc.metadata['file_path']}", output_type=OutputType.INFO)
                    PrettyOutput.print(f"片段 {doc.metadata['chunk_index'] + 1}/{doc.metadata['total_chunks']}", 
                                    output_type=OutputType.INFO)
                    PrettyOutput.print("\n内容:", output_type=OutputType.INFO)
                    content = doc.content.encode('utf-8', errors='replace').decode('utf-8')
                    PrettyOutput.print(content, output_type=OutputType.INFO)
                return 0

            if args.ask:
                # 调用 ask 方法
                response = rag.ask(args.ask)
                if not response:
                    PrettyOutput.print("未能获取答案", output_type=OutputType.WARNING)
                    return 1
                    
                # 显示回答
                PrettyOutput.print("\n回答:", output_type=OutputType.INFO)
                PrettyOutput.print(response, output_type=OutputType.INFO)
                return 0

        PrettyOutput.print("请指定操作参数。使用 -h 查看帮助。", output_type=OutputType.WARNING)
        return 1

    except Exception as e:
        PrettyOutput.print(f"执行失败: {str(e)}", output_type=OutputType.ERROR)
        return 1

if __name__ == "__main__":
    main()
