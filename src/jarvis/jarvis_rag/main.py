import os
import re
import numpy as np
import faiss
import torch  # Add torch import
from typing import List, Tuple, Optional, Dict
import pickle
from dataclasses import dataclass
from pathlib import Path
import contextlib  # 添加 contextlib 导入

from yaspin import yaspin
from jarvis.jarvis_platform.registry import PlatformRegistry
import lzma  # 添加 lzma 导入
from threading import Lock
import hashlib

from jarvis.jarvis_utils.config import get_max_paragraph_length, get_max_token_count, get_min_paragraph_length, get_thread_count, get_rag_ignored_paths
from jarvis.jarvis_utils.embedding import get_context_token_count, get_embedding, get_embedding_batch, load_embedding_model
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import  ct, get_file_md5, init_env, init_gpu_config, ot

from .file_processors import TextFileProcessor, PDFProcessor, DocxProcessor, PPTProcessor, ExcelProcessor

@dataclass
class Document:
    """Document class, for storing document content and metadata"""
    content: str  # Document content
    metadata: Dict  # Metadata (file path, position, etc.)
    md5: str = ""  # File MD5 value, for incremental update detection



class RAGTool:
    def __init__(self, root_dir: str):
        """Initialize RAG tool
        
        Args:
            root_dir: Project root directory
        """
        with yaspin(text="初始化环境...", color="cyan") as spinner:
            init_env()
            self.root_dir = root_dir
            os.chdir(self.root_dir)
            spinner.text = "环境初始化完成"
            spinner.ok("✅")
        
        # Initialize configuration
        with yaspin(text="初始化配置...", color="cyan") as spinner:
            self.min_paragraph_length = get_min_paragraph_length()  # Minimum paragraph length
            self.max_paragraph_length = get_max_paragraph_length()  # Maximum paragraph length
            self.context_window = 5  # Fixed context window size
            self.max_token_count = int(get_max_token_count() * 0.8)
            spinner.text = "配置初始化完成"
            spinner.ok("✅")
        
        # Initialize data directory
        with yaspin(text="初始化数据目录...", color="cyan") as spinner:
            self.data_dir = os.path.join(self.root_dir, ".jarvis/rag")
            if not os.path.exists(self.data_dir):
                os.makedirs(self.data_dir)
            spinner.text = "数据目录初始化完成"
            spinner.ok("✅")
            
        # Initialize embedding model
        with yaspin(text="初始化模型...", color="cyan") as spinner:
            try:
                self.embedding_model = load_embedding_model()
                self.vector_dim = self.embedding_model.get_sentence_embedding_dimension()
                spinner.text = "模型加载完成"
                spinner.ok("✅")
            except Exception as e:
                spinner.text = "模型加载失败"
                spinner.fail("❌")
                raise

        with yaspin(text="初始化缓存目录...", color="cyan") as spinner:
            self.cache_dir = os.path.join(self.data_dir, "cache")
            if not os.path.exists(self.cache_dir):
                os.makedirs(self.cache_dir)
                
            self.documents: List[Document] = []
            self.index = None
            self.flat_index = None
            self.file_md5_cache = {}
            spinner.text = "缓存目录初始化完成"
            spinner.ok("✅")
        
        # 加载缓存索引
        self._load_cache_index()

        # Register file processors
        with yaspin(text="初始化文件处理器...", color="cyan") as spinner:
            self.file_processors = [
                TextFileProcessor(),
                PDFProcessor(),
                DocxProcessor(),
                PPTProcessor(),
                ExcelProcessor()
            ]
            spinner.text = "文件处理器初始化完成"
            spinner.ok("✅")


        # Add thread related configuration
        with yaspin(text="初始化线程配置...", color="cyan") as spinner:
            self.thread_count = get_thread_count()
            self.vector_lock = Lock()  # Protect vector list concurrency
            spinner.text = "线程配置初始化完成"
            spinner.ok("✅")

        # 初始化 GPU 内存配置
        with yaspin(text="初始化 GPU 内存配置...", color="cyan") as spinner:
            with spinner.hidden():
                self.gpu_config = init_gpu_config()
            spinner.text = "GPU 内存配置初始化完成"
            spinner.ok("✅")


    def _get_cache_path(self, file_path: str, cache_type: str = "doc") -> str:
        """Get cache file path for a document
        
        Args:
            file_path: Original file path
            cache_type: Type of cache ("doc" for documents, "vec" for vectors)
            
        Returns:
            str: Cache file path
        """
        # 使用文件路径的哈希作为缓存文件名
        file_hash = hashlib.md5(file_path.encode()).hexdigest()
        
        # 确保不同类型的缓存有不同的目录
        if cache_type == "doc":
            cache_subdir = os.path.join(self.cache_dir, "documents")
        elif cache_type == "vec":
            cache_subdir = os.path.join(self.cache_dir, "vectors")
        else:
            cache_subdir = self.cache_dir
            
        # 确保子目录存在
        if not os.path.exists(cache_subdir):
            os.makedirs(cache_subdir)
            
        return os.path.join(cache_subdir, f"{file_hash}.cache")

    def _load_cache_index(self):
        """Load cache index"""
        index_path = os.path.join(self.data_dir, "index.pkl")
        if os.path.exists(index_path):
            try:
                with yaspin(text="加载缓存索引...", color="cyan") as spinner:
                    with lzma.open(index_path, 'rb') as f:
                        cache_data = pickle.load(f)
                        self.file_md5_cache = cache_data.get("file_md5_cache", {})
                    spinner.text = "缓存索引加载完成"
                    spinner.ok("✅")
                        
                # 从各个缓存文件加载文档
                with yaspin(text="加载缓存文件...", color="cyan") as spinner:
                    for file_path in self.file_md5_cache:
                        doc_cache_path = self._get_cache_path(file_path, "doc")
                        if os.path.exists(doc_cache_path):
                            try:
                                with lzma.open(doc_cache_path, 'rb') as f:
                                    doc_cache_data = pickle.load(f)
                                    self.documents.extend(doc_cache_data["documents"])
                                spinner.text = f"加载文档缓存: {file_path}"
                            except Exception as e:
                                spinner.write(f"❌ 加载文档缓存失败: {file_path}: {str(e)}")
                    spinner.text = "文档缓存加载完成"
                    spinner.ok("✅")
                
                # 重建向量索引
                if self.documents:
                    with yaspin(text="重建向量索引...", color="cyan") as spinner:
                        vectors = []
                        
                        # 按照文档列表顺序加载向量
                        processed_files = set()
                        for doc in self.documents:
                            file_path = doc.metadata['file_path']
                            
                            # 避免重复处理同一个文件
                            if file_path in processed_files:
                                continue
                                
                            processed_files.add(file_path)
                            vec_cache_path = self._get_cache_path(file_path, "vec")
                            
                            if os.path.exists(vec_cache_path):
                                try:
                                    # 加载该文件的向量缓存
                                    with lzma.open(vec_cache_path, 'rb') as f:
                                        vec_cache_data = pickle.load(f)
                                        file_vectors = vec_cache_data["vectors"]
                                    
                                    # 按照文档的chunk_index检索对应向量
                                    doc_indices = [d.metadata['chunk_index'] for d in self.documents 
                                                if d.metadata['file_path'] == file_path]
                                    
                                    # 检查向量数量与文档块数量是否匹配
                                    if len(doc_indices) <= file_vectors.shape[0]:
                                        for idx in doc_indices:
                                            if idx < file_vectors.shape[0]:
                                                vectors.append(file_vectors[idx].reshape(1, -1))
                                    else:
                                        spinner.write(f"⚠️ 向量缓存不匹配: {file_path}")
                                        
                                    spinner.text = f"加载向量缓存: {file_path}"
                                except Exception as e:
                                    spinner.write(f"❌ 加载向量缓存失败: {file_path}: {str(e)}")
                            else:
                                spinner.write(f"⚠️ 缺少向量缓存: {file_path}")
                        
                        if vectors:
                            vectors = np.vstack(vectors)
                            self._build_index(vectors, spinner)
                        spinner.text = f"向量索引重建完成，加载 {len(self.documents)} 个文档片段"
                        spinner.ok("✅")
                                
            except Exception as e:
                PrettyOutput.print(f"加载缓存索引失败: {str(e)}", 
                                output_type=OutputType.WARNING)
                self.documents = []
                self.index = None
                self.flat_index = None
                self.file_md5_cache = {}

    def _save_cache(self, file_path: str, documents: List[Document], vectors: np.ndarray, spinner=None):
        """Save cache for a single file
        
        Args:
            file_path: File path
            documents: List of documents
            vectors: Document vectors
            spinner: Optional spinner for progress display
        """
        try:
            # 保存文档缓存
            if spinner:
                spinner.text = f"保存 {file_path} 的文档缓存..."
            doc_cache_path = self._get_cache_path(file_path, "doc")
            doc_cache_data = {
                "documents": documents
            }
            with lzma.open(doc_cache_path, 'wb') as f:
                pickle.dump(doc_cache_data, f)
                
            # 保存向量缓存
            if spinner:
                spinner.text = f"保存 {file_path} 的向量缓存..."
            vec_cache_path = self._get_cache_path(file_path, "vec")
            vec_cache_data = {
                "vectors": vectors
            }
            with lzma.open(vec_cache_path, 'wb') as f:
                pickle.dump(vec_cache_data, f)
                
            # 更新并保存索引
            if spinner:
                spinner.text = f"更新 {file_path} 的索引缓存..."
            index_path = os.path.join(self.data_dir, "index.pkl")
            index_data = {
                "file_md5_cache": self.file_md5_cache
            }
            with lzma.open(index_path, 'wb') as f:
                pickle.dump(index_data, f)
            
            if spinner:
                spinner.text = f"{file_path} 的缓存保存完成"
                            
        except Exception as e:
            if spinner:
                spinner.text = f"保存 {file_path} 的缓存失败: {str(e)}"
            PrettyOutput.print(f"保存缓存失败: {str(e)}", output_type=OutputType.ERROR)

    def _build_index(self, vectors: np.ndarray, spinner=None):
        """Build FAISS index"""
        if vectors.shape[0] == 0:
            if spinner:
                spinner.text = "向量为空，跳过索引构建"
            self.index = None
            self.flat_index = None
            return
            
        # Create a flat index to store original vectors, for reconstruction
        if spinner:
            spinner.text = "创建平面索引用于向量重建..."
        self.flat_index = faiss.IndexFlatIP(self.vector_dim)
        self.flat_index.add(vectors) # type: ignore
        
        # Create an IVF index for fast search
        if spinner:
            spinner.text = "创建IVF索引用于快速搜索..."
        # 修改聚类中心的计算方式，小数据量时使用更少的聚类中心
        # 避免"WARNING clustering X points to Y centroids: please provide at least Z training points"警告
        num_vectors = vectors.shape[0]
        if num_vectors < 100:
            # 对于小于100个向量的情况，使用更少的聚类中心
            nlist = 1  # 只用1个聚类中心
        elif num_vectors < 1000:
            # 对于100-1000个向量的情况，使用较少的聚类中心
            nlist = max(1, int(num_vectors / 100))  # 每100个向量一个聚类中心
        else:
            # 原始逻辑：每1000个向量一个聚类中心，最少4个
            nlist = max(4, int(num_vectors / 1000))
            
        quantizer = faiss.IndexFlatIP(self.vector_dim)
        self.index = faiss.IndexIVFFlat(quantizer, self.vector_dim, nlist, faiss.METRIC_INNER_PRODUCT)
        
        # Train and add vectors
        if spinner:
            spinner.text = f"训练索引（{vectors.shape[0]}个向量，{nlist}个聚类中心）..."
        self.index.train(vectors) # type: ignore
        
        if spinner:
            spinner.text = "添加向量到索引..."
        self.index.add(vectors) # type: ignore
        
        # Set the number of clusters to probe during search
        if spinner:
            spinner.text = "设置搜索参数..."
        self.index.nprobe = min(nlist, 10)
        
        if spinner:
            spinner.text = f"索引构建完成，共 {vectors.shape[0]} 个向量"

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


    def _process_file(self, file_path: str, spinner=None) -> List[Document]:
        """Process a single file"""
        try:
            # Calculate file MD5
            if spinner:
                spinner.text = f"计算文件 {file_path} 的MD5..."
            current_md5 = get_file_md5(file_path)
            if not current_md5:
                if spinner:
                    spinner.text = f"文件 {file_path} 计算MD5失败"
                return []

            # Check if the file needs to be reprocessed
            if file_path in self.file_md5_cache and self.file_md5_cache[file_path] == current_md5:
                if spinner:
                    spinner.text = f"文件 {file_path} 未发生变化，跳过处理"
                return []

            # Find the appropriate processor
            if spinner:
                spinner.text = f"查找适用于 {file_path} 的处理器..."
            processor = None
            for p in self.file_processors:
                if p.can_handle(file_path):
                    processor = p
                    break
                    
            if not processor:
                # If no appropriate processor is found, return an empty document
                if spinner:
                    spinner.text = f"没有找到适用于 {file_path} 的处理器，跳过处理"
                return []
            
            # Extract text content
            if spinner:
                spinner.text = f"提取 {file_path} 的文本内容..."
            content = processor.extract_text(file_path)
            if not content.strip():
                if spinner:
                    spinner.text = f"文件 {file_path} 没有文本内容，跳过处理"
                return []
            
            # Split text
            if spinner:
                spinner.text = f"分割 {file_path} 的文本..."
            chunks = self._split_text(content)
            
            # Create document objects
            if spinner:
                spinner.text = f"为 {file_path} 创建 {len(chunks)} 个文档对象..."
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
            if spinner:
                spinner.text = f"文件 {file_path} 处理完成，共创建 {len(documents)} 个文档对象"
            return documents
            
        except Exception as e:
            if spinner:
                spinner.text = f"处理文件失败: {file_path}: {str(e)}"
            PrettyOutput.print(f"处理文件失败: {file_path}: {str(e)}", 
                            output_type=OutputType.ERROR)
            return []

    def _should_ignore_path(self, path: str, ignored_paths: List[str]) -> bool:
        """
        检查路径是否应该被忽略
        
        Args:
            path: 文件或目录路径
            ignored_paths: 忽略模式列表
            
        Returns:
            bool: 如果路径应该被忽略则返回True
        """
        import fnmatch
        import os
        
        # 获取相对路径
        rel_path = path
        if os.path.isabs(path):
            try:
                rel_path = os.path.relpath(path, self.root_dir)
            except ValueError:
                # 如果不能计算相对路径，使用原始路径
                pass
                
        path_parts = rel_path.split(os.sep)
        
        # 检查路径的每一部分是否匹配任意忽略模式
        for part in path_parts:
            for pattern in ignored_paths:
                if fnmatch.fnmatch(part, pattern):
                    return True
                    
        # 检查完整路径是否匹配任意忽略模式
        for pattern in ignored_paths:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
                
        return False
        
    def _is_git_repo(self) -> bool:
        """
        检查当前目录是否为Git仓库
        
        Returns:
            bool: 如果是Git仓库则返回True
        """
        import subprocess
        
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.root_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            return result.returncode == 0 and result.stdout.strip() == "true"
        except Exception:
            return False
    
    def _get_git_managed_files(self) -> List[str]:
        """
        获取Git仓库中被管理的文件列表
        
        Returns:
            List[str]: 被Git管理的文件路径列表（相对路径）
        """
        import subprocess
        
        try:
            # 获取git索引中的文件
            result = subprocess.run(
                ["git", "ls-files"],
                cwd=self.root_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                return []
                
            git_files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            
            # 添加未暂存但已跟踪的修改文件
            result = subprocess.run(
                ["git", "ls-files", "--modified"],
                cwd=self.root_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            
            if result.returncode == 0:
                modified_files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
                git_files.extend([f for f in modified_files if f not in git_files])
            
            # 转换为绝对路径
            return [os.path.join(self.root_dir, file) for file in git_files]
            
        except Exception as e:
            PrettyOutput.print(f"获取Git管理的文件失败: {str(e)}", output_type=OutputType.WARNING)
            return []

    def build_index(self, dir: str):
        try:
            """Build document index with optimized processing"""
            # Get all files
            with yaspin(text="获取所有文件...", color="cyan") as spinner:
                all_files = []
                
                # 获取需要忽略的路径列表
                ignored_paths = get_rag_ignored_paths()
                
                # 检查是否为Git仓库
                is_git_repo = self._is_git_repo()
                if is_git_repo:
                    git_files = self._get_git_managed_files()
                    # 过滤掉被忽略的文件
                    for file_path in git_files:
                        if self._should_ignore_path(file_path, ignored_paths):
                            continue
                            
                        if os.path.getsize(file_path) > 100 * 1024 * 1024:  # 100MB
                            PrettyOutput.print(f"跳过大文件: {file_path}", 
                                            output_type=OutputType.WARNING)
                            continue
                        all_files.append(file_path)
                else:
                    # 非Git仓库，使用常规文件遍历
                    for root, _, files in os.walk(dir):
                        # 检查目录是否匹配忽略模式
                        if self._should_ignore_path(root, ignored_paths):
                            continue
                            
                        for file in files:
                            file_path = os.path.join(root, file)
                            
                            # 检查文件是否匹配忽略模式
                            if self._should_ignore_path(file_path, ignored_paths):
                                continue
                                
                            if os.path.getsize(file_path) > 100 * 1024 * 1024:  # 100MB
                                PrettyOutput.print(f"跳过大文件: {file_path}", 
                                                output_type=OutputType.WARNING)
                                continue
                            all_files.append(file_path)
                            
                spinner.text = f"获取所有文件完成，共 {len(all_files)} 个文件"
                spinner.ok("✅")

            # Clean up cache for deleted files
            with yaspin(text="清理缓存...", color="cyan") as spinner:
                deleted_files = set(self.file_md5_cache.keys()) - set(all_files)
                deleted_count = len(deleted_files)
                
                if deleted_count > 0:
                    spinner.write(f"🗑️ 删除不存在文件的缓存: {deleted_count} 个")
                    
                for file_path in deleted_files:
                    # Remove from MD5 cache
                    del self.file_md5_cache[file_path]
                    # Remove related documents
                    self.documents = [doc for doc in self.documents if doc.metadata['file_path'] != file_path]
                    # Delete cache files
                    self._delete_file_cache(file_path, None)  # Pass None as spinner to not show individual deletions
                    
                spinner.text = f"清理缓存完成，共删除 {deleted_count} 个不存在文件的缓存"
                spinner.ok("✅")

            # Check file changes
            with yaspin(text="检查文件变化...", color="cyan") as spinner:
                files_to_process = []
                unchanged_files = []
                new_files_count = 0
                modified_files_count = 0
                
                for file_path in all_files:
                    current_md5 = get_file_md5(file_path)
                    if current_md5:  # Only process files that can successfully calculate MD5
                        if file_path in self.file_md5_cache and self.file_md5_cache[file_path] == current_md5:
                            # File未变化，记录但不重新处理
                            unchanged_files.append(file_path)
                        else:
                            # New file or modified file
                            files_to_process.append(file_path)
                            
                            # 如果是修改的文件，删除旧缓存
                            if file_path in self.file_md5_cache:
                                modified_files_count += 1
                                # 删除旧缓存
                                self._delete_file_cache(file_path, spinner)
                                # 从文档列表中移除
                                self.documents = [doc for doc in self.documents if doc.metadata['file_path'] != file_path]
                            else:
                                new_files_count += 1
                
                # 输出汇总信息
                if unchanged_files:
                    spinner.write(f"📚 已缓存文件: {len(unchanged_files)} 个")
                if new_files_count > 0:
                    spinner.write(f"🆕 新增文件: {new_files_count} 个")
                if modified_files_count > 0:
                    spinner.write(f"📝 修改文件: {modified_files_count} 个")
                    
                spinner.text = f"检查文件变化完成，共 {len(files_to_process)} 个文件需要处理"
                spinner.ok("✅")

            # Keep documents for unchanged files
            unchanged_documents = [doc for doc in self.documents 
                                if doc.metadata['file_path'] in unchanged_files]

            # Process files one by one with optimized vectorization
            if files_to_process:
                new_documents = []
                new_vectors = []
                success_count = 0
                skipped_count = 0
                failed_count = 0
                
                with yaspin(text=f"处理文件中 (0/{len(files_to_process)})...", color="cyan") as spinner:
                    for index, file_path in enumerate(files_to_process):
                        spinner.text = f"处理文件中 ({index+1}/{len(files_to_process)}): {file_path}"
                        try:
                            # Process single file
                            file_docs = self._process_file(file_path, spinner)
                            if file_docs:
                                # Vectorize documents from this file
                                spinner.text = f"处理文件中 ({index+1}/{len(files_to_process)}): 为 {file_path} 生成向量嵌入..."
                                texts_to_vectorize = [
                                    f"File:{doc.metadata['file_path']} Content:{doc.content}"
                                    for doc in file_docs
                                ]
                                
                                file_vectors = get_embedding_batch(self.embedding_model, f"({index+1}/{len(files_to_process)}){file_path}", texts_to_vectorize, spinner)
                                
                                # Save cache for this file
                                spinner.text = f"处理文件中 ({index+1}/{len(files_to_process)}): 保存 {file_path} 的缓存..."
                                self._save_cache(file_path, file_docs, file_vectors, spinner)
                                
                                # Accumulate documents and vectors
                                new_documents.extend(file_docs)
                                new_vectors.append(file_vectors)
                                success_count += 1
                            else:
                                # 文件跳过处理
                                skipped_count += 1
                                
                        except Exception as e:
                            spinner.write(f"❌ 处理失败: {file_path}: {str(e)}")
                            failed_count += 1
                    
                    # 输出处理统计
                    spinner.text = f"文件处理完成: 成功 {success_count} 个, 跳过 {skipped_count} 个, 失败 {failed_count} 个"
                    spinner.ok("✅")
                    
                # Update documents list
                self.documents.extend(new_documents)

                # Build final index
                if new_vectors:
                    with yaspin(text="构建最终索引...", color="cyan") as spinner:
                        spinner.text = "合并新向量..."
                        all_new_vectors = np.vstack(new_vectors)
                        
                        unchanged_vector_count = 0
                        if self.flat_index is not None:
                            # Get vectors for unchanged documents
                            spinner.text = "获取未变化文档的向量..."
                            unchanged_vectors = self._get_unchanged_vectors(unchanged_documents, spinner)
                            if unchanged_vectors is not None:
                                unchanged_vector_count = unchanged_vectors.shape[0]
                                spinner.text = f"合并新旧向量（新：{all_new_vectors.shape[0]}，旧：{unchanged_vector_count}）..."
                                final_vectors = np.vstack([unchanged_vectors, all_new_vectors])
                            else:
                                spinner.text = f"仅使用新向量（{all_new_vectors.shape[0]}）..."
                                final_vectors = all_new_vectors
                        else:
                            spinner.text = f"仅使用新向量（{all_new_vectors.shape[0]}）..."
                            final_vectors = all_new_vectors

                        # Build index
                        spinner.text = f"构建索引（向量数量：{final_vectors.shape[0]}）..."
                        self._build_index(final_vectors, spinner)
                        spinner.text = f"索引构建完成，共 {len(self.documents)} 个文档片段"
                        spinner.ok("✅")

                # 输出最终统计信息
                PrettyOutput.print(
                    f"📊 索引统计:\n"
                    f"  • 总文档数: {len(self.documents)} 个文档片段\n"
                    f"  • 已缓存文件: {len(unchanged_files)} 个\n"
                    f"  • 处理文件: {len(files_to_process)} 个\n"
                    f"    - 成功: {success_count} 个\n"
                    f"    - 跳过: {skipped_count} 个\n"
                    f"    - 失败: {failed_count} 个", 
                    OutputType.SUCCESS
                )
        except Exception as e:
            PrettyOutput.print(f"索引构建失败: {str(e)}", 
                            output_type=OutputType.ERROR)

    def _get_unchanged_vectors(self, unchanged_documents: List[Document], spinner=None) -> Optional[np.ndarray]:
        """Get vectors for unchanged documents from existing index"""
        try:
            if not unchanged_documents:
                if spinner:
                    spinner.text = "没有未变化的文档"
                return None

            if spinner:
                spinner.text = f"加载 {len(unchanged_documents)} 个未变化文档的向量..."
            
            # 按文件分组处理
            unchanged_files = set(doc.metadata['file_path'] for doc in unchanged_documents)
            unchanged_vectors = []
            
            for file_path in unchanged_files:
                if spinner:
                    spinner.text = f"加载 {file_path} 的向量..."
                
                # 获取该文件所有文档的chunk索引
                doc_indices = [(i, doc.metadata['chunk_index']) 
                              for i, doc in enumerate(unchanged_documents) 
                              if doc.metadata['file_path'] == file_path]
                
                if not doc_indices:
                    continue
                
                # 加载该文件的向量
                vec_cache_path = self._get_cache_path(file_path, "vec")
                if os.path.exists(vec_cache_path):
                    try:
                        with lzma.open(vec_cache_path, 'rb') as f:
                            vec_cache_data = pickle.load(f)
                            file_vectors = vec_cache_data["vectors"]
                        
                        # 按照chunk_index加载对应的向量
                        for _, chunk_idx in doc_indices:
                            if chunk_idx < file_vectors.shape[0]:
                                unchanged_vectors.append(file_vectors[chunk_idx].reshape(1, -1))
                            
                        if spinner:
                            spinner.text = f"成功加载 {file_path} 的向量"
                    except Exception as e:
                        if spinner:
                            spinner.text = f"加载 {file_path} 向量失败: {str(e)}"
                else:
                    if spinner:
                        spinner.text = f"未找到 {file_path} 的向量缓存"
                        
                    # 从flat_index重建向量
                    if self.flat_index is not None:
                        if spinner:
                            spinner.text = f"从索引重建 {file_path} 的向量..."
                        
                        for doc_idx, chunk_idx in doc_indices:
                            idx = next((i for i, d in enumerate(self.documents) 
                                     if d.metadata['file_path'] == file_path and 
                                     d.metadata['chunk_index'] == chunk_idx), None)
                            
                            if idx is not None:
                                vector = np.zeros((1, self.vector_dim), dtype=np.float32) # type: ignore
                                self.flat_index.reconstruct(idx, vector.ravel())
                                unchanged_vectors.append(vector)

            if not unchanged_vectors:
                if spinner:
                    spinner.text = "未能加载任何未变化文档的向量"
                return None
                
            if spinner:
                spinner.text = f"未变化文档向量加载完成，共 {len(unchanged_vectors)} 个"
                
            return np.vstack(unchanged_vectors)
            
        except Exception as e:
            if spinner:
                spinner.text = f"获取不变向量失败: {str(e)}"
            PrettyOutput.print(f"获取不变向量失败: {str(e)}", OutputType.ERROR)
            return None

    def _perform_keyword_search(self, query: str, limit: int = 30) -> List[Tuple[int, float]]:
        """执行基于关键词的文本搜索
        
        Args:
            query: 查询字符串
            limit: 返回结果数量限制
            
        Returns:
            List[Tuple[int, float]]: 文档索引和得分的列表
        """
        # 使用大模型生成关键词
        keywords = self._generate_keywords_with_llm(query)
        
        # 如果大模型生成失败，回退到简单的关键词提取
        if not keywords:
            # 简单的关键词预处理
            keywords = query.lower().split()
            # 移除停用词和过短的词
            stop_words = {'的', '了', '和', '是', '在', '有', '与', '对', '为', 'a', 'an', 'the', 'and', 'is', 'in', 'of', 'to', 'with'}
            keywords = [k for k in keywords if k not in stop_words and len(k) > 1]
        
        if not keywords:
            return []
        
        # 使用TF-IDF思想的简单实现
        doc_scores = []
        
        # 计算IDF（逆文档频率）
        doc_count = len(self.documents)
        keyword_doc_count = {}
        
        for keyword in keywords:
            count = 0
            for doc in self.documents:
                if keyword in doc.content.lower():
                    count += 1
            keyword_doc_count[keyword] = max(1, count)  # 避免除零错误
        
        # 计算每个关键词的IDF值
        keyword_idf = {
            keyword: np.log(doc_count / count) 
            for keyword, count in keyword_doc_count.items()
        }
        
        # 为每个文档计算得分
        for i, doc in enumerate(self.documents):
            doc_content = doc.content.lower()
            score = 0
            
            # 计算每个关键词的TF（词频）
            for keyword in keywords:
                # 简单的TF：关键词在文档中出现的次数
                tf = doc_content.count(keyword)
                # TF-IDF得分
                if tf > 0:
                    score += tf * keyword_idf[keyword]
            
            # 添加额外权重：标题匹配、完整短语匹配等
            if query.lower() in doc_content:
                score *= 2.0  # 完整查询匹配加倍得分
                
            # 文件路径匹配也加分
            file_path = doc.metadata['file_path'].lower()
            for keyword in keywords:
                if keyword in file_path:
                    score += 0.5 * keyword_idf.get(keyword, 1.0)
            
            if score > 0:
                # 归一化得分（0-1范围）
                doc_scores.append((i, score))
        
        # 排序并限制结果数量
        doc_scores.sort(key=lambda x: x[1], reverse=True)
        
        # 归一化分数到0-1之间
        if doc_scores:
            max_score = max(score for _, score in doc_scores)
            if max_score > 0:
                doc_scores = [(idx, score/max_score) for idx, score in doc_scores]
        
        return doc_scores[:limit]

    def _generate_keywords_with_llm(self, query: str) -> List[str]:
        """
        使用大语言模型从查询中提取关键词
        
        Args:
            query: 用户查询
            
        Returns:
            List[str]: 提取的关键词列表
        """
        try:
            from jarvis.jarvis_utils.output import PrettyOutput, OutputType
            from jarvis.jarvis_platform.registry import PlatformRegistry
            
            # 获取平台注册表和模型
            registry = PlatformRegistry.get_global_platform_registry()
            model = registry.get_normal_platform()

            # 构建关键词提取提示词
            prompt = f"""
            请分析以下查询，提取用于文档检索的关键词。你的任务是：
            
            1. 识别核心概念、主题和实体，包括:
               - 技术术语和专业名词
               - 代码相关的函数名、类名、变量名和库名
               - 重要的业务领域词汇
               - 操作和动作相关的词汇
            
            2. 优先提取与以下场景相关的关键词:
               - 代码搜索: 编程语言、框架、API、特定功能
               - 文档检索: 主题、标题词汇、专业名词
               - 错误排查: 错误信息、异常名称、问题症状
            
            3. 同时包含:
               - 中英文关键词 (尤其是技术领域常用英文术语)
               - 完整的专业术语和缩写形式
               - 可能的同义词或相关概念
            
            4. 关键词应当精准、具体，数量控制在3-10个之间。
            
            输出格式：
            {ot("KEYWORD")}
            关键词1
            关键词2
            ...
            {ct("KEYWORD")}
            
            查询文本:
            {query}

            仅返回提取的关键词，不要包含其他内容。
            """
            
            # 调用大模型获取响应
            response = model.chat_until_success(prompt)
            
            if response:
                # 清理响应，提取关键词
                sm = re.search(ot('KEYWORD') + r"(.*?)" + ct('KEYWORD'), response, re.DOTALL)
                if sm:
                    extracted_keywords = sm[1]
                
                    if extracted_keywords:
                        # 记录检测到的关键词
                        ret = extracted_keywords.strip().splitlines()
                        return ret
                
            # 如果处理失败，返回空列表
            return []
            
        except Exception as e:
            from jarvis.jarvis_utils.output import PrettyOutput, OutputType
            PrettyOutput.print(f"使用大模型生成关键词失败: {str(e)}", OutputType.WARNING)
            return []

    def _hybrid_search(self, query: str, top_k: int = 30) -> List[Tuple[int, float]]:
        """混合搜索方法，综合向量相似度和关键词匹配
        
        Args:
            query: 查询字符串
            top_k: 返回结果数量限制
            
        Returns:
            List[Tuple[int, float]]: 文档索引和得分的列表
        """
        # 获取向量搜索结果
        query_vector = get_embedding(self.embedding_model, query)
        query_vector = query_vector.reshape(1, -1)
        
        # 进行向量搜索
        vector_limit = min(top_k * 3, len(self.documents))
        if self.index and vector_limit > 0:
            distances, indices = self.index.search(query_vector, vector_limit) # type: ignore
            vector_results = [(int(idx), 1.0 / (1.0 + float(dist))) 
                             for idx, dist in zip(indices[0], distances[0])
                             if idx != -1 and idx < len(self.documents)]
        else:
            vector_results = []
        
        # 进行关键词搜索
        keyword_results = self._perform_keyword_search(query, top_k * 2)
        
        # 合并结果集
        combined_results = {}
        
        # 加入向量结果，权重为0.7
        for idx, score in vector_results:
            combined_results[idx] = score * 0.7
        
        # 加入关键词结果，权重为0.3，如果文档已存在则取加权平均
        for idx, score in keyword_results:
            if idx in combined_results:
                # 已有向量得分，取加权平均
                combined_results[idx] = combined_results[idx] + score * 0.3
            else:
                # 新文档，直接添加关键词得分（权重稍低）
                combined_results[idx] = score * 0.3
        
        # 转换成列表并排序
        result_list = [(idx, score) for idx, score in combined_results.items()]
        result_list.sort(key=lambda x: x[1], reverse=True)
        
        return result_list[:top_k]

    def _rerank_candidates(self, query: str, initial_indices: List[int], spinner=None) -> Tuple[List[int], List[Tuple[int, float]]]:
        """对候选文档进行重排序以提高准确度
        
        Args:
            query: 查询文本
            initial_indices: 初始候选文档索引
            spinner: 用于显示进度的spinner对象(可选)
            
        Returns:
            Tuple[List[int], List[Tuple[int, float]]]: 重排序后的文档索引及对应评分
        """
        try:
            # 获取重排序模型
            from jarvis.jarvis_utils.embedding import load_rerank_model
            
            with spinner.hidden() if spinner else contextlib.nullcontext():
                rerank_model, rerank_tokenizer = load_rerank_model()
            
            # 准备重排序的文档
            rerank_candidates = []
            rerank_indices = []
            
            # 收集有效的文档用于重排序
            for i, idx in enumerate(initial_indices):
                if idx < len(self.documents):  # 确保索引有效
                    doc = self.documents[idx]
                    # 获取文档内容，添加文件路径作为上下文增强
                    doc_text = f"文件: {doc.metadata['file_path']}\n{doc.content}"
                    rerank_candidates.append(doc_text)
                    rerank_indices.append((i, idx))
            
            # 如果有候选文档，进行重排序
            if rerank_candidates:
                if spinner:
                    spinner.text = f"重排序 {len(rerank_candidates)} 个候选文档..."
                
                # 分批重排序以避免内存溢出
                batch_size = 50
                all_scores = []
                
                # 先尝试使用GPU进行重排序
                use_gpu = torch.cuda.is_available()
                gpu_failed = False
                
                try:
                    for i in range(0, len(rerank_candidates), batch_size):
                        batch = rerank_candidates[i:i+batch_size]
                        # 准备重排序模型的输入
                        inputs = []
                        for doc in batch:
                            inputs.append((query, doc))
                            
                        model_inputs = rerank_tokenizer.batch_encode_plus( # type: ignore
                            inputs,
                            padding=True,
                            truncation=True,
                            return_tensors="pt",
                            max_length=512
                        )
                        
                        # 将张量移到适当的设备上
                        if use_gpu:
                            try:
                                model_inputs = {k: v.cuda() for k, v in model_inputs.items()}
                            except Exception as gpu_error:
                                if spinner:
                                    spinner.text = f"GPU加载失败({str(gpu_error)})，切换到CPU..."
                                use_gpu = False
                                gpu_failed = True
                                # 重新开始本批次，使用CPU
                                raise RuntimeError("GPU加载失败，切换到CPU") from gpu_error
                        
                        # 使用当前设备计算重排序得分
                        with torch.no_grad():
                            outputs = rerank_model(**model_inputs) # type: ignore
                            scores = outputs.logits
                            scores = scores.detach().cpu().numpy()
                            all_scores.extend(scores.squeeze().tolist())
                            
                        if spinner and i + batch_size < len(rerank_candidates):
                            spinner.text = f"重排序进度: {i + batch_size}/{len(rerank_candidates)} ({use_gpu and 'GPU' or 'CPU'})"
                
                except Exception as e:
                    # 如果使用GPU失败，尝试切换到CPU重新处理整个任务
                    if use_gpu or gpu_failed:
                        if spinner:
                            spinner.text = f"GPU重排序失败，切换到CPU重试..."
                        
                        # 重置得分和使用CPU
                        all_scores = []
                        use_gpu = False
                        
                        # 使用CPU重新处理所有批次
                        for i in range(0, len(rerank_candidates), batch_size):
                            batch = rerank_candidates[i:i+batch_size]
                            
                            inputs = []
                            for doc in batch:
                                inputs.append((query, doc))
                                
                            model_inputs = rerank_tokenizer.batch_encode_plus( # type: ignore
                                inputs,
                                padding=True,
                                truncation=True,
                                return_tensors="pt",
                                max_length=512
                            )
                            
                            # 确保在CPU上处理
                            with torch.no_grad():
                                outputs = rerank_model(**model_inputs) # type: ignore
                                scores = outputs.logits
                                scores = scores.detach().cpu().numpy()
                                all_scores.extend(scores.squeeze().tolist())
                                
                            if spinner and i + batch_size < len(rerank_candidates):
                                spinner.text = f"CPU重排序进度: {i + batch_size}/{len(rerank_candidates)}"
                    else:
                        # 如果CPU也失败，则抛出异常
                        raise
                
                # 将重排序得分与候选文档和原始索引关联
                reranked_results = []
                for (orig_i, idx), score in zip(rerank_indices, all_scores):
                    reranked_results.append((idx, score))
                
                # 按重排序得分排序（降序）
                reranked_results.sort(key=lambda x: x[1], reverse=True)
                
                # 提取排序后的文档索引
                reranked_indices = [idx for idx, _ in reranked_results]
                
                if spinner:
                    spinner.text = f"重排序完成 (使用{'GPU' if use_gpu else 'CPU'})"
                
                # 返回重排序结果及评分
                return reranked_indices, reranked_results
            else:
                # 如果没有找到有效候选，返回原始索引
                if spinner:
                    spinner.text = "跳过重排序（无有效候选）"
                
                # 返回原始结果，没有评分
                return initial_indices, []
        
        except Exception as e:
            # 如果重排序失败，返回原始索引
            if spinner:
                spinner.text = f"重排序失败（{str(e)}），使用原始检索结果"
            
            # 返回原始索引，没有评分
            return initial_indices, []

    def search(self, query: str, top_k: int = 30) -> List[Tuple[Document, float]]:
        """Search documents with context window"""
        if not self.is_index_built():
            PrettyOutput.print("索引未建立，自动建立索引中...", OutputType.INFO)
            self.build_index(self.root_dir)
            
        # 如果索引建立失败或文档列表为空，返回空结果
        if not self.is_index_built():
            PrettyOutput.print("索引建立失败或文档列表为空", OutputType.WARNING)
            return []
            
        # 使用混合搜索获取候选文档
        with yaspin(text="执行混合搜索...", color="cyan") as spinner:
            # 获取初始候选结果
            search_results = self._hybrid_search(query, top_k * 2)
            
            if not search_results:
                spinner.text = "搜索结果为空"
                spinner.fail("❌")
                return []
                
            # 准备重排序
            initial_indices = [idx for idx, _ in search_results]
            spinner.text = f"检索完成，获取 {len(initial_indices)} 个候选文档"
            spinner.ok("✅")
        
        # Apply reranking for better accuracy
        with yaspin(text="重排序以提高准确度...", color="cyan") as spinner:
            # 调用重排序函数
            indices_list, reranked_results = self._rerank_candidates(query, initial_indices, spinner)
            
            if reranked_results:  # 如果重排序成功
                spinner.text = "重排序完成"
            else:  # 使用原始检索结果
                indices_list = [idx for idx, _ in search_results if idx < len(self.documents)]
            
            spinner.ok("✅")
        
        # Process results with context window
        with yaspin(text="处理结果...", color="cyan") as spinner:
            results = []
            seen_files = set()
            
            # 检查索引列表是否为空
            if not indices_list:
                spinner.text = "搜索结果为空"
                spinner.fail("❌")
                return []
                
            for idx in indices_list:
                if idx < len(self.documents):  # 确保索引有效
                    doc = self.documents[idx]
                    
                    # 使用重排序得分或基于原始相似度的得分
                    similarity = next((score for i, score in reranked_results if i == idx), 0.5) if reranked_results else 0.5
                    
                    file_path = doc.metadata['file_path']
                    if file_path not in seen_files:
                        seen_files.add(file_path)
                        
                        # Get full context from original document
                        original_doc = next((d for d in self.documents 
                                        if d.metadata['file_path'] == file_path), None)
                        if original_doc:
                            window_docs = []  # Add this line to initialize the list
                            # Find all chunks from this file
                            file_chunks = [d for d in self.documents 
                                        if d.metadata['file_path'] == file_path]
                            # Add all related chunks
                            for chunk_doc in file_chunks:
                                window_docs.append((chunk_doc, similarity * 0.9))
                        
                        results.extend(window_docs)
                        if len(results) >= top_k * (2 * self.context_window + 1):
                            break
            spinner.text = "处理结果完成"
            spinner.ok("✅")
        
        # Sort by similarity and deduplicate
        with yaspin(text="排序...", color="cyan") as spinner:
            if not results:
                spinner.text = "无有效结果"
                spinner.fail("❌")
                return []
                
            results.sort(key=lambda x: x[1], reverse=True)
            seen = set()
            final_results = []
            for doc, score in results:
                key = (doc.metadata['file_path'], doc.metadata['chunk_index'])
                if key not in seen:
                    seen.add(key)
                    final_results.append((doc, score))
                    if len(final_results) >= top_k:
                        break
            spinner.text = "排序完成"
            spinner.ok("✅")
                    
        return final_results

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
            # 检查索引是否已建立，如果没有则自动建立
            if not self.is_index_built():
                PrettyOutput.print("索引未建立，自动建立索引中...", OutputType.INFO)
                self.build_index(self.root_dir)
                
                # 如果建立索引后仍未成功，返回错误信息
                if not self.is_index_built():
                    PrettyOutput.print("无法建立索引，请检查文档和配置", OutputType.ERROR)
                    return "无法建立索引，请检查文档和配置。可能的原因：文档目录为空、权限不足或格式不支持。"
            
            # 增强查询预处理 - 提取关键词和语义信息
            enhanced_query = self._enhance_query(question)
            
            # 使用增强的查询进行搜索
            results = self.search(enhanced_query)
            if not results:
                return "未找到与问题相关的文档。请尝试重新表述问题或确认问题相关内容已包含在索引中。"
            
            prompt = f"""
# 🤖 角色定义
您是一位文档分析专家，能够基于提供的文档提供准确且全面的回答。

# 🎯 核心职责
- 全面分析文档片段
- 准确回答问题
- 引用源文档
- 识别缺失信息
- 保持专业语气

# 📋 回答要求
## 内容质量
- 严格基于提供的文档作答
- 具体且精确
- 在有帮助时引用相关内容
- 指出任何信息缺口
- 使用专业语言

## 回答结构
1. 直接回答
   - 清晰简洁的回应
   - 基于文档证据
   - 专业术语

2. 支持细节
   - 相关文档引用
   - 文件参考
   - 上下文解释

3. 信息缺口（如有）
   - 缺失信息
   - 需要的额外上下文
   - 潜在限制

# 🔍 分析上下文
问题: {question}

相关文档（按相关性排序）：
"""

            # Add context with length control and deduplication
            with yaspin(text="添加上下文...", color="cyan") as spinner:
                available_count = self.max_token_count - get_context_token_count(prompt) - 1000
                current_count = 0
                
                # 保存已添加的内容指纹，避免重复
                added_content_hashes = set()
                
                # 分组文档，按文件路径整理
                file_groups = {}
                for doc, score in results:
                    file_path = doc.metadata['file_path']
                    if file_path not in file_groups:
                        file_groups[file_path] = []
                    file_groups[file_path].append((doc, score))
                
                # 按文件添加文档片段
                for file_path, docs in file_groups.items():
                    # 按相关性排序
                    docs.sort(key=lambda x: x[1], reverse=True)
                    
                    # 添加文件信息
                    file_header = f"\n## 文件: {file_path}\n"
                    if current_count + get_context_token_count(file_header) > available_count:
                        break
                    
                    prompt += file_header
                    current_count += get_context_token_count(file_header)
                    
                    # 添加最相关的文档片段
                    added_count = 0
                    for doc, score in docs:
                        # 计算内容指纹以避免重复
                        content_hash = hash(doc.content)
                        if content_hash in added_content_hashes:
                            continue
                            
                        # 如果内容相似度低于阈值，跳过
                        if score < 0.2:
                            continue
                            
                        # 格式化文档片段
                        doc_content = f"""
### 片段 {doc.metadata['chunk_index'] + 1}/{doc.metadata['total_chunks']} [相关度: {score:.2f}]
```
{doc.content}
```
"""
                        if current_count + get_context_token_count(doc_content) > available_count:
                            break
                            
                        prompt += doc_content
                        current_count += get_context_token_count(doc_content)
                        added_content_hashes.add(content_hash)
                        added_count += 1
                        
                        # 每个文件最多添加3个最相关的片段
                        if added_count >= 3:
                            break
                
                if current_count >= available_count:
                    PrettyOutput.print(
                        "由于上下文长度限制，部分内容被省略",
                        output_type=OutputType.WARNING
                    )

                prompt += """
# ❗ 重要规则
1. 仅使用提供的文档
2. 保持精确和准确
3. 在相关时引用来源
4. 指出缺失的信息
5. 保持专业语气
6. 使用用户的语言回答
"""
                spinner.text = "添加上下文完成"
                spinner.ok("✅")

            with yaspin(text="正在生成答案...", color="cyan") as spinner:
                model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
                response = model.chat_until_success(prompt)
                spinner.text = "答案生成完成"
                spinner.ok("✅")
                return response
            
        except Exception as e:
            PrettyOutput.print(f"回答失败：{str(e)}", OutputType.ERROR)
            return None
            
    def _enhance_query(self, query: str) -> str:
        """增强查询以提高检索质量
        
        Args:
            query: 原始查询
            
        Returns:
            str: 增强后的查询
        """
        # 简单的查询预处理
        query = query.strip()
        
        # 如果查询太短，返回原始查询
        if len(query) < 10:
            return query
            
        try:
            # 尝试使用大模型增强查询（如果可用）
            model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
            enhance_prompt = f"""请分析以下查询，提取关键概念、关键词和主题。
            
查询："{query}"

输出格式：对原始查询的改写版本，专注于提取关键信息，保留原始语义，以提高检索相关度。
仅输出改写后的查询文本，不要输出其他内容。
只对信息进行最小必要的增强，不要过度添加与原始查询无关的内容。
"""
            
            enhanced_query = model.chat_until_success(enhance_prompt)
            # 清理增强的查询结果
            enhanced_query = enhanced_query.strip().strip('"')
            
            # 如果增强查询有效且不是完全相同的，使用它
            if enhanced_query and len(enhanced_query) >= len(query) / 2 and enhanced_query != query:
                return enhanced_query
                
        except Exception:
            # 如果增强失败，使用原始查询
            pass
            
        return query

    def is_index_built(self) -> bool:
        """Check if the index is built and valid
        
        Returns:
            bool: True if index is built and valid
        """
        return self.index is not None and len(self.documents) > 0

    def _delete_file_cache(self, file_path: str, spinner=None):
        """Delete cache files for a specific file
        
        Args:
            file_path: Path to the original file
            spinner: Optional spinner for progress information. If None, runs silently.
        """
        try:
            # Delete document cache
            doc_cache_path = self._get_cache_path(file_path, "doc")
            if os.path.exists(doc_cache_path):
                os.remove(doc_cache_path)
                if spinner is not None:
                    spinner.write(f"🗑️ 删除文档缓存: {file_path}")
                    
            # Delete vector cache
            vec_cache_path = self._get_cache_path(file_path, "vec")
            if os.path.exists(vec_cache_path):
                os.remove(vec_cache_path)
                if spinner is not None:
                    spinner.write(f"🗑️ 删除向量缓存: {file_path}")
                    
        except Exception as e:
            if spinner is not None:
                spinner.write(f"❌ 删除缓存失败: {file_path}: {str(e)}")
            PrettyOutput.print(f"删除缓存失败: {file_path}: {str(e)}", output_type=OutputType.ERROR)

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
            rag.build_index(args.dir)
            return 0

        if args.search or args.ask:
            # 当需要搜索或提问时，自动检查并建立索引
            if not rag.is_index_built():
                PrettyOutput.print(f"索引未建立，自动为目录 '{args.dir}' 建立索引...", OutputType.INFO)
                rag.build_index(args.dir)
                
                if not rag.is_index_built():
                    PrettyOutput.print("索引建立失败，请检查目录和文件格式", OutputType.ERROR)
                    return 1

            if args.search:
                results = rag.query(args.search)
                if not results:
                    PrettyOutput.print("未找到相关内容", output_type=OutputType.WARNING)
                    return 1
                    
                for doc in results:
                    output = f"""文件: {doc.metadata['file_path']}\n"""
                    output += f"""片段 {doc.metadata['chunk_index'] + 1}/{doc.metadata['total_chunks']}\n"""
                    output += f"""内容:\n{doc.content}\n"""
                    PrettyOutput.print(output, output_type=OutputType.INFO, lang="markdown")
                return 0

            if args.ask:
                # Call ask method
                response = rag.ask(args.ask)
                if not response:
                    PrettyOutput.print("获取答案失败", output_type=OutputType.WARNING)
                    return 1
                    
                # Display answer
                output = f"""{response}"""
                PrettyOutput.print(output, output_type=OutputType.INFO)
                return 0

        PrettyOutput.print("请指定操作参数。使用 -h 查看帮助。", output_type=OutputType.WARNING)
        return 1

    except Exception as e:
        PrettyOutput.print(f"执行失败: {str(e)}", output_type=OutputType.ERROR)
        return 1

if __name__ == "__main__":
    main()
