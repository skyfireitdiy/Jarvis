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
import pickle

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

        self.git_file_list = self.get_git_file_list()
        self.platform_registry = PlatformRegistry().get_global_platform_registry()
        
        # 初始化向量索引
        self.index_path = os.path.join(self.data_dir, "vectors.index")
        self.index = None
        self.file_paths = []
        if os.path.exists(self.index_path):
            PrettyOutput.print("正在加载向量数据库", output_type=OutputType.INFO)
            self.index = faiss.read_index(self.index_path)
            try:
                with open(os.path.join(self.data_dir, "file_paths.pkl"), "rb") as f:
                    self.file_paths = pickle.load(f)
            except Exception as e:
                PrettyOutput.print(f"加载文件路径列表失败: {str(e)}", 
                                 output_type=OutputType.WARNING)
                self.file_paths = []

        # 初始化向量缓存
        self.vector_cache_path = os.path.join(self.data_dir, "vector_cache.pkl")
        self.vector_cache = {}
        if os.path.exists(self.vector_cache_path):
            try:
                with open(self.vector_cache_path, 'rb') as f:
                    self.vector_cache = pickle.load(f)
                PrettyOutput.print(f"加载了 {len(self.vector_cache)} 个向量缓存", 
                                 output_type=OutputType.INFO)
            except Exception as e:
                PrettyOutput.print(f"加载向量缓存失败: {str(e)}", 
                                 output_type=OutputType.WARNING)
                self.vector_cache = {}

    def get_git_file_list(self):
        """获取 git 仓库中的文件列表，排除 .jarvis-codebase 目录"""
        files = os.popen("git ls-files").read().splitlines()
        # 过滤掉 .jarvis-codebase 目录下的文件
        return [f for f in files if not f.startswith(".jarvis-codebase/")]

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

    def save_vector_cache(self):
        """保存向量缓存到文件"""
        try:
            with open(self.vector_cache_path, 'wb') as f:
                pickle.dump(self.vector_cache, f)
            PrettyOutput.print(f"保存了 {len(self.vector_cache)} 个向量缓存", output_type=OutputType.INFO)
        except Exception as e:
            PrettyOutput.print(f"保存向量缓存失败: {str(e)}", output_type=OutputType.ERROR)

    def get_cached_vector(self, file_path: str, description: str = None) -> Optional[np.ndarray]:
        """从缓存中获取向量
        
        Args:
            file_path: 文件路径
            description: 文件描述，如果提供则同时检查描述是否匹配
        """
        if file_path not in self.vector_cache:
            return None
            
        cached_data = self.vector_cache[file_path]
        if description is not None and cached_data["description"] != description:
            return None
            
        return cached_data["vector"]

    def cache_vector(self, file_path: str, vector: np.ndarray, description: str = None):
        """将向量保存到缓存
        
        Args:
            file_path: 文件路径
            vector: 向量数据
            description: 文件描述，用于检查文件内容是否变化
        """
        self.vector_cache[file_path] = {
            "vector": vector,
            "description": description
        }

    def get_embedding(self, text: str) -> np.ndarray:
        """使用 transformers 模型获取文本的向量表示"""
        # 先尝试从缓存获取
        cached_vector = self.get_cached_vector(text)
        if cached_vector is not None:
            return cached_vector

        # 对长文本进行截断
        max_length = 512  # 或其他合适的长度
        text = ' '.join(text.split()[:max_length])
        
        # 获取嵌入向量
        embedding = self.embedding_model.encode(text, 
                                             normalize_embeddings=True,  # L2归一化
                                             show_progress_bar=False)
        vector = np.array(embedding, dtype=np.float32)
        
        # 保存到缓存
        self.cache_vector(text, vector)
        return vector

    def vectorize_file(self, file_path: str, description: str) -> np.ndarray:
        """将文件内容和描述向量化"""
        try:
            # 先尝试从缓存获取
            cached_vector = self.get_cached_vector(file_path, description)
            if cached_vector is not None:
                return cached_vector
                
            # 组合文件信息
            combined_text = f"""
文件路径: {file_path}
文件描述: {description}
"""
            vector = self.get_embedding(combined_text)
            
            # 保存到缓存，使用实际文件路径作为键
            self.cache_vector(file_path, vector, description)
            return vector
        except Exception as e:
            PrettyOutput.print(f"Error vectorizing file {file_path}: {str(e)}", 
                             output_type=OutputType.ERROR)
            return np.zeros(self.vector_dim, dtype=np.float32)

    def clean_cache(self) -> bool:
        """清理过期的缓存记录"""
        files_to_delete = []
        for file_path in list(self.vector_cache.keys()):
            if file_path not in self.git_file_list:
                del self.vector_cache[file_path]
                files_to_delete.append(file_path)
        
        if files_to_delete:
            self.save_vector_cache()
            PrettyOutput.print(f"清理了 {len(files_to_delete)} 个文件的缓存", 
                             output_type=OutputType.INFO)
            return True
        return False

    def process_file(self, file_path: str):
        """处理单个文件"""
        try:
            # 跳过不存在的文件
            if not os.path.exists(file_path):
                return None
                
            if not self.is_text_file(file_path):
                return None
                
            md5 = hashlib.md5(open(file_path, "rb").read()).hexdigest()
            
            # 检查文件是否已经处理过且内容未变
            if file_path in self.vector_cache:
                if self.vector_cache[file_path].get("md5") == md5:
                    return None
                    
            description = self.make_description(file_path)
            vector = self.vectorize_file(file_path, description)
            
            # 保存到缓存，使用实际文件路径作为键
            self.vector_cache[file_path] = {
                "vector": vector,
                "description": description,
                "md5": md5
            }
            
            return file_path
            
        except Exception as e:
            PrettyOutput.print(f"处理文件失败 {file_path}: {str(e)}", 
                             output_type=OutputType.ERROR,
                             traceback=True)
            return None

    def generate_codebase(self):
        """生成代码库索引"""
        self.clean_cache()  # 清理过期缓存
        processed_files = []
        
        # 使用线程池处理文件
        with ThreadPoolExecutor(max_workers=self.thread_count) as executor:
            futures = [executor.submit(self.process_file, file) for file in self.git_file_list]
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    processed_files.append(result)
                    PrettyOutput.print(f"索引文件: {result}", output_type=OutputType.INFO)

        if processed_files:
            PrettyOutput.print("重新生成向量数据库", output_type=OutputType.INFO)
            self.gen_vector_db_from_cache()
            self.save_vector_cache()
        else:
            PrettyOutput.print("没有新的文件变更，跳过向量数据库生成", output_type=OutputType.INFO)
            
        PrettyOutput.print(f"成功索引 {len(processed_files)} 个文件", output_type=OutputType.INFO)

    def gen_vector_db_from_cache(self):
        """从缓存生成向量数据库"""
        self.index = faiss.IndexHNSWFlat(self.vector_dim, 16)
        self.index.hnsw.efConstruction = 40
        self.index.hnsw.efSearch = 16
        
        vectors = []
        self.file_paths = []  # 存储文件路径列表，与向量顺序对应
        
        for file_path, data in self.vector_cache.items():
            vectors.append(data["vector"].reshape(1, -1))
            # 使用实际文件路径
            self.file_paths.append(file_path)
            
        if vectors:
            vectors = np.vstack(vectors)
            self.index.add(vectors)
            faiss.write_index(self.index, self.index_path)
            # 保存文件路径列表
            with open(os.path.join(self.data_dir, "file_paths.pkl"), "wb") as f:
                pickle.dump(self.file_paths, f)

    def search_similar(self, query: str, top_k: int = 5) -> List[Tuple[str, float, str]]:
        """搜索相似文件"""
        query_vector = self.get_embedding(query)
        query_vector = query_vector.reshape(1, -1)
        
        distances, indices = self.index.search(query_vector, top_k)
        
        results = []
        for i, distance in zip(indices[0], distances[0]):
            if i == -1:  # faiss返回-1表示无效结果
                continue
                
            file_path = self.file_paths[i]
            data = self.vector_cache[file_path]
            similarity = 1.0 / (1.0 + float(distance))
            results.append((file_path, similarity, data["description"]))
        
        return results

    def ask_codebase(self, query: str, top_k: int = 5) -> List[Tuple[str, float, str]]:
        """查询代码库"""
        results = self.search_similar(query, top_k)
        PrettyOutput.print(f"找到的关联文件: ", output_type=OutputType.INFO)
        for path, score, _ in results:
            PrettyOutput.print(f"文件: {path} 关联度: {score:.3f}", 
                             output_type=OutputType.INFO)
        
        prompt = f"""你是一个代码专家，请根据以下文件信息回答用户的问题：
"""
        for path, _, _ in results:
            try:
                content = open(path, "r", encoding="utf-8").read()
                prompt += f"""
文件路径: {path}
文件内容:
{content}
========================================
"""
            except Exception as e:
                PrettyOutput.print(f"读取文件失败 {path}: {str(e)}", 
                                 output_type=OutputType.ERROR)
                continue
                
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