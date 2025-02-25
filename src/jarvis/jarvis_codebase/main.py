import hashlib
import os
import numpy as np
import faiss
from typing import List, Tuple, Optional, Dict

from jarvis.jarvis_platform.registry import PlatformRegistry
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from jarvis.jarvis_utils import OutputType, PrettyOutput, find_git_root, get_context_token_count, get_embedding, get_file_md5, get_max_token_count, get_thread_count, load_embedding_model, user_confirm
from jarvis.jarvis_utils import init_env
import argparse
import pickle
import lzma  # 添加 lzma 导入
from tqdm import tqdm
import re

class CodeBase:
    def __init__(self, root_dir: str):
        init_env()
        self.root_dir = root_dir
        os.chdir(self.root_dir)
        self.thread_count = get_thread_count()
        self.max_token_count = get_max_token_count()
        self.index = None
            
        # 初始化数据目录
        self.data_dir = os.path.join(self.root_dir, ".jarvis/codebase")
        self.cache_dir = os.path.join(self.data_dir, "cache")
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
            
        # 初始化嵌入模型
        try:
            self.embedding_model = load_embedding_model()
            test_text = """This is a test text"""
            self.embedding_model.encode([test_text], 
                                     convert_to_tensor=True,
                                     normalize_embeddings=True)
            PrettyOutput.print("模型加载成功", output_type=OutputType.SUCCESS)
        except Exception as e:
            PrettyOutput.print(f"加载模型失败: {str(e)}", output_type=OutputType.ERROR)
            raise
            
        self.vector_dim = self.embedding_model.get_sentence_embedding_dimension()
        self.git_file_list = self.get_git_file_list()
        self.platform_registry = PlatformRegistry.get_global_platform_registry()
        
        # 初始化缓存和索引
        self.vector_cache = {}
        self.file_paths = []
        
        # 加载所有缓存文件
        self._load_all_cache()

    def get_git_file_list(self):
        """Get the list of files in the git repository, excluding the .jarvis-codebase directory"""
        files = os.popen("git ls-files").read().splitlines()
        # Filter out files in the .jarvis-codebase directory
        return [f for f in files if not f.startswith(".jarvis")]

    def is_text_file(self, file_path: str):
        try:
            open(file_path, "r", encoding="utf-8").read()
            return True
        except Exception:
            return False

    def make_description(self, file_path: str, content: str) -> str:
        model = PlatformRegistry.get_global_platform_registry().get_cheap_platform()
        if self.thread_count > 1:
            model.set_suppress_output(True)
        else:
            PrettyOutput.print(f"为 {file_path} 生成描述 ...", output_type=OutputType.PROGRESS)
        prompt = f"""Please analyze the following code file and generate a detailed description. The description should include:
1. Overall file functionality description
2. description for each global variable, function, type definition, class, method, and other code elements

Please use concise and professional language, emphasizing technical functionality to facilitate subsequent code retrieval.
File path: {file_path}
Code content:
{content}
"""
        response = model.chat_until_success(prompt)
        return response

    def export(self):
        """Export the current index data to standard output"""
        for file_path, data in self.vector_cache.items():
            print(f"## {file_path}")
            print(f"- path: {file_path}")
            print(f"- description: {data['description']}")
    
    def _get_cache_path(self, file_path: str) -> str:
        """Get cache file path for a source file
        
        Args:
            file_path: Source file path
            
        Returns:
            str: Cache file path
        """
        # 处理文件路径：
        # 1. 移除开头的 ./ 或 /
        # 2. 将 / 替换为 --
        # 3. 添加 .cache 后缀
        clean_path = file_path.lstrip('./').lstrip('/')
        cache_name = clean_path.replace('/', '--') + '.cache'
        return os.path.join(self.cache_dir, cache_name)

    def _load_all_cache(self):
        """Load all cache files"""
        try:
            # 清空现有缓存和文件路径
            self.vector_cache = {}
            self.file_paths = []
            vectors = []
            
            for cache_file in os.listdir(self.cache_dir):
                if not cache_file.endswith('.cache'):
                    continue
                    
                cache_path = os.path.join(self.cache_dir, cache_file)
                try:
                    with lzma.open(cache_path, 'rb') as f:
                        cache_data = pickle.load(f)
                        file_path = cache_data["path"]
                        self.vector_cache[file_path] = cache_data
                        self.file_paths.append(file_path)
                        vectors.append(cache_data["vector"])
                except Exception as e:
                    PrettyOutput.print(f"加载缓存文件 {cache_file} 失败: {str(e)}", 
                                     output_type=OutputType.WARNING)
                    continue
            
            if vectors:
                # 重建索引
                vectors_array = np.vstack(vectors)
                hnsw_index = faiss.IndexHNSWFlat(self.vector_dim, 16)
                hnsw_index.hnsw.efConstruction = 40
                hnsw_index.hnsw.efSearch = 16
                self.index = faiss.IndexIDMap(hnsw_index)
                self.index.add_with_ids(vectors_array, np.array(range(len(vectors)))) # type: ignore
                
                PrettyOutput.print(f"加载 {len(self.vector_cache)} 个向量缓存并重建索引", 
                                 output_type=OutputType.INFO)
            else:
                self.index = None
                PrettyOutput.print("没有找到有效的缓存文件", output_type=OutputType.WARNING)
                
        except Exception as e:
            PrettyOutput.print(f"加载缓存目录失败: {str(e)}", 
                             output_type=OutputType.WARNING)
            self.vector_cache = {}
            self.file_paths = []
            self.index = None

    def cache_vector(self, file_path: str, vector: np.ndarray, description: str):
        """Cache the vector representation of a file"""
        try:
            with open(file_path, "rb") as f:
                file_md5 = hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            PrettyOutput.print(f"计算 {file_path} 的MD5失败: {str(e)}", 
                              output_type=OutputType.ERROR)
            file_md5 = ""
        
        # 准备缓存数据
        cache_data = {
            "path": file_path,  # 保存文件路径
            "md5": file_md5,    # 保存文件MD5
            "description": description,  # 保存文件描述
            "vector": vector    # 保存向量
        }
        
        # 更新内存缓存
        self.vector_cache[file_path] = cache_data
        
        # 保存到单独的缓存文件
        cache_path = self._get_cache_path(file_path)
        try:
            with lzma.open(cache_path, 'wb') as f:
                pickle.dump(cache_data, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as e:
            PrettyOutput.print(f"保存 {file_path} 的缓存失败: {str(e)}", 
                             output_type=OutputType.ERROR)

    def get_cached_vector(self, file_path: str, description: str) -> Optional[np.ndarray]:
        """Get the vector representation of a file from the cache"""
        if file_path not in self.vector_cache:
            return None
        
        # Check if the file has been modified
        try:
            with open(file_path, "rb") as f:
                current_md5 = hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            PrettyOutput.print(f"计算 {file_path} 的MD5失败: {str(e)}", 
                              output_type=OutputType.ERROR)
            return None
        
        cached_data = self.vector_cache[file_path]
        if cached_data["md5"] != current_md5:
            return None
        
        # Check if the description has changed
        if cached_data["description"] != description:
            return None
        
        return cached_data["vector"]

    def vectorize_file(self, file_path: str, description: str) -> np.ndarray:
        """Vectorize the file content and description"""
        try:
            # Try to get the vector from the cache first
            cached_vector = self.get_cached_vector(file_path, description)
            if cached_vector is not None:
                return cached_vector
                
            # Read the file content and combine information
            content = open(file_path, "r", encoding="utf-8").read()[:self.max_token_count]  # Limit the file content length
            
            # Combine file information, including file content
            combined_text = f"""
File path: {file_path}
Description: {description}
Content: {content}
"""
            vector = get_embedding(self.embedding_model, combined_text)
            
            # Save to cache
            self.cache_vector(file_path, vector, description)
            return vector
        except Exception as e:
            PrettyOutput.print(f"向量化 {file_path} 失败: {str(e)}", 
                             output_type=OutputType.ERROR)
            return np.zeros(self.vector_dim, dtype=np.float32) # type: ignore

    def clean_cache(self) -> bool:
        """Clean expired cache records"""
        try:
            files_to_delete = []
            for file_path in list(self.vector_cache.keys()):
                if not os.path.exists(file_path):
                    files_to_delete.append(file_path)
                    cache_path = self._get_cache_path(file_path)
                    try:
                        os.remove(cache_path)
                    except Exception:
                        pass
                        
            for file_path in files_to_delete:
                del self.vector_cache[file_path]
                if file_path in self.file_paths:
                    self.file_paths.remove(file_path)
                    
            return bool(files_to_delete)
            
        except Exception as e:
            PrettyOutput.print(f"清理缓存失败: {str(e)}", 
                             output_type=OutputType.ERROR)
            return False

    def process_file(self, file_path: str):
        """Process a single file"""
        try:
            # Skip non-existent files
            if not os.path.exists(file_path):
                return None
                
            if not self.is_text_file(file_path):
                return None
            
            md5 = get_file_md5(file_path)

            content = open(file_path, "r", encoding="utf-8").read()
            
            # Check if the file has already been processed and the content has not changed
            if file_path in self.vector_cache:
                if self.vector_cache[file_path].get("md5") == md5:
                    return None
                    
            description = self.make_description(file_path, content)  # Pass the truncated content
            vector = self.vectorize_file(file_path, description)
            
            # Save to cache, using the actual file path as the key
            self.vector_cache[file_path] = {
                "vector": vector,
                "description": description,
                "md5": md5
            }
            
            return file_path
            
        except Exception as e:
            PrettyOutput.print(f"处理 {file_path} 失败: {str(e)}", 
                             output_type=OutputType.ERROR)
            return None

    def build_index(self):
        """Build a faiss index from the vector cache"""
        try:
            if not self.vector_cache:
                self.index = None
                return

            # Create the underlying HNSW index
            hnsw_index = faiss.IndexHNSWFlat(self.vector_dim, 16)
            hnsw_index.hnsw.efConstruction = 40
            hnsw_index.hnsw.efSearch = 16
            
            # Wrap the HNSW index with IndexIDMap
            self.index = faiss.IndexIDMap(hnsw_index)
            
            vectors = []
            ids = []
            self.file_paths = []  # Reset the file path list
            
            for i, (file_path, data) in enumerate(self.vector_cache.items()):
                if "vector" not in data:
                    PrettyOutput.print(f"无效的缓存数据 {file_path}: 缺少向量", 
                                     output_type=OutputType.WARNING)
                    continue
                    
                vector = data["vector"]
                if not isinstance(vector, np.ndarray):
                    PrettyOutput.print(f"无效的向量类型 {file_path}: {type(vector)}", 
                                     output_type=OutputType.WARNING)
                    continue
                    
                vectors.append(vector.reshape(1, -1))
                ids.append(i)
                self.file_paths.append(file_path)
                
            if vectors:
                vectors = np.vstack(vectors)
                if len(vectors) != len(ids):
                    PrettyOutput.print(f"向量数量不匹配: {len(vectors)} 个向量 vs {len(ids)} 个ID", 
                                     output_type=OutputType.ERROR)
                    self.index = None
                    return
                    
                try:
                    self.index.add_with_ids(vectors, np.array(ids)) # type: ignore
                    PrettyOutput.print(f"成功构建包含 {len(vectors)} 个向量的索引", 
                                     output_type=OutputType.SUCCESS)
                except Exception as e:
                    PrettyOutput.print(f"添加向量到索引失败: {str(e)}", 
                                     output_type=OutputType.ERROR)
                    self.index = None
            else:
                PrettyOutput.print("没有找到有效的向量, 索引未构建", 
                                 output_type=OutputType.WARNING)
                self.index = None
                
        except Exception as e:
            PrettyOutput.print(f"构建索引失败: {str(e)}", 
                             output_type=OutputType.ERROR)
            self.index = None

    def gen_vector_db_from_cache(self):
        """Generate a vector database from the cache"""
        self.build_index()
        self._load_all_cache()


    def generate_codebase(self, force: bool = False):
        """Generate the codebase index
        Args:
            force: Whether to force rebuild the index, without asking the user
        """
        try:
            # Clean up cache for non-existent files
            files_to_delete = []
            for cached_file in list(self.vector_cache.keys()):
                if not os.path.exists(cached_file) or not self.is_text_file(cached_file):
                    files_to_delete.append(cached_file)
                    cache_path = self._get_cache_path(cached_file)
                    try:
                        os.remove(cache_path)
                    except Exception as e:
                        PrettyOutput.print(f"删除缓存文件 {cached_file} 失败: {str(e)}", 
                                         output_type=OutputType.WARNING)
            
            if files_to_delete:
                for file_path in files_to_delete:
                    del self.vector_cache[file_path]
                PrettyOutput.print(f"清理了 {len(files_to_delete)} 个不存在的文件的缓存", 
                                 output_type=OutputType.INFO)
            
            # Update the git file list
            self.git_file_list = self.get_git_file_list()
            
            # Check file changes
            PrettyOutput.print("检查文件变化...", output_type=OutputType.INFO)
            changes_detected = False
            new_files = []
            modified_files = []
            deleted_files = []
            
            # Check deleted files
            files_to_delete = []
            for file_path in list(self.vector_cache.keys()):
                if file_path not in self.git_file_list:
                    deleted_files.append(file_path)
                    files_to_delete.append(file_path)
                    changes_detected = True
            # Check new and modified files
            from rich.progress import Progress
            with Progress() as progress:
                task = progress.add_task("Check file status", total=len(self.git_file_list))
                for file_path in self.git_file_list:
                    if not os.path.exists(file_path) or not self.is_text_file(file_path):
                        progress.advance(task)
                        continue
                    
                    try:
                        current_md5 = get_file_md5(file_path)
                        
                        if file_path not in self.vector_cache:
                            new_files.append(file_path)
                            changes_detected = True
                        elif self.vector_cache[file_path].get("md5") != current_md5:
                            modified_files.append(file_path)
                            changes_detected = True
                    except Exception as e:
                        PrettyOutput.print(f"检查 {file_path} 失败: {str(e)}", 
                                         output_type=OutputType.ERROR)
                    progress.advance(task)
            
            # If changes are detected, display changes and ask the user
            if changes_detected:
                output_lines = ["检测到以下变化:"]
                if new_files:
                    output_lines.append("新文件:")
                    output_lines.extend(f"  {f}" for f in new_files)
                if modified_files:
                    output_lines.append("修改的文件:")
                    output_lines.extend(f"  {f}" for f in modified_files)
                if deleted_files:
                    output_lines.append("删除的文件:")
                    output_lines.extend(f"  {f}" for f in deleted_files)
                
                PrettyOutput.print("\n".join(output_lines), output_type=OutputType.WARNING)

                # If force is True, continue directly
                if not force:
                    if not user_confirm("重建索引?", False):
                        PrettyOutput.print("取消重建索引", output_type=OutputType.INFO)
                        return
                
                # Clean deleted files
                for file_path in files_to_delete:
                    del self.vector_cache[file_path]
                if files_to_delete:
                    PrettyOutput.print(f"清理了 {len(files_to_delete)} 个文件的缓存", 
                                     output_type=OutputType.INFO)
                
                # Process new and modified files
                files_to_process = new_files + modified_files
                processed_files = []
                
                with tqdm(total=len(files_to_process), desc="Processing files") as pbar:
                    # Use a thread pool to process files
                    with ThreadPoolExecutor(max_workers=self.thread_count) as executor:
                        # Submit all tasks
                        future_to_file = {
                            executor.submit(self.process_file, file): file 
                            for file in files_to_process
                        }
                        
                        # Process completed tasks
                        for future in concurrent.futures.as_completed(future_to_file):
                            file = future_to_file[future]
                            try:
                                result = future.result()
                                if result:
                                    processed_files.append(result)
                            except Exception as e:
                                PrettyOutput.print(f"Failed to process file {file}: {str(e)}", 
                                                output_type=OutputType.ERROR)
                            pbar.update(1)

                if processed_files:
                    PrettyOutput.print("重建向量数据库...", output_type=OutputType.INFO)
                    self.gen_vector_db_from_cache()
                    PrettyOutput.print(f"成功生成了 {len(processed_files)} 个文件的索引", 
                                    output_type=OutputType.SUCCESS)
            else:
                PrettyOutput.print("没有检测到文件变化, 不需要重建索引", output_type=OutputType.INFO)
                
        except Exception as e:
            # Try to save the cache when an exception occurs
            try:
                self._load_all_cache()
            except Exception as save_error:
                PrettyOutput.print(f"保存缓存失败: {str(save_error)}", 
                                output_type=OutputType.ERROR)
            raise e  # Re-raise the original exception


    def _text_search_score(self, content: str, keywords: List[str]) -> float:
        """Calculate the matching score between the text content and the keywords
        
        Args:
            content: Text content
            keywords: List of keywords
            
        Returns:
            float: Matching score (0-1)
        """
        if not keywords:
            return 0.0
            
        content = content.lower()
        matched_keywords = set()
        
        for keyword in keywords:
            keyword = keyword.lower()
            if keyword in content:
                matched_keywords.add(keyword)
                
        # Calculate the matching score
        score = len(matched_keywords) / len(keywords)
        return score

    def pick_results(self, query: List[str], initial_results: List[str]) -> List[Dict[str,str]]:
        """Use a large model to pick the search results
        
        Args:
            query: Search query
            initial_results: Initial results list of file paths
            
        Returns:
            List[str]: The picked results list, each item is a file path
        """
        if not initial_results:
            return []
            
        try:
            PrettyOutput.print(f"Picking results ...", output_type=OutputType.INFO)
            
            # Maximum content length per batch
            max_batch_length = self.max_token_count - 1000  # Reserve space for prompt
            max_file_length = max_batch_length // 3  # Limit individual file size
            
            # Process files in batches
            all_selected_files = []
            current_batch = []
            current_token_count = 0
            
            for path in initial_results:
                try:
                    content = open(path, "r", encoding="utf-8").read()
                    # Truncate large files
                    if get_context_token_count(content) > max_file_length:
                        PrettyOutput.print(f"Truncating large file: {path}", OutputType.WARNING)
                        content = content[:max_file_length] + "\n... (content truncated)"
                    
                    file_info = f"File: {path}\nContent: {content}\n\n"
                    tokens_count = get_context_token_count(file_info)
                    
                    # If adding this file would exceed batch limit
                    if current_token_count + tokens_count > max_batch_length:
                        # Process current batch
                        if current_batch:
                            selected = self._process_batch('\n'.join(query), current_batch)
                            all_selected_files.extend(selected)
                        # Start new batch
                        current_batch = [file_info]
                        current_token_count = tokens_count
                    else:
                        current_batch.append(file_info)
                        current_token_count += tokens_count
                        
                except Exception as e:
                    PrettyOutput.print(f"读取 {path} 失败: {str(e)}", OutputType.ERROR)
                    continue
            
            # Process final batch
            if current_batch:
                selected = self._process_batch('\n'.join(query), current_batch)
                all_selected_files.extend(selected)
            
            # Convert set to list and maintain original order
            return all_selected_files

        except Exception as e:
            PrettyOutput.print(f"选择失败: {str(e)}", OutputType.ERROR)
            return [{"file": f, "reason": "" } for f in initial_results]
            
    def _process_batch(self, query: str, files_info: List[str]) -> List[Dict[str, str]]:
        """Process a batch of files"""
        prompt = f"""As a code analysis expert, please help identify the most relevant files for the given query using chain-of-thought reasoning.

Query: {query}

Available files:
{''.join(files_info)}

Think through this step by step:
1. First, analyze the query to identify key requirements and technical concepts
2. For each file:
   - Examine its path and content
   - Assess how it relates to the query's requirements
   - Consider both direct and indirect relationships
   - Rate its relevance (high/medium/low)
3. Select only files with clear relevance to the query
4. Order files by relevance, with most relevant first

Please output your selection in YAML format:
<FILES>
- file: path/to/most/relevant.py
  reason: xxxxxxxxxx
- path/to/next/relevant.py
  reason: yyyyyyyyyy
</FILES>

Important:
- Only include files that are truly relevant
- Exclude files with weak or unclear connections
- Focus on implementation rather than test files
- Consider both file paths and content
- Only output the file paths, no other text
"""

        # Use a large model to evaluate
        model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
        model.set_suppress_output(True)
        response = model.chat_until_success(prompt)

        # Parse the response
        import yaml
        files_match = re.search(r'<FILES>\n(.*?)</FILES>', response, re.DOTALL)
        if not files_match:
            return []

        try:
            selected_files = yaml.safe_load(files_match.group(1))
            return selected_files if selected_files else []
        except Exception as e:
            PrettyOutput.print(f"解析响应失败: {str(e)}", OutputType.ERROR)
            return []

    def _generate_query_variants(self, query: str) -> List[str]:
        """Generate different expressions of the query optimized for vector search
        
        Args:
            query: Original query
            
        Returns:
            List[str]: The query variants list
        """
        model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
        model.set_suppress_output(True)
        prompt = f"""Please generate 10 different expressions optimized for vector search based on the following query. Each expression should:

1. Focus on key technical concepts and terminology
2. Use clear and specific language
3. Include important contextual terms
4. Avoid general or ambiguous words
5. Maintain semantic similarity with original query
6. Be suitable for embedding-based search

Original query: 
{query}

Example transformations:
Query: "How to handle user login?"
Output format:
<QUESTION>
- user authentication implementation and flow
- login system architecture and components
- credential validation and session management
- ...
</QUESTION>

Please provide 10 search-optimized expressions in the specified format.
"""
        response = model.chat_until_success(prompt)
        
        # Parse the response using YAML format
        import yaml
        variants = []
        question_match = re.search(r'<QUESTION>\n(.*?)</QUESTION>', response, re.DOTALL)
        if question_match:
            try:
                variants = yaml.safe_load(question_match.group(1))
                if not isinstance(variants, list):
                    variants = [str(variants)]
            except Exception as e:
                PrettyOutput.print(f"解析变体失败: {str(e)}", OutputType.ERROR)
        
        # Add original query
        variants.append(query)
        return variants if variants else [query]

    def _vector_search(self, query_variants: List[str], top_k: int) -> Dict[str, Tuple[str, float, str]]:
        """Use vector search to find related files
        
        Args:
            query_variants: The query variants list
            top_k: The number of results to return
            
        Returns:
            Dict[str, Tuple[str, float, str]]: The mapping from file path to (file path, score, description)
        """
        results = {}
        for query in query_variants:
            query_vector = get_embedding(self.embedding_model, query)
            query_vector = query_vector.reshape(1, -1)
            
            distances, indices = self.index.search(query_vector, top_k) # type: ignore
            
            for i, distance in zip(indices[0], distances[0]):
                if i == -1:
                    continue
                    
                similarity = 1.0 / (1.0 + float(distance))
                file_path = self.file_paths[i]
                # Use the highest similarity score
                if file_path not in results:
                    if similarity > 0.5:
                        data = self.vector_cache[file_path]
                        results[file_path] = (file_path, similarity, data["description"])
        
        return results


    def search_similar(self, query: str, top_k: int = 30) -> List[Dict[str, str]]:
        """Search related files with optimized retrieval"""
        try:
            self.generate_codebase()
            if self.index is None:
                return []
                
            # Generate query variants for better coverage
            query_variants = self._generate_query_variants(query)
            
            # Collect results from all variants
            all_results = []
            seen_files = set()
            
            for variant in query_variants:
                # Get vector for each variant
                query_vector = get_embedding(self.embedding_model, variant)
                query_vector = query_vector.reshape(1, -1)
                
                # Search with current variant
                initial_k = min(top_k * 2, len(self.file_paths))
                distances, indices = self.index.search(query_vector, initial_k) # type: ignore
                
                # Process results
                for idx, dist in zip(indices[0], distances[0]):
                    if idx != -1:
                        file_path = self.file_paths[idx]
                        if file_path not in seen_files:
                            similarity = 1.0 / (1.0 + float(dist))
                            if similarity > 0.3:  # Lower threshold for better recall
                                seen_files.add(file_path)
                                all_results.append((file_path, similarity, self.vector_cache[file_path]["description"]))
            
            if not all_results:
                return []
                
            # Sort by similarity and take top_k
            all_results.sort(key=lambda x: x[1], reverse=True)
            results = all_results[:top_k]

            results = self.pick_results(query_variants, [path for path, _, _ in results])

            output = "Found related files:\n"
            for file in results:
                output += f'''- {file['file']} ({file['reason']})\n'''
            PrettyOutput.print(output, output_type=OutputType.INFO, lang="markdown")

            
            return results
            
        except Exception as e:
            PrettyOutput.print(f"搜索失败: {str(e)}", output_type=OutputType.ERROR)
            return []

    def ask_codebase(self, query: str, top_k: int=20) -> Tuple[List[Dict[str, str]], str]:
        """Query the codebase with enhanced context building"""
        files_from_codebase = self.search_similar(query, top_k)
        
        if not files_from_codebase:
            PrettyOutput.print("没有找到相关文件", output_type=OutputType.WARNING)
            return [],""
        
        # Build enhanced prompt
        prompt = f"""Based on the following code files, please provide a comprehensive and accurate answer to the user's question.

Important guidelines:
1. Focus on code-specific details and implementation
2. Explain technical concepts clearly
3. Include relevant code snippets when helpful
4. If the code doesn't fully answer the question, indicate what's missing
5. Answer in user's language.
6. Answer with professional language.

Question: {query}

Relevant code files (ordered by relevance):
"""
        # Add context with length control
        available_count = self.max_token_count - get_context_token_count(prompt) - 1000  # Reserve space for answer
        current_count = 0
        
        for path in files_from_codebase:
            try:
                content = open(path["file"], "r", encoding="utf-8").read()
                file_content = f"""
File: {path["file"]}
Content:
{content}
----------------------------------------
"""
                if current_count + get_context_token_count(file_content) > available_count:
                    PrettyOutput.print(
                        "由于上下文长度限制, 一些文件被省略", 
                        output_type=OutputType.WARNING
                    )
                    break
                    
                prompt += file_content
                current_count += get_context_token_count(file_content)
                
            except Exception as e:
                PrettyOutput.print(f"读取 {path} 失败: {str(e)}", 
                                output_type=OutputType.ERROR)
                continue
        
        model = PlatformRegistry.get_global_platform_registry().get_thinking_platform()

        prompt += """
Output Format:
- question: the question to answer
  answer: the answer to the question
- question: the question to answer
  answer: the answer to the question
"""

        return files_from_codebase, model.chat_until_success(prompt)

    def is_index_generated(self) -> bool:
        """Check if the index has been generated"""
        try:
            # 1. 检查基本条件
            if not self.vector_cache or not self.file_paths:
                return False
                
            if not hasattr(self, 'index') or self.index is None:
                return False
                
            # 2. 检查索引是否可用
            # 创建测试向量
            test_vector = np.zeros((1, self.vector_dim), dtype=np.float32) # type: ignore
            try:
                self.index.search(test_vector, 1) # type: ignore
            except Exception:
                return False
                
            # 3. 验证向量缓存和文件路径的一致性
            if len(self.vector_cache) != len(self.file_paths):
                return False
                
            # 4. 验证所有缓存文件
            for file_path in self.file_paths:
                if file_path not in self.vector_cache:
                    return False
                    
                cache_path = self._get_cache_path(file_path)
                if not os.path.exists(cache_path):
                    return False
                    
                cache_data = self.vector_cache[file_path]
                if not isinstance(cache_data.get("vector"), np.ndarray):
                    return False
            
            return True
            
        except Exception as e:
            PrettyOutput.print(f"检查索引状态失败: {str(e)}", 
                             output_type=OutputType.ERROR)
            return False





def main():

    parser = argparse.ArgumentParser(description='Codebase management and search tool')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Generate command
    generate_parser = subparsers.add_parser('generate', help='Generate codebase index')
    generate_parser.add_argument('--force', action='store_true', help='Force rebuild index')

    # Search command
    search_parser = subparsers.add_parser('search', help='Search similar code files')
    search_parser.add_argument('query', type=str, help='Search query')
    search_parser.add_argument('--top-k', type=int, default=20, help='Number of results to return (default: 20)')

    # Ask command
    ask_parser = subparsers.add_parser('ask', help='Ask a question about the codebase')
    ask_parser.add_argument('question', type=str, help='Question to ask')
    ask_parser.add_argument('--top-k', type=int, default=20, help='Number of results to use (default: 20)')

    export_parser = subparsers.add_parser('export', help='Export current index data')
    args = parser.parse_args()
    
    current_dir = find_git_root()
    codebase = CodeBase(current_dir)

    if args.command == 'export':
        codebase.export()
        return

    # 如果没有生成索引，且不是生成命令，提示用户先生成索引
    if not codebase.is_index_generated() and args.command != 'generate':
        PrettyOutput.print("索引尚未生成，请先运行 'generate' 命令生成索引", output_type=OutputType.WARNING)
        return

    if args.command == 'generate':
        try:
            codebase.generate_codebase(force=args.force)
            PrettyOutput.print("代码库生成完成", output_type=OutputType.SUCCESS)
        except Exception as e:
            PrettyOutput.print(f"代码库生成失败: {str(e)}", output_type=OutputType.ERROR)
    
    elif args.command == 'search':
        results = codebase.search_similar(args.query, args.top_k)
        if not results:
            PrettyOutput.print("没有找到相似的文件", output_type=OutputType.WARNING)
            return
            
        output = "搜索结果:\n"
        for path in results:
            output += f"""- {path}\n"""
        PrettyOutput.print(output, output_type=OutputType.INFO, lang="markdown")

    elif args.command == 'ask':            
        response = codebase.ask_codebase(args.question, args.top_k)
        output = f"""{response}"""
        PrettyOutput.print(output, output_type=OutputType.INFO)

    else:
        parser.print_help()


if __name__ == "__main__":
    exit(main())