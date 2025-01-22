import hashlib
import os
import sqlite3
import time
import numpy as np
import faiss
from typing import List, Tuple, Optional
from jarvis.models.registry import PlatformRegistry
import concurrent.futures
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from jarvis.utils import OutputType, PrettyOutput, find_git_root
from jarvis.utils import load_env_from_file
import argparse
from sentence_transformers import SentenceTransformer

class CodeBase:
    def __init__(self, root_dir: str, thread_count: int = 10, 
                 model_name: str = "BAAI/bge-large-zh-v1.5",
                 vector_dim: Optional[int] = None):
        load_env_from_file()
        self.root_dir = root_dir
        os.chdir(self.root_dir)
        self.thread_count = thread_count
        self.platform = os.environ.get("JARVIS_CHEAP_PLATFORM") or os.environ.get("JARVIS_PLATFORM")
        self.model = os.environ.get("JARVIS_CHEAP_MODEL") or os.environ.get("JARVIS_MODEL")
        if not self.platform or not self.model:
            raise ValueError("JARVIS_CHEAP_PLATFORM or JARVIS_CHEAP_MODEL is not set")
            
        # 初始化嵌入模型
        self.embedding_model_name = model_name
        self.embedding_model = SentenceTransformer(model_name)
        if vector_dim is None:
            self.vector_dim = self.embedding_model.get_sentence_embedding_dimension()
        else:
            self.vector_dim = vector_dim
            
        self.data_dir = os.path.join(self.root_dir, ".jarvis-codebase")
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        self.db_path = os.path.join(self.data_dir, "codebase.db")
        if not os.path.exists(self.db_path):
            self.create_db()
        self.git_file_list = self.get_git_file_list()
        self.platform_registry = PlatformRegistry().get_global_platform_registry()
        self.index_path = os.path.join(self.data_dir, "vectors.index")
        self.init_vector_index()

    def get_git_file_list(self):
        return os.popen("git ls-files").read().splitlines()

    def get_db_connection(self):
        """创建并返回一个新的数据库连接"""
        return sqlite3.connect(self.db_path)

    def clean_db(self):
        """清理数据库和向量索引中的过期记录"""
        db = self.get_db_connection()
        try:
            # 获取所有数据库记录
            all_records = db.execute("SELECT path FROM codebase").fetchall()
            files_to_delete = []
            
            # 找出需要删除的文件
            for row in all_records:
                if row[0] not in self.git_file_list:
                    files_to_delete.append(row[0])
            
            if not files_to_delete:
                return
                
            # 重新初始化HNSW索引
            self.index = faiss.IndexHNSWFlat(self.vector_dim, 16)
            self.index.hnsw.efConstruction = 40
            self.index.hnsw.efSearch = 16
            
            # 获取保留的记录
            kept_records = []
            for row in all_records:
                if row[0] not in files_to_delete:
                    # 获取文件内容和描述
                    file_info = db.execute("SELECT path, description FROM codebase WHERE path = ?", (row[0],)).fetchone()
                    if file_info:
                        path, description = file_info
                        # 重新生成向量
                        vector = self.vectorize_file(path, description)
                        kept_records.append((path, vector))
            
            # 删除数据库中的记录
            for file_path in files_to_delete:
                db.execute("DELETE FROM codebase WHERE path = ?", (file_path,))
            
            # 重新添加保留的向量到索引
            if kept_records:
                vectors = np.vstack([record[1] for record in kept_records])
                self.index.add(vectors)
            
            # 保存更新后的索引
            faiss.write_index(self.index, self.index_path)
            db.commit()
            
            PrettyOutput.print(f"Cleaned {len(files_to_delete)} files from database and vector index", 
                             output_type=OutputType.INFO)
            
        finally:
            db.close()
        
    def create_db(self):
        db = self.get_db_connection()
        try:
            db.execute("CREATE TABLE IF NOT EXISTS codebase (path TEXT, md5 TEXT ,description TEXT)")
            db.commit()
        finally:
            db.close()

    def is_text_file(self, file_path: str):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                f.read()
                return True
            except UnicodeDecodeError:
                return False

    def make_description(self, file_path: str) -> str:
        model = self.platform_registry.create_platform(self.platform)
        model.set_model_name(self.model)
        model.set_suppress_output(True)
        content = open(file_path, "r", encoding="utf-8").read()
        prompt = f"""
你是一个代码库的描述专家，请根据以下代码内容，生成一个详细的描述，描述该代码库的功能和用途。

代码路径：{file_path}
代码内容：{content}
"""
        response = model.chat(prompt)
        return response

    def init_vector_index(self):
        """初始化HNSW索引"""
        # 使用HNSW索引，M=16（每个节点的最大出边数），ef_construction=40（建图时的搜索范围）
        self.index = faiss.IndexHNSWFlat(self.vector_dim, 16)
        self.index.hnsw.efConstruction = 40
        self.index.hnsw.efSearch = 16
        
        if os.path.exists(self.index_path):
            self.index = faiss.read_index(self.index_path)

    def get_embedding(self, text: str) -> np.ndarray:
        """使用 transformers 模型获取文本的向量表示"""
        # 对长文本进行截断
        max_length = 512  # 或其他合适的长度
        text = ' '.join(text.split()[:max_length])
        
        # 获取嵌入向量
        embedding = self.embedding_model.encode(text, 
                                             normalize_embeddings=True,  # L2归一化
                                             show_progress_bar=False)
        return np.array(embedding, dtype=np.float32)

    def vectorize_file(self, file_path: str, description: str) -> np.ndarray:
        """将文件内容和描述向量化"""
        try:            
            # 组合文件信息
            combined_text = f"""
文件路径: {file_path}
文件描述: {description}
"""
            return self.get_embedding(combined_text)
        except Exception as e:
            PrettyOutput.print(f"Error vectorizing file {file_path}: {str(e)}", 
                             output_type=OutputType.ERROR)
            return np.zeros(self.vector_dim, dtype=np.float32)

    def add_to_vector_index(self, file_path: str, vector: np.ndarray):
        """将向量添加到索引中"""
        vector = vector.reshape(1, -1)  # 调整维度为 (1, dim)
        with Lock():
            self.index.add(vector)
            faiss.write_index(self.index, self.index_path)

    def process_file(self, file):
        """处理单个文件的辅助方法"""
        db = self.get_db_connection()
        try:
            if not self.is_text_file(file):
                return None
            md5 = hashlib.md5(open(file, "rb").read()).hexdigest()
            if db.execute("SELECT path FROM codebase WHERE md5 = ?", (md5,)).fetchone():
                return None
            description = self.make_description(file)
            # 生成向量
            vector = self.vectorize_file(file, description)
            return (file, md5, description, vector)
        finally:
            db.close()

    def generate_codebase(self):
        db_lock = Lock()
        
        def process_and_save(file):
            result = self.process_file(file)
            if result:
                file, md5, description, vector = result
                db = self.get_db_connection()
                try:
                    with db_lock:
                        db.execute("DELETE FROM codebase WHERE path = ?", (file,))
                        db.execute("INSERT INTO codebase (path, md5, description) VALUES (?, ?, ?)", 
                                 (file, md5, description))
                        db.commit()
                        self.add_to_vector_index(file, vector)
                        PrettyOutput.print(f"Processed file: {file}", output_type=OutputType.INFO)
                finally:
                    db.close()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.thread_count) as executor:
            list(executor.map(process_and_save, self.git_file_list))

    def search_similar(self, query: str, top_k: int = 5) -> List[Tuple[str, float, str]]:
        """搜索与查询最相似的文件
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            List of (file_path, similarity_score, description) tuples
        """
        # 获取查询文本的向量表示
        query_vector = self.get_embedding(query)
        query_vector = query_vector.reshape(1, -1)

        # 搜索最相似的向量
        distances, indices = self.index.search(query_vector, top_k)
        
        # 获取对应的文件信息
        db = self.get_db_connection()
        try:
            results = []
            for i, distance in zip(indices[0], distances[0]):
                if i == -1:  # faiss返回-1表示无效结果
                    continue
                    
                # 获取文件路径和描述
                cursor = db.execute("SELECT path, description FROM codebase LIMIT 1 OFFSET ?", (i,))
                row = cursor.fetchone()
                if row:
                    path, description = row
                    # 将distance转换为相似度分数（0-1之间）
                    similarity = 1.0 / (1.0 + distance)
                    results.append((path, similarity, description))
            
            return results
        finally:
            db.close()

def main():
    parser = argparse.ArgumentParser(description='Codebase management and search tool')
    parser.add_argument('--search', type=str, help='Search query to find similar code files')
    parser.add_argument('--top-k', type=int, default=5, help='Number of results to return (default: 5)')
    parser.add_argument('--generate', action='store_true', help='Generate or update the codebase index')
    parser.add_argument('--model', type=str, default=os.environ.get("JARVIS_EMBEDDING_MODEL") or "BAAI/bge-large-zh-v1.5",
                       help='Embedding model name (default: BAAI/bge-large-zh-v1.5)')
    args = parser.parse_args()
    
    current_dir = find_git_root()
    codebase = CodeBase(current_dir, model_name=args.model)
    
    if args.generate:
        codebase.generate_codebase()
        PrettyOutput.print("Codebase generation completed", output_type=OutputType.SUCCESS)
    
    if args.search:
        results = codebase.search_similar(args.search, args.top_k)
        if not results:
            PrettyOutput.print("No similar files found", output_type=OutputType.WARNING)
            return
            
        PrettyOutput.print("\nSearch Results:", output_type=OutputType.INFO)
        for path, score, desc in results:
            PrettyOutput.print("\n" + "="*50, output_type=OutputType.INFO)
            PrettyOutput.print(f"File: {path}", output_type=OutputType.INFO)
            PrettyOutput.print(f"Similarity: {score:.3f}", output_type=OutputType.INFO)
            PrettyOutput.print(f"Description: {desc}", output_type=OutputType.INFO)
    
    if not args.generate and not args.search:
        parser.print_help()


if __name__ == "__main__":
    exit(main())