import os
import numpy as np
import faiss
from typing import List, Tuple, Optional, Dict
import pickle
from jarvis.utils import OutputType, PrettyOutput, get_context_window, get_file_md5, get_max_context_length, get_max_paragraph_length, get_min_paragraph_length, get_thread_count, load_embedding_model, load_rerank_model
from jarvis.utils import init_env
from dataclasses import dataclass
from tqdm import tqdm
import fitz  # PyMuPDF for PDF files
from docx import Document as DocxDocument  # python-docx for DOCX files
from pathlib import Path
from jarvis.jarvis_platform.registry import PlatformRegistry
import shutil
from datetime import datetime
import lzma  # 添加 lzma 导入
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import concurrent.futures
import re
import hashlib

@dataclass
class Document:
    """Document class, for storing document content and metadata"""
    content: str  # Document content
    metadata: Dict  # Metadata (file path, position, etc.)
    md5: str = ""  # File MD5 value, for incremental update detection

class FileProcessor:
    """Base class for file processor"""
    @staticmethod
    def can_handle(file_path: str) -> bool:
        """Determine if the file can be processed"""
        raise NotImplementedError
        
    @staticmethod
    def extract_text(file_path: str) -> str:
        """Extract file text content"""
        raise NotImplementedError

class TextFileProcessor(FileProcessor):
    """Text file processor"""
    ENCODINGS = ['utf-8', 'gbk', 'gb2312', 'latin1']
    SAMPLE_SIZE = 8192  # Read the first 8KB to detect encoding
    
    @staticmethod
    def can_handle(file_path: str) -> bool:
        """Determine if the file is a text file by trying to decode it"""
        try:
            # Read the first part of the file to detect encoding
            with open(file_path, 'rb') as f:
                sample = f.read(TextFileProcessor.SAMPLE_SIZE)
                
            # Check if it contains null bytes (usually represents a binary file)
            if b'\x00' in sample:
                return False
                
            # Check if it contains too many non-printable characters (usually represents a binary file)
            non_printable = sum(1 for byte in sample if byte < 32 and byte not in (9, 10, 13))  # tab, newline, carriage return
            if non_printable / len(sample) > 0.3:  # If non-printable characters exceed 30%, it is considered a binary file
                return False
                
            # Try to decode with different encodings
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
        """Extract text content, using the detected correct encoding"""
        detected_encoding = None
        try:
            # First try to detect encoding
            with open(file_path, 'rb') as f:
                raw_data = f.read()
                
            # Try different encodings
            for encoding in TextFileProcessor.ENCODINGS:
                try:
                    raw_data.decode(encoding)
                    detected_encoding = encoding
                    break
                except UnicodeDecodeError:
                    continue
                    
            if not detected_encoding:
                raise UnicodeDecodeError(f"Failed to decode file with supported encodings: {file_path}") # type: ignore
                
            # Use the detected encoding to read the file
            with open(file_path, 'r', encoding=detected_encoding, errors='replace') as f:
                content = f.read()
                
            # Normalize Unicode characters
            import unicodedata
            content = unicodedata.normalize('NFKC', content)
            
            return content
            
        except Exception as e:
            raise Exception(f"Failed to read file: {str(e)}")

class PDFProcessor(FileProcessor):
    """PDF file processor"""
    @staticmethod
    def can_handle(file_path: str) -> bool:
        return Path(file_path).suffix.lower() == '.pdf'
    
    @staticmethod
    def extract_text(file_path: str) -> str:
        text_parts = []
        with fitz.open(file_path) as doc: # type: ignore
            for page in doc:
                text_parts.append(page.get_text()) # type: ignore
        return "\n".join(text_parts)

class DocxProcessor(FileProcessor):
    """DOCX file processor"""
    @staticmethod
    def can_handle(file_path: str) -> bool:
        return Path(file_path).suffix.lower() == '.docx'
    
    @staticmethod
    def extract_text(file_path: str) -> str:
        doc = DocxDocument(file_path)
        return "\n".join([paragraph.text for paragraph in doc.paragraphs])

class RAGTool:
    def __init__(self, root_dir: str):
        """Initialize RAG tool
        
        Args:
            root_dir: Project root directory
        """
        init_env()
        self.root_dir = root_dir
        os.chdir(self.root_dir)
        
        # Initialize configuration
        self.min_paragraph_length = get_min_paragraph_length()  # Minimum paragraph length
        self.max_paragraph_length = get_max_paragraph_length()  # Maximum paragraph length
        self.context_window = get_context_window()  # Context window size, default前后各5个片段
        self.max_context_length = int(get_max_context_length() * 0.8)
        
        # Initialize data directory
        self.data_dir = os.path.join(self.root_dir, ".jarvis/rag")
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            
        # Initialize embedding model
        try:
            self.embedding_model = load_embedding_model()
            self.vector_dim = self.embedding_model.get_sentence_embedding_dimension()
            PrettyOutput.print("Model loaded", output_type=OutputType.SUCCESS)
        except Exception as e:
            PrettyOutput.print(f"Failed to load model: {str(e)}", output_type=OutputType.ERROR)
            raise

        # 修改缓存相关初始化
        self.cache_dir = os.path.join(self.data_dir, "cache")
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
            
        self.documents: List[Document] = []
        self.index = None
        self.flat_index = None
        self.file_md5_cache = {}
        
        # 加载缓存索引
        self._load_cache_index()

        # Register file processors
        self.file_processors = [
            TextFileProcessor(),
            PDFProcessor(),
            DocxProcessor()
        ]

        # Add thread related configuration
        self.thread_count = get_thread_count()
        self.vector_lock = Lock()  # Protect vector list concurrency

        # 初始化 GPU 内存配置
        self.gpu_config = self._init_gpu_config()

    def _init_gpu_config(self) -> Dict:
        """Initialize GPU configuration based on available hardware
        
        Returns:
            Dict: GPU configuration including memory sizes and availability
        """
        config = {
            "has_gpu": False,
            "shared_memory": 0,
            "device_memory": 0,
            "memory_fraction": 0.8  # 默认使用80%的可用内存
        }
        
        try:
            import torch
            if torch.cuda.is_available():
                # 获取GPU信息
                gpu_mem = torch.cuda.get_device_properties(0).total_memory
                config["has_gpu"] = True
                config["device_memory"] = gpu_mem
                
                # 估算共享内存 (通常是系统内存的一部分)
                import psutil
                system_memory = psutil.virtual_memory().total
                config["shared_memory"] = min(system_memory * 0.5, gpu_mem * 2)  # 取系统内存的50%或GPU内存的2倍中的较小值
                
                # 设置CUDA内存分配
                torch.cuda.set_per_process_memory_fraction(config["memory_fraction"])
                torch.cuda.empty_cache()
                
                PrettyOutput.print(
                    f"GPU initialized: {torch.cuda.get_device_name(0)}\n"
                    f"Device Memory: {gpu_mem / 1024**3:.1f}GB\n"
                    f"Shared Memory: {config['shared_memory'] / 1024**3:.1f}GB", 
                    output_type=OutputType.SUCCESS
                )
            else:
                PrettyOutput.print("No GPU available, using CPU mode", output_type=OutputType.WARNING)
        except Exception as e:
            PrettyOutput.print(f"GPU initialization failed: {str(e)}", output_type=OutputType.WARNING)
            
        return config

    def _get_cache_path(self, file_path: str) -> str:
        """Get cache file path for a document
        
        Args:
            file_path: Original file path
            
        Returns:
            str: Cache file path
        """
        # 使用文件路径的哈希作为缓存文件名
        file_hash = hashlib.md5(file_path.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{file_hash}.cache")

    def _load_cache_index(self):
        """Load cache index"""
        index_path = os.path.join(self.data_dir, "index.pkl")
        if os.path.exists(index_path):
            try:
                with lzma.open(index_path, 'rb') as f:
                    cache_data = pickle.load(f)
                    self.file_md5_cache = cache_data.get("file_md5_cache", {})
                    
                # 从各个缓存文件加载文档
                for file_path in self.file_md5_cache:
                    cache_path = self._get_cache_path(file_path)
                    if os.path.exists(cache_path):
                        try:
                            with lzma.open(cache_path, 'rb') as f:
                                file_cache = pickle.load(f)
                                self.documents.extend(file_cache["documents"])
                        except Exception as e:
                            PrettyOutput.print(f"Failed to load cache for {file_path}: {str(e)}", 
                                            output_type=OutputType.WARNING)
                
                # 重建向量索引
                if self.documents:
                    vectors = []
                    for doc in self.documents:
                        cache_path = self._get_cache_path(doc.metadata['file_path'])
                        if os.path.exists(cache_path):
                            with lzma.open(cache_path, 'rb') as f:
                                file_cache = pickle.load(f)
                                doc_idx = next((i for i, d in enumerate(file_cache["documents"]) 
                                            if d.metadata['chunk_index'] == doc.metadata['chunk_index']), None)
                                if doc_idx is not None:
                                    vectors.append(file_cache["vectors"][doc_idx])
                    
                    if vectors:
                        vectors = np.vstack(vectors)
                        self._build_index(vectors)
                        
                PrettyOutput.print(f"Loaded {len(self.documents)} document fragments", 
                                output_type=OutputType.INFO)
                                
            except Exception as e:
                PrettyOutput.print(f"Failed to load cache index: {str(e)}", 
                                output_type=OutputType.WARNING)
                self.documents = []
                self.index = None
                self.flat_index = None
                self.file_md5_cache = {}

    def _save_cache(self, file_path: str, documents: List[Document], vectors: np.ndarray):
        """Save cache for a single file
        
        Args:
            file_path: File path
            documents: List of documents
            vectors: Document vectors
        """
        try:
            # 保存文件缓存
            cache_path = self._get_cache_path(file_path)
            cache_data = {
                "documents": documents,
                "vectors": vectors
            }
            with lzma.open(cache_path, 'wb') as f:
                pickle.dump(cache_data, f)
                
            # 更新并保存索引
            index_path = os.path.join(self.data_dir, "index.pkl")
            index_data = {
                "file_md5_cache": self.file_md5_cache
            }
            with lzma.open(index_path, 'wb') as f:
                pickle.dump(index_data, f)
                
            PrettyOutput.print(f"Cache saved: {len(documents)} document fragments", 
                            output_type=OutputType.INFO)
                            
        except Exception as e:
            PrettyOutput.print(f"Failed to save cache: {str(e)}", output_type=OutputType.ERROR)

    def _build_index(self, vectors: np.ndarray):
        """Build FAISS index"""
        if vectors.shape[0] == 0:
            self.index = None
            self.flat_index = None
            return
            
        # Create a flat index to store original vectors, for reconstruction
        self.flat_index = faiss.IndexFlatIP(self.vector_dim)
        self.flat_index.add(vectors) # type: ignore
        
        # Create an IVF index for fast search
        nlist = max(4, int(vectors.shape[0] / 1000))  # 每1000个向量一个聚类中心
        quantizer = faiss.IndexFlatIP(self.vector_dim)
        self.index = faiss.IndexIVFFlat(quantizer, self.vector_dim, nlist, faiss.METRIC_INNER_PRODUCT)
        
        # Train and add vectors
        self.index.train(vectors) # type: ignore
        self.index.add(vectors) # type: ignore
        # Set the number of clusters to probe during search
        self.index.nprobe = min(nlist, 10)

    def _split_text(self, text: str) -> List[str]:
        """Use a more intelligent splitting strategy"""
        # Add overlapping blocks to maintain context consistency
        overlap_size = min(200, self.max_paragraph_length // 4)
        
        paragraphs = []
        current_chunk = []
        current_length = 0
        
        # First split by sentence
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
        
        # Build overlapping blocks based on sentences
        for sentence in sentences:
            if current_length + len(sentence) > self.max_paragraph_length:
                if current_chunk:
                    chunk_text = ' '.join(current_chunk)
                    if len(chunk_text) >= self.min_paragraph_length:
                        paragraphs.append(chunk_text)
                        
                    # Keep some content as overlap
                    overlap_text = ' '.join(current_chunk[-2:])  # Keep the last two sentences
                    current_chunk = []
                    if overlap_text:
                        current_chunk.append(overlap_text)
                        current_length = len(overlap_text)
                    else:
                        current_length = 0
                        
            current_chunk.append(sentence)
            current_length += len(sentence)
        
        # Process the last chunk
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            if len(chunk_text) >= self.min_paragraph_length:
                paragraphs.append(chunk_text)
        
        return paragraphs

    def _get_embedding(self, text: str) -> np.ndarray:
        """Get the vector representation of the text"""
        embedding = self.embedding_model.encode(text, 
                                            normalize_embeddings=True,
                                            show_progress_bar=False)
        return np.array(embedding, dtype=np.float32)

    def _get_embedding_batch(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """Get embeddings for a batch of texts efficiently"""
        try:
            if self.gpu_config["has_gpu"]:
                import torch
                torch.cuda.empty_cache()
                
                # 使用更保守的批处理大小
                optimal_batch_size = min(8, len(texts))
                all_embeddings = []
                
                with tqdm(total=len(texts), desc="Vectorizing") as pbar:
                    for i in range(0, len(texts), optimal_batch_size):
                        try:
                            batch = texts[i:i + optimal_batch_size]
                            
                            # 临时将模型移到 CPU 以清理 GPU 内存
                            self.embedding_model.to('cpu')
                            torch.cuda.empty_cache()
                            
                            # 分批处理文本
                            embeddings = self.embedding_model.encode(
                                batch,
                                normalize_embeddings=True,
                                show_progress_bar=False,
                                batch_size=2,  # 使用更小的内部批处理大小
                                convert_to_tensor=False  # 直接返回 numpy 数组
                            )
                            
                            all_embeddings.append(embeddings)
                            pbar.update(len(batch))
                            
                        except RuntimeError as e:
                            if "out of memory" in str(e):
                                # 如果内存不足，减小批次大小
                                if optimal_batch_size > 2:
                                    optimal_batch_size //= 2
                                    PrettyOutput.print(
                                        f"CUDA out of memory, reducing batch size to {optimal_batch_size}", 
                                        OutputType.WARNING
                                    )
                                    # 清理内存并重试
                                    torch.cuda.empty_cache()
                                    self.embedding_model.to('cpu')
                                    i -= optimal_batch_size
                                    continue
                                else:
                                    # 如果批次已经最小，切换到 CPU 模式
                                    PrettyOutput.print(
                                        "Switching to CPU mode due to memory constraints",
                                        OutputType.WARNING
                                    )
                                    self.embedding_model.to('cpu')
                                    return self._get_embedding_batch_cpu(texts[i:])
                            raise
                            
                return np.vstack(all_embeddings)
            else:
                return self._get_embedding_batch_cpu(texts)
                
        except Exception as e:
            PrettyOutput.print(f"Batch embedding failed: {str(e)}", OutputType.ERROR)
            return np.zeros((len(texts), self.vector_dim), dtype=np.float32) # type: ignore

    def _get_embedding_batch_cpu(self, texts: List[str]) -> np.ndarray:
        """Get embeddings using CPU only"""
        return self.embedding_model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=True,
            batch_size=4,
            convert_to_tensor=False
        )

    def _process_document_batch(self, documents: List[Document]) -> np.ndarray:
        """Process a batch of documents using shared memory
        
        Args:
            documents: List of documents to process
            
        Returns:
            np.ndarray: Document vectors
        """
        try:
            import torch
            
            # 估算内存需求
            total_content_size = sum(len(doc.content) for doc in documents)
            est_memory_needed = total_content_size * 4  # 粗略估计
            
            # 如果预估内存超过共享内存限制，分批处理
            if est_memory_needed > self.gpu_config["shared_memory"] * 0.7:
                batch_size = max(1, int(len(documents) * (self.gpu_config["shared_memory"] * 0.7 / est_memory_needed)))
                
                all_vectors = []
                for i in range(0, len(documents), batch_size):
                    batch = documents[i:i + batch_size]
                    vectors = self._process_document_batch(batch)
                    all_vectors.append(vectors)
                return np.vstack(all_vectors)
            
            # 正常处理单个批次
            texts = []
            for doc in documents:
                combined_text = f"File:{doc.metadata['file_path']} Content:{doc.content}"
                texts.append(combined_text)
                
            return self._get_embedding_batch(texts)
            
        except Exception as e:
            PrettyOutput.print(f"Batch processing failed: {str(e)}", OutputType.ERROR)
            return np.zeros((0, self.vector_dim), dtype=np.float32) # type: ignore

    def _process_file(self, file_path: str) -> List[Document]:
        """Process a single file"""
        try:
            # Calculate file MD5
            current_md5 = get_file_md5(file_path)
            if not current_md5:
                return []

            # Check if the file needs to be reprocessed
            if file_path in self.file_md5_cache and self.file_md5_cache[file_path] == current_md5:
                return []

            # Find the appropriate processor
            processor = None
            for p in self.file_processors:
                if p.can_handle(file_path):
                    processor = p
                    break
                    
            if not processor:
                # If no appropriate processor is found, return an empty document
                return []
            
            # Extract text content
            content = processor.extract_text(file_path)
            if not content.strip():
                return []
            
            # Split text
            chunks = self._split_text(content)
            
            # Create document objects
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
            
            # Update MD5 cache
            self.file_md5_cache[file_path] = current_md5
            return documents
            
        except Exception as e:
            PrettyOutput.print(f"Failed to process file {file_path}: {str(e)}", 
                            output_type=OutputType.ERROR)
            return []

    def build_index(self, dir: str):
        """Build document index with optimized processing"""
        # Get all files
        all_files = []
        for root, _, files in os.walk(dir):
            # Skip .jarvis directories and other ignored paths
            if any(ignored in root for ignored in ['.git', '__pycache__', 'node_modules', '.jarvis']) or \
               any(part.startswith('.jarvis-') for part in root.split(os.sep)):
                continue
                
            for file in files:
                # Skip .jarvis files
                if '.jarvis' in root:
                    continue
                    
                file_path = os.path.join(root, file)
                if os.path.getsize(file_path) > 100 * 1024 * 1024:  # 100MB
                    PrettyOutput.print(f"Skip large file: {file_path}", 
                                    output_type=OutputType.WARNING)
                    continue
                all_files.append(file_path)

        # Clean up cache for deleted files
        deleted_files = set(self.file_md5_cache.keys()) - set(all_files)
        for file_path in deleted_files:
            del self.file_md5_cache[file_path]
            # Remove related documents
            self.documents = [doc for doc in self.documents if doc.metadata['file_path'] != file_path]

        # Check file changes
        files_to_process = []
        unchanged_files = []
        
        with tqdm(total=len(all_files), desc="Check file status") as pbar:
            for file_path in all_files:
                current_md5 = get_file_md5(file_path)
                if current_md5:  # Only process files that can successfully calculate MD5
                    if file_path in self.file_md5_cache and self.file_md5_cache[file_path] == current_md5:
                        # File未变化，记录但不重新处理
                        unchanged_files.append(file_path)
                    else:
                        # New file or modified file
                        files_to_process.append(file_path)
                pbar.update(1)

        # Keep documents for unchanged files
        unchanged_documents = [doc for doc in self.documents 
                            if doc.metadata['file_path'] in unchanged_files]

        # Process files in parallel with optimized vectorization
        if files_to_process:
            PrettyOutput.print(f"Processing {len(files_to_process)} files...", OutputType.INFO)
            
            # Step 1: 并行提取文本内容
            documents_to_process = []
            with ThreadPoolExecutor(max_workers=self.thread_count) as executor:
                futures = {
                    executor.submit(self._process_file, file_path): file_path 
                    for file_path in files_to_process
                }
                
                with tqdm(total=len(files_to_process), desc="Extracting text") as pbar:
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            docs = future.result()
                            if docs:
                                documents_to_process.extend(docs)
                            pbar.update(1)
                        except Exception as e:
                            PrettyOutput.print(f"File processing failed: {str(e)}", OutputType.ERROR)
                            pbar.update(1)

            # Step 2: 优化的批量向量化
            if documents_to_process:
                PrettyOutput.print(f"Vectorizing {len(documents_to_process)} documents...", OutputType.INFO)
                
                # 准备向量化的文本
                texts_to_vectorize = []
                for doc in documents_to_process:
                    # 优化文本组合，减少内存使用
                    combined_text = f"File:{doc.metadata['file_path']} Content:{doc.content}"
                    texts_to_vectorize.append(combined_text)

                # 使用较小的初始批处理大小
                initial_batch_size = min(
                    32,  # 最大批次大小
                    max(4, len(texts_to_vectorize) // 8),  # 基于文档数的批次大小
                    len(texts_to_vectorize)  # 不超过总文档数
                )
                
                # 批量处理向量
                vectors = self._get_embedding_batch(texts_to_vectorize, initial_batch_size)

                # 更新文档和索引
                self.documents.extend(documents_to_process)

                # 构建最终索引
                if self.flat_index is not None:
                    # 获取未更改文档的向量
                    unchanged_vectors = self._get_unchanged_vectors(unchanged_documents)
                    if unchanged_vectors is not None:
                        final_vectors = np.vstack([unchanged_vectors, vectors])
                    else:
                        final_vectors = vectors
                else:
                    final_vectors = vectors

                # 构建索引并保存缓存
                self._build_index(final_vectors)
                
                # 按文件分别保存缓存
                for file_path in files_to_process:
                    file_docs = [doc for doc in documents_to_process if doc.metadata['file_path'] == file_path]
                    if file_docs:
                        doc_vectors = vectors[len(self.documents)-len(documents_to_process):][
                            [i for i, doc in enumerate(documents_to_process) if doc.metadata['file_path'] == file_path]
                        ]
                        self._save_cache(file_path, file_docs, doc_vectors)

                PrettyOutput.print(
                    f"Indexed {len(self.documents)} documents "
                    f"(New/Modified: {len(documents_to_process)}, "
                    f"Unchanged: {len(unchanged_documents)})", 
                    OutputType.SUCCESS
                )

    def _get_unchanged_vectors(self, unchanged_documents: List[Document]) -> Optional[np.ndarray]:
        """Get vectors for unchanged documents from existing index"""
        try:
            if not unchanged_documents or self.flat_index is None:
                return None

            unchanged_vectors = []
            for doc in unchanged_documents:
                doc_idx = next((i for i, d in enumerate(self.documents) 
                            if d.metadata['file_path'] == doc.metadata['file_path']), None)
                if doc_idx is not None:
                    vector = np.zeros((1, self.vector_dim), dtype=np.float32) # type: ignore
                    self.flat_index.reconstruct(doc_idx, vector.ravel())
                    unchanged_vectors.append(vector)

            return np.vstack(unchanged_vectors) if unchanged_vectors else None
            
        except Exception as e:
            PrettyOutput.print(f"Failed to get unchanged vectors: {str(e)}", OutputType.ERROR)
            return None

    def search(self, query: str, top_k: int = 30) -> List[Tuple[Document, float]]:
        """Search documents using vector similarity
        
        Args:
            query: Search query
            top_k: Number of results to return
        """
        if not self.index:
            PrettyOutput.print("Index not built, building...", output_type=OutputType.INFO)
            self.build_index(self.root_dir)
            
        # Get query vector
        query_vector = self._get_embedding(query)
        query_vector = query_vector.reshape(1, -1)
        
        # Search with more candidates
        initial_k = min(top_k * 4, len(self.documents))
        distances, indices = self.index.search(query_vector, initial_k) # type: ignore
        
        # Process results
        results = []
        seen_files = set()
        for idx, dist in zip(indices[0], distances[0]):
            if idx != -1:
                doc = self.documents[idx]
                similarity = 1.0 / (1.0 + float(dist))
                if similarity > 0.3:  # 降低过滤阈值以获取更多结果
                    file_path = doc.metadata['file_path']
                    if file_path not in seen_files:
                        seen_files.add(file_path)
                        results.append((doc, similarity))
                        if len(results) >= top_k:
                            break
        
        return results

    def query(self, query: str) -> List[Document]:
        """Query related documents
        
        Args:
            query: Query text
            
        Returns:
            List[Document]: Related documents
        """
        results = self.search(query)
        return [doc for doc, _ in results]

    def ask(self, question: str) -> Optional[str]:
        """Ask questions about documents with enhanced context building"""
        try:
            # 搜索相关文档
            results = self.search(question)
            if not results:
                return None
            
            # 显示找到的文档
            for doc, score in results:
                output = f"""File: {doc.metadata['file_path']} (Score: {score:.3f})\n"""
                output += f"""Fragment {doc.metadata['chunk_index'] + 1}/{doc.metadata['total_chunks']}\n"""
                output += f"""Content:\n{doc.content}\n"""
                PrettyOutput.print(output, output_type=OutputType.INFO, lang="markdown")
            
            # 构建提示词
            prompt = f"""Based on the following document fragments, please answer the user's question accurately and comprehensively.

Question: {question}

Relevant documents (ordered by relevance):
"""
            # 添加上下文，控制长度
            available_length = self.max_context_length - len(prompt) - 1000
            current_length = 0
            
            for doc, score in results:
                doc_content = f"""
[Score: {score:.3f}] {doc.metadata['file_path']}:
{doc.content}
---
"""
                if current_length + len(doc_content) > available_length:
                    PrettyOutput.print(
                        "Due to context length limit, some fragments were omitted", 
                        output_type=OutputType.WARNING
                    )
                    break
                    
                prompt += doc_content
                current_length += len(doc_content)
            
            prompt += "\nIf the documents don't fully answer the question, please indicate what information is missing."
            
            # 使用 normal 平台处理文档问答
            model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
            response = model.chat_until_success(prompt)
            
            return response
            
        except Exception as e:
            PrettyOutput.print(f"Failed to answer: {str(e)}", OutputType.ERROR)
            return None

    def is_index_built(self) -> bool:
        """Check if the index is built and valid
        
        Returns:
            bool: True if index is built and valid
        """
        return self.index is not None and len(self.documents) > 0

def main():
    """Main function"""
    import argparse
    import sys
    
    # Set standard output encoding to UTF-8
    if sys.stdout.encoding != 'utf-8':
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    
    parser = argparse.ArgumentParser(description='Document retrieval and analysis tool')
    parser.add_argument('--dir', type=str, help='Directory to process')
    parser.add_argument('--build', action='store_true', help='Build document index')
    parser.add_argument('--search', type=str, help='Search document content')
    parser.add_argument('--ask', type=str, help='Ask about documents')
    args = parser.parse_args()

    try:
        current_dir = os.getcwd()
        rag = RAGTool(current_dir)

        if not args.dir:
            args.dir = current_dir

        if args.dir and args.build:
            PrettyOutput.print(f"Processing directory: {args.dir}", output_type=OutputType.INFO)
            rag.build_index(args.dir)
            return 0

        if args.search or args.ask:

            if args.search:
                results = rag.query(args.search)
                if not results:
                    PrettyOutput.print("No related content found", output_type=OutputType.WARNING)
                    return 1
                    
                for doc in results:
                    output = f"""File: {doc.metadata['file_path']}\n"""
                    output += f"""Fragment {doc.metadata['chunk_index'] + 1}/{doc.metadata['total_chunks']}\n"""
                    output += f"""Content:\n{doc.content}\n"""
                    PrettyOutput.print(output, output_type=OutputType.INFO, lang="markdown")
                return 0

            if args.ask:
                # Call ask method
                response = rag.ask(args.ask)
                if not response:
                    PrettyOutput.print("Failed to get answer", output_type=OutputType.WARNING)
                    return 1
                    
                # Display answer
                output = f"""Answer:\n{response}"""
                PrettyOutput.print(output, output_type=OutputType.INFO)
                return 0

        PrettyOutput.print("Please specify operation parameters. Use -h to view help.", output_type=OutputType.WARNING)
        return 1

    except Exception as e:
        PrettyOutput.print(f"Failed to execute: {str(e)}", output_type=OutputType.ERROR)
        return 1

if __name__ == "__main__":
    main()
