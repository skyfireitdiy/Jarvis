import os
import numpy as np
import faiss
from typing import List, Tuple, Optional, Dict
import pickle
from jarvis.utils import OutputType, PrettyOutput, get_file_md5, get_max_context_length, load_embedding_model, load_rerank_model
from jarvis.utils import init_env
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
                text_parts.append(page.get_text())
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
        self.min_paragraph_length = int(os.environ.get("JARVIS_MIN_PARAGRAPH_LENGTH", "50"))  # Minimum paragraph length
        self.max_paragraph_length = int(os.environ.get("JARVIS_MAX_PARAGRAPH_LENGTH", "1000"))  # Maximum paragraph length
        self.context_window = int(os.environ.get("JARVIS_CONTEXT_WINDOW", "5"))  # Context window size, default前后各5个片段
        self.max_context_length = int(get_max_context_length() * 0.8)
        
        # Initialize data directory
        self.data_dir = os.path.join(self.root_dir, ".jarvis-rag")
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

        # Initialize cache and index
        self.cache_path = os.path.join(self.data_dir, "cache.pkl")
        self.documents: List[Document] = []
        self.index = None  # IVF index for search
        self.flat_index = None  # Store original vectors
        self.file_md5_cache = {}  # Store file MD5 values
        
        # Load cache
        self._load_cache()

        # Register file processors
        self.file_processors = [
            TextFileProcessor(),
            PDFProcessor(),
            DocxProcessor()
        ]

        # Add thread related configuration
        self.thread_count = int(os.environ.get("JARVIS_THREAD_COUNT", os.cpu_count() or 4))
        self.vector_lock = Lock()  # Protect vector list concurrency

    def _load_cache(self):
        """Load cache data"""
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
                PrettyOutput.print(f"Loaded {len(self.documents)} document fragments", 
                                output_type=OutputType.INFO)
            except Exception as e:
                PrettyOutput.print(f"Failed to load cache: {str(e)}", 
                                output_type=OutputType.WARNING)
                self.documents = []
                self.index = None
                self.flat_index = None
                self.file_md5_cache = {}

    def _save_cache(self, vectors: np.ndarray):
        """Optimize cache saving"""
        try:
            cache_data = {
                "version": "1.0",
                "timestamp": datetime.now().isoformat(),
                "documents": self.documents,
                "vectors": vectors.copy() if vectors is not None else None,  # Create a copy of the array
                "file_md5_cache": dict(self.file_md5_cache),  # Create a copy of the dictionary
                "metadata": {
                    "vector_dim": self.vector_dim,
                    "total_docs": len(self.documents),
                    "model_name": self.embedding_model.__class__.__name__
                }
            }
            
            # First serialize the data to a byte stream
            data = pickle.dumps(cache_data, protocol=pickle.HIGHEST_PROTOCOL)
            
            # Then use LZMA to compress the byte stream
            with lzma.open(self.cache_path, 'wb') as f:
                f.write(data)
            
            # Create a backup
            backup_path = f"{self.cache_path}.backup"
            shutil.copy2(self.cache_path, backup_path)
            
            PrettyOutput.print(f"Cache saved: {len(self.documents)} document fragments", 
                            output_type=OutputType.INFO)
        except Exception as e:
            PrettyOutput.print(f"Failed to save cache: {str(e)}", 
                            output_type=OutputType.ERROR)
            raise

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

    def _get_embedding_batch(self, texts: List[str]) -> np.ndarray:
        """Get the vector representation of the text batch
        
        Args:
            texts: Text list
            
        Returns:
            np.ndarray: Vector representation array
        """
        try:
            embeddings = self.embedding_model.encode(texts, 
                                                normalize_embeddings=True,
                                                show_progress_bar=False,
                                                batch_size=32)  # Use batch processing to improve efficiency
            return np.array(embeddings, dtype=np.float32)
        except Exception as e:
            PrettyOutput.print(f"Failed to get vector representation: {str(e)}", 
                            output_type=OutputType.ERROR)
            return np.zeros((len(texts), self.vector_dim), dtype=np.float32) # type: ignore

    def _process_document_batch(self, documents: List[Document]) -> List[np.ndarray]:
        """Process a batch of documents vectorization
        
        Args:
            documents: Document list
            
        Returns:
            List[np.ndarray]: Vector list
        """
        texts = []
        for doc in documents:
            # Combine document information
            combined_text = f"""
File: {doc.metadata['file_path']}
Content: {doc.content}
"""
            texts.append(combined_text)
            
        return self._get_embedding_batch(texts) # type: ignore

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
        """Build document index"""
        # Get all files
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

        # Process new files and modified files
        new_documents = []
        if files_to_process:
            with tqdm(total=len(files_to_process), desc="Process files") as pbar:
                for file_path in files_to_process:
                    try:
                        docs = self._process_file(file_path)
                        if len(docs) > 0:
                            new_documents.extend(docs)
                    except Exception as e:
                        PrettyOutput.print(f"Failed to process file {file_path}: {str(e)}", 
                                        output_type=OutputType.ERROR)
                    pbar.update(1)

        # Update document list
        self.documents = unchanged_documents + new_documents

        if not self.documents:
            PrettyOutput.print("No documents to process", output_type=OutputType.WARNING)
            return

        # Only vectorize new documents
        if new_documents:
            PrettyOutput.print(f"Start processing {len(new_documents)} new documents", 
                            output_type=OutputType.INFO)
            
            # Use thread pool to process vectorization
            batch_size = 32
            new_vectors = []
            
            with tqdm(total=len(new_documents), desc="Generating vectors") as pbar:
                with ThreadPoolExecutor(max_workers=self.thread_count) as executor:
                    for i in range(0, len(new_documents), batch_size):
                        batch = new_documents[i:i + batch_size]
                        future = executor.submit(self._process_document_batch, batch)
                        batch_vectors = future.result()
                        
                        with self.vector_lock:
                            new_vectors.extend(batch_vectors)
                        
                        pbar.update(len(batch))

            # Merge new and old vectors
            if self.flat_index is not None:
                # Get vectors for unchanged documents
                unchanged_vectors = []
                for doc in unchanged_documents:
                    # Get vectors from existing index
                    doc_idx = next((i for i, d in enumerate(self.documents) 
                                if d.metadata['file_path'] == doc.metadata['file_path']), None)
                    if doc_idx is not None:
                        # Reconstruct vectors from flat index
                        vector = np.zeros((1, self.vector_dim), dtype=np.float32) # type: ignore
                        self.flat_index.reconstruct(doc_idx, vector.ravel())
                        unchanged_vectors.append(vector)
                
                if unchanged_vectors:
                    unchanged_vectors = np.vstack(unchanged_vectors)
                    vectors = np.vstack([unchanged_vectors, np.vstack(new_vectors)])
                else:
                    vectors = np.vstack(new_vectors)
            else:
                vectors = np.vstack(new_vectors)

            # Build index
            self._build_index(vectors)
            # Save cache
            self._save_cache(vectors)
        
        PrettyOutput.print(f"Successfully indexed {len(self.documents)} document fragments (Added/Modified: {len(new_documents)}, Unchanged: {len(unchanged_documents)})", 
                        output_type=OutputType.SUCCESS)

    def search(self, query: str, top_k: int = 30) -> List[Tuple[Document, float]]:
        """Optimize search strategy"""
        if not self.index:
            PrettyOutput.print("Index not built, building...", output_type=OutputType.INFO)
            self.build_index(self.root_dir)
        
        # Implement MMR (Maximal Marginal Relevance) to increase result diversity
        def mmr(query_vec, doc_vecs, doc_ids, lambda_param=0.5, n_docs=top_k):
            selected = []
            selected_ids = []
            
            while len(selected) < n_docs and len(doc_ids) > 0:
                best_score = -1
                best_idx = -1
                
                for i, (doc_vec, doc_id) in enumerate(zip(doc_vecs, doc_ids)):
                    # Calculate similarity with query
                    query_sim = float(np.dot(query_vec, doc_vec))
                    
                    # Calculate maximum similarity with selected documents
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
        
        # Get query vector
        query_vector = self._get_embedding(query)
        query_vector = query_vector.reshape(1, -1)
        
        # Initial search more results for MMR
        initial_k = min(top_k * 2, len(self.documents))
        distances, indices = self.index.search(query_vector, initial_k) # type: ignore
        
        # Get valid results
        valid_indices = indices[0][indices[0] != -1]
        valid_vectors = np.vstack([self._get_embedding(self.documents[idx].content) for idx in valid_indices])
        
        # Apply MMR
        final_indices = mmr(query_vector[0], valid_vectors, valid_indices, n_docs=top_k)
        
        # Build results
        results = []
        for idx in final_indices:
            doc = self.documents[idx]
            similarity = 1.0 / (1.0 + float(distances[0][np.where(indices[0] == idx)[0][0]]))
            results.append((doc, similarity))
        
        return results

    def _rerank_results(self, query: str, initial_results: List[Tuple[Document, float]]) -> List[Tuple[Document, float]]:
        """Use rerank model to rerank search results"""
        try:
            import torch
            model, tokenizer = load_rerank_model()
            
            # Prepare data
            pairs = []
            for doc, _ in initial_results:
                # Combine document information
                doc_content = f"""
File: {doc.metadata['file_path']}
Content: {doc.content}
"""
                pairs.append([query, doc_content])
                
            # Score each document pair
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
            
            # Normalize scores to 0-1 range
            if scores:
                min_score = min(scores)
                max_score = max(scores)
                if max_score > min_score:
                    scores = [(s - min_score) / (max_score - min_score) for s in scores]
            
            # Combine scores with documents and sort
            scored_results = []
            for (doc, _), score in zip(initial_results, scores):
                if score >= 0.5:  # Only keep results with a score greater than 0.5
                    scored_results.append((doc, float(score)))
                    
            # Sort by score in descending order
            scored_results.sort(key=lambda x: x[1], reverse=True)
            
            return scored_results
            
        except Exception as e:
            PrettyOutput.print(f"Failed to rerank, using original sorting: {str(e)}", output_type=OutputType.WARNING)
            return initial_results

    def is_index_built(self):
        """Check if index is built"""
        return self.index is not None

    def query(self, query: str) -> List[Document]:
        """Query related documents
        
        Args:
            query: Query text
            
        Returns:
            List[Document]: Related documents, including context
        """
        results = self.search(query)
        return [doc for doc, _ in results]

    def ask(self, question: str) -> Optional[str]:
        """Ask about documents
        
        Args:
            question: User question
            
        Returns:
            Model answer, return None if failed
        """
        try:
            # Search related document fragments
            results = self.query(question)
            if not results:
                return None
            
            # Display found document fragments
            for doc in results:
                PrettyOutput.print(f"File: {doc.metadata['file_path']}", output_type=OutputType.INFO)
                PrettyOutput.print(f"Fragment {doc.metadata['chunk_index'] + 1}/{doc.metadata['total_chunks']}", 
                                output_type=OutputType.INFO)
                PrettyOutput.print("\nContent:", output_type=OutputType.INFO)
                content = doc.content.encode('utf-8', errors='replace').decode('utf-8')
                PrettyOutput.print(content, output_type=OutputType.INFO)

            # Build base prompt
            base_prompt = f"""Please answer the user's question based on the following document fragments. If the document content is not sufficient to answer the question completely, please clearly indicate.

User question: {question}

Related document fragments:
"""
            end_prompt = "\nPlease provide an accurate and concise answer. If the document content is not sufficient to answer the question completely, please clearly indicate."
            
            # Calculate the maximum length that can be used for document content
            # Leave some space for the model's answer
            available_length = self.max_context_length - len(base_prompt) - len(end_prompt) - 500
            
            # Build context, while controlling the total length
            context = []
            current_length = 0
            
            for doc in results:
                # Calculate the length of this document fragment's content
                doc_content = f"""
Source file: {doc.metadata['file_path']}
Content:
{doc.content}
---
"""
                content_length = len(doc_content)
                
                # If adding this fragment would exceed the limit, stop adding
                if current_length + content_length > available_length:
                    PrettyOutput.print("Due to context length limit, some related document fragments were omitted", 
                                    output_type=OutputType.WARNING)
                    break
                    
                context.append(doc_content)
                current_length += content_length

            # Build complete prompt
            prompt = base_prompt + ''.join(context) + end_prompt
            
            # Get model instance and generate answer
            model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
            response = model.chat_until_success(prompt)
            
            return response
            
        except Exception as e:
            PrettyOutput.print(f"Failed to answer: {str(e)}", output_type=OutputType.ERROR)
            return None

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
                    PrettyOutput.print(f"\nFile: {doc.metadata['file_path']}", output_type=OutputType.INFO)
                    PrettyOutput.print(f"Fragment {doc.metadata['chunk_index'] + 1}/{doc.metadata['total_chunks']}", 
                                    output_type=OutputType.INFO)
                    PrettyOutput.print("\nContent:", output_type=OutputType.INFO)
                    content = doc.content.encode('utf-8', errors='replace').decode('utf-8')
                    PrettyOutput.print(content, output_type=OutputType.INFO)
                return 0

            if args.ask:
                # Call ask method
                response = rag.ask(args.ask)
                if not response:
                    PrettyOutput.print("Failed to get answer", output_type=OutputType.WARNING)
                    return 1
                    
                # Display answer
                PrettyOutput.print("\nAnswer:", output_type=OutputType.INFO)
                PrettyOutput.print(response, output_type=OutputType.INFO)
                return 0

        PrettyOutput.print("Please specify operation parameters. Use -h to view help.", output_type=OutputType.WARNING)
        return 1

    except Exception as e:
        PrettyOutput.print(f"Failed to execute: {str(e)}", output_type=OutputType.ERROR)
        return 1

if __name__ == "__main__":
    main()
