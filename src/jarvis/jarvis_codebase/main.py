import hashlib
import os
import numpy as np
import faiss
from typing import List, Tuple, Optional
from jarvis.models.registry import PlatformRegistry
import concurrent.futures
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from jarvis.utils import OutputType, PrettyOutput, find_git_root, get_max_context_length, get_thread_count, load_embedding_model, load_rerank_model
from jarvis.utils import load_env_from_file
import argparse
from sentence_transformers import SentenceTransformer
import pickle

class CodeBase:
    def __init__(self, root_dir: str):
        load_env_from_file()
        self.root_dir = root_dir
        os.chdir(self.root_dir)
        self.thread_count = get_thread_count()
        self.max_context_length = get_max_context_length()
        self.index = None
            
        # 初始化数据目录
        self.data_dir = os.path.join(self.root_dir, ".jarvis-codebase")
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            
        # 初始化嵌入模型，使用系统默认缓存目录
        try:
            self.embedding_model = load_embedding_model()
            
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
        self.platform_registry = PlatformRegistry.get_global_platform_registry()
        
        # 初始化缓存和索引
        self.cache_path = os.path.join(self.data_dir, "cache.pkl")
        self.vector_cache = {}
        self.file_paths = []
        
        # 加载缓存
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, 'rb') as f:
                    cache_data = pickle.load(f)
                    self.vector_cache = cache_data["vectors"]
                    self.file_paths = cache_data["file_paths"]
                PrettyOutput.print(f"加载了 {len(self.vector_cache)} 个向量缓存", 
                                 output_type=OutputType.INFO)
                # 从缓存重建索引
                self.build_index()
            except Exception as e:
                PrettyOutput.print(f"加载缓存失败: {str(e)}", 
                                 output_type=OutputType.WARNING)
                self.vector_cache = {}
                self.file_paths = []
                self.index = None

    def get_git_file_list(self):
        """获取 git 仓库中的文件列表，排除 .jarvis-codebase 目录"""
        files = os.popen("git ls-files").read().splitlines()
        # 过滤掉 .jarvis-codebase 目录下的文件
        return [f for f in files if not f.startswith(".jarvis-")]

    def is_text_file(self, file_path: str):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                f.read()
                return True
            except UnicodeDecodeError:
                return False

    def make_description(self, file_path: str, content: str) -> str:
        model = PlatformRegistry.get_global_platform_registry().get_codegen_platform()
        model.set_suppress_output(True)
        prompt = f"""请分析以下代码文件，并生成一个详细的描述。描述应该包含以下要点：

1. 主要功能和用途
2. 关键类和方法的作用
3. 重要的依赖和技术特征（如使用了什么框架、算法、设计模式等）
4. 代码处理的主要数据类型和数据结构
5. 关键业务逻辑和处理流程
6. 特殊功能点和亮点特性

请用简洁专业的语言描述，突出代码的技术特征和功能特点，以便后续进行关联代码检索。

文件路径：{file_path}
代码内容：
{content}
"""
        response = model.chat(prompt)
        return response

    def save_cache(self):
        """保存缓存数据"""
        try:
            cache_data = {
                "vectors": self.vector_cache,
                "file_paths": self.file_paths
            }
            with open(self.cache_path, 'wb') as f:
                pickle.dump(cache_data, f)
            PrettyOutput.print(f"保存了 {len(self.vector_cache)} 个向量缓存", 
                             output_type=OutputType.INFO)
        except Exception as e:
            PrettyOutput.print(f"保存缓存失败: {str(e)}", 
                             output_type=OutputType.ERROR)

    def get_cached_vector(self, file_path: str, description: str) -> Optional[np.ndarray]:
        """从缓存获取文件的向量表示"""
        if file_path not in self.vector_cache:
            return None
        
        # 检查文件是否被修改
        try:
            with open(file_path, "rb") as f:
                current_md5 = hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            PrettyOutput.print(f"计算文件MD5失败 {file_path}: {str(e)}", 
                              output_type=OutputType.ERROR)
            return None
        
        cached_data = self.vector_cache[file_path]
        if cached_data["md5"] != current_md5:
            return None
        
        # 检查描述是否变化
        if cached_data["description"] != description:
            return None
        
        return cached_data["vector"]

    def cache_vector(self, file_path: str, vector: np.ndarray, description: str):
        """缓存文件的向量表示"""
        try:
            with open(file_path, "rb") as f:
                file_md5 = hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            PrettyOutput.print(f"计算文件MD5失败 {file_path}: {str(e)}", 
                              output_type=OutputType.ERROR)
            file_md5 = ""
        
        self.vector_cache[file_path] = {
            "path": file_path,  # 保存文件路径
            "md5": file_md5,    # 保存文件MD5
            "description": description,  # 保存文件描述
            "vector": vector    # 保存向量
        }
        
        # 保存缓存到文件
        try:
            with open(self.cache_path, 'wb') as f:
                cache_data = {
                    "vectors": self.vector_cache,
                    "file_paths": self.file_paths
                }
                pickle.dump(cache_data, f)
        except Exception as e:
            PrettyOutput.print(f"保存向量缓存失败: {str(e)}", 
                              output_type=OutputType.ERROR)

    def get_embedding(self, text: str) -> np.ndarray:
        """使用 transformers 模型获取文本的向量表示"""
        # 对长文本进行截断
        max_length = 512  # 或其他合适的长度
        text = ' '.join(text.split()[:max_length])
        
        # 获取嵌入向量
        embedding = self.embedding_model.encode(text, 
                                                 normalize_embeddings=True,  # L2归一化
                                                 show_progress_bar=False)
        vector = np.array(embedding, dtype=np.float32)
        return vector

    def vectorize_file(self, file_path: str, description: str) -> np.ndarray:
        """将文件内容和描述向量化"""
        try:
            # 先尝试从缓存获取
            cached_vector = self.get_cached_vector(file_path, description)
            if cached_vector is not None:
                return cached_vector
                
            # 读取文件内容并组合信息
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()[:self.max_context_length]  # 限制文件内容长度
            
            # 组合文件信息，包含文件内容
            combined_text = f"""
文件路径: {file_path}
文件描述: {description}
文件内容: {content}
"""
            vector = self.get_embedding(combined_text)
            
            # 保存到缓存
            self.cache_vector(file_path, vector, description)
            return vector
        except Exception as e:
            PrettyOutput.print(f"Error vectorizing file {file_path}: {str(e)}", 
                             output_type=OutputType.ERROR)
            return np.zeros(self.vector_dim, dtype=np.float32)

    def clean_cache(self) -> bool:
        """清理过期的缓存记录，返回是否有文件被删除"""
        files_to_delete = []
        for file_path in list(self.vector_cache.keys()):
            if file_path not in self.git_file_list:
                del self.vector_cache[file_path]
                files_to_delete.append(file_path)
        
        if files_to_delete:
            self.save_cache()
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
                
            # 读取文件内容，限制长度
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                if len(content) > self.max_context_length:
                    PrettyOutput.print(f"文件 {file_path} 内容超出长度限制，将截取前 {self.max_context_length} 个字符", 
                                     output_type=OutputType.WARNING)
                    content = content[:self.max_context_length]
            
            md5 = hashlib.md5(content.encode('utf-8')).hexdigest()
            
            # 检查文件是否已经处理过且内容未变
            if file_path in self.vector_cache:
                if self.vector_cache[file_path].get("md5") == md5:
                    return None
                    
            description = self.make_description(file_path, content)  # 传入截取后的内容
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
                             output_type=OutputType.ERROR)
            return None

    def build_index(self):
        """从向量缓存构建 faiss 索引"""
        # 创建底层 HNSW 索引
        hnsw_index = faiss.IndexHNSWFlat(self.vector_dim, 16)
        hnsw_index.hnsw.efConstruction = 40
        hnsw_index.hnsw.efSearch = 16
        
        # 用 IndexIDMap 包装 HNSW 索引
        self.index = faiss.IndexIDMap(hnsw_index)
        
        vectors = []
        ids = []
        self.file_paths = []  # 重置文件路径列表
        
        for i, (file_path, data) in enumerate(self.vector_cache.items()):
            vectors.append(data["vector"].reshape(1, -1))
            ids.append(i)
            self.file_paths.append(file_path)
            
        if vectors:
            vectors = np.vstack(vectors)
            self.index.add_with_ids(vectors, np.array(ids))
        else:
            self.index = None

    def gen_vector_db_from_cache(self):
        """从缓存生成向量数据库"""
        self.build_index()
        self.save_cache()


    def generate_codebase(self, force: bool = False):
        """生成代码库索引
        Args:
            force: 是否强制重建索引，不询问用户
        """
        # 更新 git 文件列表
        self.git_file_list = self.get_git_file_list()
        
        # 检查文件变化
        changes_detected = False
        new_files = []
        modified_files = []
        deleted_files = []
        
        # 检查删除的文件
        files_to_delete = []
        for file_path in list(self.vector_cache.keys()):
            if file_path not in self.git_file_list:
                deleted_files.append(file_path)
                files_to_delete.append(file_path)
                changes_detected = True
        
        # 检查新增和修改的文件
        for file_path in self.git_file_list:
            if not os.path.exists(file_path) or not self.is_text_file(file_path):
                continue
            
            try:
                current_md5 = hashlib.md5(open(file_path, "rb").read()).hexdigest()
                
                if file_path not in self.vector_cache:
                    new_files.append(file_path)
                    changes_detected = True
                elif self.vector_cache[file_path].get("md5") != current_md5:
                    modified_files.append(file_path)
                    changes_detected = True
            except Exception as e:
                PrettyOutput.print(f"检查文件失败 {file_path}: {str(e)}", 
                                 output_type=OutputType.ERROR)
                continue
        
        # 如果检测到变化，显示变化并询问用户
        if changes_detected:
            PrettyOutput.print("\n检测到以下变化:", output_type=OutputType.WARNING)
            if new_files:
                PrettyOutput.print("\n新增文件:", output_type=OutputType.INFO)
                for f in new_files:
                    PrettyOutput.print(f"  {f}", output_type=OutputType.INFO)
            if modified_files:
                PrettyOutput.print("\n修改的文件:", output_type=OutputType.INFO)
                for f in modified_files:
                    PrettyOutput.print(f"  {f}", output_type=OutputType.INFO)
            if deleted_files:
                PrettyOutput.print("\n删除的文件:", output_type=OutputType.INFO)
                for f in deleted_files:
                    PrettyOutput.print(f"  {f}", output_type=OutputType.INFO)
            

            # 如果force为True，直接继续
            if not force:
                # 询问用户是否继续
                while True:
                    response = input("\n是否重建索引？[y/N] ").lower().strip()
                    if response in ['y', 'yes']:
                        break
                    elif response in ['', 'n', 'no']:
                        PrettyOutput.print("取消重建索引", output_type=OutputType.INFO)
                        return
                    else:
                        PrettyOutput.print("请输入 y 或 n", output_type=OutputType.WARNING)
            
            # 清理已删除的文件
            for file_path in files_to_delete:
                del self.vector_cache[file_path]
            if files_to_delete:
                PrettyOutput.print(f"清理了 {len(files_to_delete)} 个文件的缓存", 
                                 output_type=OutputType.INFO)
            
            # 处理新文件和修改的文件
            processed_files = []
            files_to_process = new_files + modified_files
            
            # 使用线程池处理文件
            with ThreadPoolExecutor(max_workers=self.thread_count) as executor:
                futures = [executor.submit(self.process_file, file) for file in files_to_process]
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        processed_files.append(result)
                        PrettyOutput.print(f"索引文件: {result}", output_type=OutputType.INFO)

            PrettyOutput.print("重新生成向量数据库", output_type=OutputType.INFO)
            self.gen_vector_db_from_cache()
            PrettyOutput.print(f"成功为 {len(processed_files)} 个文件生成索引", output_type=OutputType.INFO)
        else:
            PrettyOutput.print("没有检测到文件变更，无需重建索引", output_type=OutputType.INFO)

    def rerank_results(self, query: str, initial_results: List[Tuple[str, float, str]]) -> List[Tuple[str, float, str]]:
        """使用 BAAI/bge-reranker-v2-m3 对搜索结果重新排序"""
        if not initial_results:
            return []
            
        try:
            import torch
            
            # 加载模型和分词器
            model, tokenizer = load_rerank_model()
            
            # 准备数据 - 加入文件内容进行更准确的重排序
            pairs = []
            for path, _, desc in initial_results:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()[:512]  # 限制内容长度
                    # 组合文件路径、描述和内容
                    doc_content = f"文件: {path}\n描述: {desc}\n内容: {content}"
                    pairs.append([query, doc_content])
                except Exception as e:
                    PrettyOutput.print(f"读取文件失败 {path}: {str(e)}", 
                                    output_type=OutputType.ERROR)
                    doc_content = f"文件: {path}\n描述: {desc}"
                    pairs.append([query, doc_content])
            
            # 使用更大的batch size提高处理速度
            batch_size = 16  # 根据GPU显存调整
            
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
                    # 修改这里：直接使用 outputs.logits 作为分数
                    batch_scores = outputs.logits.squeeze(-1).cpu().numpy()
            
            # 归一化分数到 0-1 范围
            if batch_scores:
                min_score = min(batch_scores)
                max_score = max(batch_scores)
                if max_score > min_score:
                    batch_scores = [(s - min_score) / (max_score - min_score) for s in batch_scores]
            
            # 将分数与原始结果组合并排序
            scored_results = []
            for (path, _, desc), score in zip(initial_results, batch_scores):
                if score >= 0.5:  # 只保留相关度大于 0.5 的结果
                    scored_results.append((path, float(score), desc))
                    
            # 按分数降序排序
            scored_results.sort(key=lambda x: x[1], reverse=True)
            
            return scored_results
            
        except Exception as e:
            PrettyOutput.print(f"重排序失败，使用原始排序: {str(e)}", output_type=OutputType.WARNING)
            return initial_results

    def search_similar(self, query: str, top_k: int = 30) -> List[Tuple[str, float, str]]:
        """搜索关联文件"""
        try:
            if self.index is None:
                return []
            # 生成多个查询变体以提高召回率
            model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
            prompt = f"""请根据以下查询，生成3个不同的表述，每个表述都要完整表达原始查询的意思。这些表述将用于代码搜索，要保持专业性和准确性。
原始查询: {query}

请直接输出3个表述，用换行分隔，不要有编号或其他标记。
"""
            query_variants = model.chat(prompt).strip().split('\n')
            query_variants.append(query)  # 添加原始查询
            
            # 对每个查询变体进行搜索
            all_results = {}
            for q in query_variants:
                q_vector = self.get_embedding(q)
                q_vector = q_vector.reshape(1, -1)
                
                distances, indices = self.index.search(q_vector, top_k)
                
                for i, distance in zip(indices[0], distances[0]):
                    if i == -1:
                        continue
                        
                    similarity = 1.0 / (1.0 + float(distance))
                    if similarity >= 0.5:
                        file_path = self.file_paths[i]
                        # 使用最高的相似度分数
                        if file_path not in all_results or similarity > all_results[file_path][1]:
                            data = self.vector_cache[file_path]
                            all_results[file_path] = (file_path, similarity, data["description"])
            
            # 转换为列表并排序
            results = list(all_results.values())
            results.sort(key=lambda x: x[1], reverse=True)
            
            return results[:top_k]
            
        except Exception as e:
            PrettyOutput.print(f"搜索失败: {str(e)}", output_type=OutputType.ERROR)
            return []

    def ask_codebase(self, query: str, top_k: int=20) -> str:
        """查询代码库"""
        results = self.search_similar(query, top_k)
        if not results:
            PrettyOutput.print("没有找到关联的文件", output_type=OutputType.WARNING)
            return ""
        
        PrettyOutput.print(f"找到的关联文件: ", output_type=OutputType.SUCCESS)
        for path, score, _ in results:
            PrettyOutput.print(f"文件: {path} 关联度: {score:.3f}", 
                             output_type=OutputType.INFO)
        
        prompt = f"""你是一个代码专家，请根据以下文件信息回答用户的问题：
"""
        for path, _, _ in results:
            try:
                if len(prompt) > self.max_context_length:
                    PrettyOutput.print(f"避免上下文超限，丢弃低相关度文件：{path}", OutputType.WARNING)
                    continue
                content = open(path, "r", encoding="utf-8").read()
                prompt += f"""
文件路径: {path}prompt
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
        model = PlatformRegistry.get_global_platform_registry().get_codegen_platform()
        response = model.chat(prompt)
        return response

    def is_index_generated(self) -> bool:
        """检查索引是否已经生成"""
        # 检查缓存文件是否存在
        if not os.path.exists(self.cache_path):
            return False
        
        # 检查缓存是否有效
        try:
            with open(self.cache_path, 'rb') as f:
                cache_data = pickle.load(f)
                if not cache_data.get("vectors") or not cache_data.get("file_paths"):
                    return False
        except Exception:
            return False
        
        # 检查索引是否已构建
        if not hasattr(self, 'index') or self.index is None:
            return False
        
        # 检查向量缓存和文件路径列表是否非空
        if not self.vector_cache or not self.file_paths:
            return False
        
        return True



def main():
    parser = argparse.ArgumentParser(description='Codebase management and search tool')
    parser.add_argument('--search', type=str, help='Search query to find similar code files')
    parser.add_argument('--top-k', type=int, default=20, help='Number of results to return (default: 20)')
    parser.add_argument('--ask', type=str, help='Ask a question about the codebase')
    parser.add_argument('--generate', action='store_true', help='Generate codebase index')
    args = parser.parse_args()
    
    current_dir = find_git_root()
    codebase = CodeBase(current_dir)

    # 如果没有生成索引，且不是生成命令，提示用户先生成索引
    if not codebase.is_index_generated() and not args.generate:
        PrettyOutput.print("索引尚未生成，请先运行 --generate 生成索引", output_type=OutputType.WARNING)
        return


    if args.generate:
        try:
            codebase.generate_codebase(force=True)
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