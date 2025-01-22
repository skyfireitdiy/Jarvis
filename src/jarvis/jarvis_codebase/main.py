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
    def __init__(self, root_dir: str, thread_count: int = 10):
        load_env_from_file()
        self.root_dir = root_dir
        os.chdir(self.root_dir)
        self.thread_count = thread_count
        self.cheap_platform = os.environ.get("JARVIS_CHEAP_PLATFORM") or os.environ.get("JARVIS_PLATFORM") or "kimi"
        self.cheap_model = os.environ.get("JARVIS_CHEAP_MODEL") or os.environ.get("JARVIS_MODEL") or "kimi"
        self.normal_platform = os.environ.get("JARVIS_PLATFORM") or "kimi"
        self.normal_model = os.environ.get("JARVIS_MODEL") or "kimi"
        self.embedding_model_name = os.environ.get("JARVIS_EMBEDDING_MODEL") or "BAAI/bge-large-zh-v1.5"
        if not self.cheap_platform or not self.cheap_model or not self.embedding_model_name or not self.normal_platform or not self.normal_model:
            raise ValueError("JARVIS_CHEAP_PLATFORM or JARVIS_CHEAP_MODEL or JARVIS_EMBEDDING_MODEL or JARVIS_PLATFORM or JARVIS_MODEL is not set")
        
        PrettyOutput.print(f"廉价模型使用平台: {self.cheap_platform} 模型: {self.cheap_model}", output_type=OutputType.INFO)
        PrettyOutput.print(f"分析模型使用平台: {self.normal_platform} 模型: {self.normal_model}", output_type=OutputType.INFO)
        PrettyOutput.print(f"嵌入模型: {self.embedding_model_name}", output_type=OutputType.INFO)
        PrettyOutput.print(f"检索算法：分层导航小世界算法", output_type=OutputType.INFO)
            
        # 初始化数据目录
        self.data_dir = os.path.join(self.root_dir, ".jarvis-codebase")
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            
        # 初始化嵌入模型，使用系统默认缓存目录
        try:
            PrettyOutput.print("正在加载/下载模型，请稍候...", output_type=OutputType.INFO)
            self.embedding_model = SentenceTransformer(self.embedding_model_name)
            
            # 强制完全加载所有模型组件
            test_text = """
这是一段测试文本，用于确保模型完全加载。
包含多行内容，以模拟实际使用场景。
"""
            # 预热模型，确保所有组件都被加载
            self.embedding_model.encode([test_text], 
                                     convert_to_tensor=True,
                                     normalize_embeddings=True)
            PrettyOutput.print("模型加载完成", output_type=OutputType.SUCCESS)
        except Exception as e:
            PrettyOutput.print(f"加载模型失败: {str(e)}", output_type=OutputType.ERROR)
            raise
            
        self.vector_dim = self.embedding_model.get_sentence_embedding_dimension()

            
        self.db_path = os.path.join(self.data_dir, "codebase.db")
        if not os.path.exists(self.db_path):
            self.create_db()
        self.git_file_list = self.get_git_file_list()
        self.platform_registry = PlatformRegistry().get_global_platform_registry()
        self.index_path = os.path.join(self.data_dir, "vectors.index")
        self.index = None
        if  os.path.exists(self.index_path):
            PrettyOutput.print("正在加载向量数据库", output_type=OutputType.INFO)
            self.index = faiss.read_index(self.index_path)

    def get_git_file_list(self):
        return os.popen("git ls-files").read().splitlines()

    def get_db_connection(self):
        """创建并返回一个新的数据库连接"""
        return sqlite3.connect(self.db_path)

    def clean_db(self) -> bool:
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
                return False
                
            for file_path in files_to_delete:
                db.execute("DELETE FROM codebase WHERE path = ?", (file_path,))
            
            db.commit()
            
            PrettyOutput.print(f"清理了 {len(files_to_delete)} 个文件的记录", 
                             output_type=OutputType.INFO)
            return True
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
        model = self.platform_registry.create_platform(self.cheap_platform)
        model.set_model_name(self.cheap_model)
        model.set_suppress_output(True)
        content = open(file_path, "r", encoding="utf-8").read()
        prompt = f"""请分析以下代码文件，并生成一个详细的描述。描述应该包含以下要点：

1. 主要功能和用途
2. 关键类和方法的作用
3. 重要的依赖和技术特征（如使用了什么框架、算法、设计模式等）
4. 代码处理的主要数据类型和数据结构
5. 关键业务逻辑和处理流程
6. 特殊功能点和亮点特性

请用简洁专业的语言描述，突出代码的技术特征和功能特点，以便后续进行相似代码检索。

文件路径：{file_path}
代码内容：
{content}
"""
        response = model.chat(prompt)
        return response

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
            return (file, md5, description)
        finally:
            db.close()

    def gen_vector_db_from_sqlite(self):
        self.index = faiss.IndexHNSWFlat(self.vector_dim, 16)
        self.index.hnsw.efConstruction = 40
        self.index.hnsw.efSearch = 16
        db = self.get_db_connection()
        try:
            all_records = db.execute("SELECT path, description FROM codebase").fetchall()
            for row in all_records:
                file, description = row
                PrettyOutput.print(f"正在向量化文件: {file}", output_type=OutputType.INFO)
                vector = self.vectorize_file(file, description)
                vector = vector.reshape(1, -1)  
                self.index.add(vector)
            faiss.write_index(self.index, self.index_path)
        finally:
            db.close()

    def generate_codebase(self):
        updated =self.clean_db()
        db_lock = Lock()
        processed_files = []  # 用于跟踪已处理的文件
        
        def process_and_save(file):
            result = self.process_file(file)
            if result:
                file, md5, description = result
                db = self.get_db_connection()
                try:
                    with db_lock:
                        db.execute("DELETE FROM codebase WHERE path = ?", (file,))
                        db.execute("INSERT INTO codebase (path, md5, description) VALUES (?, ?, ?)", 
                                 (file, md5, description))
                        db.commit()
                        PrettyOutput.print(f"索引文件: {file}", output_type=OutputType.INFO)
                        processed_files.append(file)
                finally:
                    db.close()
        
        # 使用 ThreadPoolExecutor 并等待所有任务完成
        with ThreadPoolExecutor(max_workers=self.thread_count) as executor:
            futures = [executor.submit(process_and_save, file) for file in self.git_file_list]
            # 等待所有任务完成
            concurrent.futures.wait(futures)

        if updated or len(processed_files) > 0:
            PrettyOutput.print("有新的文件被删除或添加，正在重新生成向量数据库", output_type=OutputType.INFO)
            self.gen_vector_db_from_sqlite()
        else:
            PrettyOutput.print("没有新的文件被删除或添加，跳过向量数据库生成", output_type=OutputType.INFO)
            
        PrettyOutput.print(f"成功索引 {len(processed_files)} 个文件", output_type=OutputType.INFO)

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
                    
                # 将numpy.int64转换为Python int
                offset = int(i)
                # 获取文件路径和描述
                cursor = db.execute("SELECT path, description FROM codebase LIMIT 1 OFFSET ?", (offset,))
                row = cursor.fetchone()
                if row:
                    path, description = row
                    # 将distance转换为相似度分数（0-1之间）
                    similarity = 1.0 / (1.0 + float(distance))  # 确保使用Python float
                    results.append((path, similarity, description))
            
            return results
        finally:
            db.close()

    def ask_codebase(self, query: str, top_k: int = 5) -> List[Tuple[str, float, str]]:
        """Ask a question about the codebase"""
        # 使用搜索函数获取相似文件
        results = self.search_similar(query, top_k)
        PrettyOutput.print(f"找到的关联文件: ", output_type=OutputType.INFO)
        for path, score, _ in results:
            PrettyOutput.print(f"文件: {path} 关联度: {score:.3f}", output_type=OutputType.INFO)
        
        prompt = f"""你是一个代码专家，请根据以下文件信息回答用户的问题：
"""
        for path, _, _ in results:
            content = open(path, "r", encoding="utf-8").read()
            prompt += f"""
文件路径: {path}
文件内容:
{content}
========================================
"""
        prompt += f"""
用户问题: {query}

请用专业的语言回答用户的问题，如果给出的文件内容不足以回答用户的问题，请告诉用户，绝对不要胡编乱造。
"""
        model = self.platform_registry.create_platform(self.normal_platform)
        model.set_model_name(self.normal_model)
        response = model.chat(prompt)
        return response


def main():
    parser = argparse.ArgumentParser(description='Codebase management and search tool')
    parser.add_argument('--search', type=str, help='Search query to find similar code files')
    parser.add_argument('--top-k', type=int, default=5, help='Number of results to return (default: 5)')
    parser.add_argument('--ask', type=str, help='Ask a question about the codebase')
    args = parser.parse_args()
    
    current_dir = find_git_root()
    codebase = CodeBase(current_dir)

    try:
        codebase.generate_codebase()
        PrettyOutput.print("\nCodebase generation completed", output_type=OutputType.SUCCESS)
    except Exception as e:
        PrettyOutput.print(f"Error during codebase generation: {str(e)}", output_type=OutputType.ERROR)
    
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
            PrettyOutput.print(f"Description: {desc[100:]}", output_type=OutputType.INFO)

    if args.ask:            
        codebase.ask_codebase(args.ask, args.top_k)


if __name__ == "__main__":
    exit(main())