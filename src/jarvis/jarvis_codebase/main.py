import hashlib
import os
import numpy as np
import faiss
from typing import List, Tuple, Optional, Dict

import yaml
from jarvis.models.registry import PlatformRegistry
import concurrent.futures
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from jarvis.utils import OutputType, PrettyOutput, find_git_root, get_file_md5, get_max_context_length, get_thread_count, load_embedding_model, load_rerank_model
from jarvis.utils import load_env_from_file
import argparse
import pickle
import lzma  # 添加 lzma 导入
from tqdm import tqdm
import re

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
            test_text = """This is a test text"""
            # 预热模型，确保所有组件都被加载
            self.embedding_model.encode([test_text], 
                                     convert_to_tensor=True,
                                     normalize_embeddings=True)
            PrettyOutput.print("Model loaded successfully", output_type=OutputType.SUCCESS)
        except Exception as e:
            PrettyOutput.print(f"Failed to load model: {str(e)}", output_type=OutputType.ERROR)
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
                with lzma.open(self.cache_path, 'rb') as f:
                    cache_data = pickle.load(f)
                    self.vector_cache = cache_data["vectors"]
                    self.file_paths = cache_data["file_paths"]
                PrettyOutput.print(f"Loaded {len(self.vector_cache)} vector cache", 
                                 output_type=OutputType.INFO)
                # 从缓存重建索引
                self.build_index()
            except Exception as e:
                PrettyOutput.print(f"Failed to load cache: {str(e)}", 
                                 output_type=OutputType.WARNING)
                self.vector_cache = {}
                self.file_paths = []
                self.index = None

    def get_git_file_list(self):
        """Get the list of files in the git repository, excluding the .jarvis-codebase directory"""
        files = os.popen("git ls-files").read().splitlines()
        # Filter out files in the .jarvis-codebase directory
        return [f for f in files if not f.startswith(".jarvis-")]

    def is_text_file(self, file_path: str):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                f.read()
                return True
            except UnicodeDecodeError:
                return False

    def make_description(self, file_path: str, content: str) -> str:
        model = PlatformRegistry.get_global_platform_registry().get_cheap_platform()
        if self.thread_count > 1:
            model.set_suppress_output(True)
        else:
            PrettyOutput.print(f"Make description for {file_path} ...", output_type=OutputType.PROGRESS)
        prompt = f"""Please analyze the following code file and generate a detailed description. The description should include:
1. Overall file functionality description, no more than 100 characters
2. One-sentence description (max 50 characters) for each global variable, function, type definition, class, method, and other code elements
3. 5 potential questions users might ask about this file

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
    
    def _save_cache(self):
        """Save cache data"""
        try:
            # Create a copy of the cache data
            cache_data = {
                "vectors": dict(self.vector_cache),  # 创建字典的副本
                "file_paths": list(self.file_paths)  # 创建列表的副本
            }
            
            # 使用 lzma 压缩存储
            with lzma.open(self.cache_path, 'wb') as f:
                pickle.dump(cache_data, f, protocol=pickle.HIGHEST_PROTOCOL)
            PrettyOutput.print(f"Saved {len(self.vector_cache)} vector cache", 
                             output_type=OutputType.INFO)
        except Exception as e:
            PrettyOutput.print(f"Failed to save cache: {str(e)}", 
                             output_type=OutputType.ERROR)
            raise  # 抛出异常以便上层处理

    def get_cached_vector(self, file_path: str, description: str) -> Optional[np.ndarray]:
        """Get the vector representation of a file from the cache"""
        if file_path not in self.vector_cache:
            return None
        
        # Check if the file has been modified
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
        
        # Check if the description has changed
        if cached_data["description"] != description:
            return None
        
        return cached_data["vector"]

    def cache_vector(self, file_path: str, vector: np.ndarray, description: str):
        """Cache the vector representation of a file"""
        try:
            with open(file_path, "rb") as f:
                file_md5 = hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            PrettyOutput.print(f"计算文件MD5失败 {file_path}: {str(e)}", 
                              output_type=OutputType.ERROR)
            file_md5 = ""
        
        # Only update the in-memory cache
        self.vector_cache[file_path] = {
            "path": file_path,  # Save file path
            "md5": file_md5,    # Save file MD5
            "description": description,  # Save file description
            "vector": vector    # Save vector
        }

    def get_embedding(self, text: str) -> np.ndarray:
        """Use the transformers model to get the vector representation of text"""
        # Truncate long text
        max_length = 512  # Or other suitable length
        text = ' '.join(text.split()[:max_length])
        
        # Get the embedding vector
        embedding = self.embedding_model.encode(text, 
                                                 normalize_embeddings=True,  # L2 normalization
                                                 show_progress_bar=False)
        vector = np.array(embedding, dtype=np.float32)
        return vector

    def vectorize_file(self, file_path: str, description: str) -> np.ndarray:
        """Vectorize the file content and description"""
        try:
            # Try to get the vector from the cache first
            cached_vector = self.get_cached_vector(file_path, description)
            if cached_vector is not None:
                return cached_vector
                
            # Read the file content and combine information
            content = open(file_path, "r", encoding="utf-8").read()[:self.max_context_length]  # Limit the file content length
            
            # Combine file information, including file content
            combined_text = f"""
{file_path}
{description}
{content}
"""
            vector = self.get_embedding(combined_text)
            
            # Save to cache
            self.cache_vector(file_path, vector, description)
            return vector
        except Exception as e:
            PrettyOutput.print(f"Error vectorizing file {file_path}: {str(e)}", 
                             output_type=OutputType.ERROR)
            return np.zeros(self.vector_dim, dtype=np.float32) # type: ignore

    def clean_cache(self) -> bool:
        """Clean expired cache records, return whether any files were deleted"""
        try:
            files_to_delete = []
            for file_path in list(self.vector_cache.keys()):
                if file_path not in self.git_file_list:
                    del self.vector_cache[file_path]
                    files_to_delete.append(file_path)
            
            if files_to_delete:
                # Save cache only when files are deleted
                self._save_cache()
                PrettyOutput.print(f"Cleaned {len(files_to_delete)} cache files", 
                                output_type=OutputType.INFO)
                return True
            return False
            
        except Exception as e:
            PrettyOutput.print(f"Failed to clean cache: {str(e)}", 
                            output_type=OutputType.ERROR)
            # Try to save the current state when an exception occurs
            try:
                self._save_cache()
            except:
                pass
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
            PrettyOutput.print(f"Failed to process file {file_path}: {str(e)}", 
                             output_type=OutputType.ERROR)
            return None

    def build_index(self):
        """Build a faiss index from the vector cache"""
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
            vectors.append(data["vector"].reshape(1, -1))
            ids.append(i)
            self.file_paths.append(file_path)
            
        if vectors:
            vectors = np.vstack(vectors)
            self.index.add_with_ids(vectors, np.array(ids)) # type: ignore
        else:
            self.index = None

    def gen_vector_db_from_cache(self):
        """Generate a vector database from the cache"""
        self.build_index()
        self._save_cache()


    def generate_codebase(self, force: bool = False):
        """Generate the codebase index
        Args:
            force: Whether to force rebuild the index, without asking the user
        """
        try:
            # Update the git file list
            self.git_file_list = self.get_git_file_list()
            
            # Check file changes
            PrettyOutput.print("\nCheck file changes...", output_type=OutputType.INFO)
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
            with tqdm(total=len(self.git_file_list), desc="Check file status") as pbar:
                for file_path in self.git_file_list:
                    if not os.path.exists(file_path) or not self.is_text_file(file_path):
                        pbar.update(1)
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
                        PrettyOutput.print(f"检查文件失败 {file_path}: {str(e)}", 
                                         output_type=OutputType.ERROR)
                    pbar.update(1)
            
            # If changes are detected, display changes and ask the user
            if changes_detected:
                PrettyOutput.print("\nDetected the following changes:", output_type=OutputType.WARNING)
                if new_files:
                    PrettyOutput.print("\nNew files:", output_type=OutputType.INFO)
                    for f in new_files:
                        PrettyOutput.print(f"  {f}", output_type=OutputType.INFO)
                if modified_files:
                    PrettyOutput.print("\nModified files:", output_type=OutputType.INFO)
                    for f in modified_files:
                        PrettyOutput.print(f"  {f}", output_type=OutputType.INFO)
                if deleted_files:
                    PrettyOutput.print("\nDeleted files:", output_type=OutputType.INFO)
                    for f in deleted_files:
                        PrettyOutput.print(f"  {f}", output_type=OutputType.INFO)

                # If force is True, continue directly
                if not force:
                    # Ask the user whether to continue
                    while True:
                        response = input("\nRebuild the index? [y/N] ").lower().strip()
                        if response in ['y', 'yes']:
                            break
                        elif response in ['', 'n', 'no']:
                            PrettyOutput.print("Cancel rebuilding the index", output_type=OutputType.INFO)
                            return
                        else:
                            PrettyOutput.print("Please input y or n", output_type=OutputType.WARNING)
                
                # Clean deleted files
                for file_path in files_to_delete:
                    del self.vector_cache[file_path]
                if files_to_delete:
                    PrettyOutput.print(f"Cleaned the cache of {len(files_to_delete)} files", 
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
                                PrettyOutput.print(f"处理文件失败 {file}: {str(e)}", 
                                                output_type=OutputType.ERROR)
                            pbar.update(1)

                if processed_files:
                    PrettyOutput.print("\nRebuilding the vector database...", output_type=OutputType.INFO)
                    self.gen_vector_db_from_cache()
                    PrettyOutput.print(f"Successfully generated the index for {len(processed_files)} files", 
                                    output_type=OutputType.SUCCESS)
            else:
                PrettyOutput.print("No file changes detected, no need to rebuild the index", output_type=OutputType.INFO)
                
        except Exception as e:
            # Try to save the cache when an exception occurs
            try:
                self._save_cache()
            except Exception as save_error:
                PrettyOutput.print(f"Failed to save cache: {str(save_error)}", 
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

    def pick_results(self, query: str, initial_results: List[Tuple[str, float, str]]) -> List[Tuple[str, float]]:
        """Use a large model to pick the search results
        
        Args:
            query: Search query
            initial_results: Initial results list, each item is a tuple of (file path, score, description)
            
        Returns:
            List[Tuple[str, float]]: The picked results list, each item is a tuple of (file path, score)
        """
        if not initial_results:
            return []
            
        try:
            # Prepare the prompt
            files_info = ""
            for path, _, desc in initial_results:
                files_info += f"File: {path}\nDescription: {desc}\n\n"
                
            prompt = f"""Please analyze the following code files and determine which files are most relevant to the given query. Consider file paths and descriptions to make your judgment.

Query: {query}

Available files:
{files_info}

Please output a YAML list of relevant file paths, ordered by relevance (most relevant first). Only include files that are truly relevant to the query.
Output format:
<FILES>
- path/to/file1.py
- path/to/file2.py
</FILES>

Note: Only include files that have a strong connection to the query."""

            # Use a large model to evaluate
            model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
            response = model.chat_until_success(prompt)

            # Parse the response
            import yaml
            files_match = re.search(r'<FILES>\n(.*?)</FILES>', response, re.DOTALL)
            if not files_match:
                return [(path, score) for path, score, _ in initial_results]

            # Extract the file list
            selected_files = yaml.safe_load(files_match.group(1))

            # Build the results, using the position as the score
            scored_results = []
            for i, file_path in enumerate(selected_files):
                # The score decreases from 1 to 0.1
                score = 1.0 - (i * 0.9 / len(selected_files))
                scored_results.append((file_path, score))

            return scored_results

        except Exception as e:
            PrettyOutput.print(f"Failed to pick: {str(e)}", 
                            output_type=OutputType.ERROR)
            return [(path, score) for path, score, _ in initial_results]

    def _generate_query_variants(self, query: str) -> List[str]:
        """Generate different expressions of the query
        
        Args:
            query: Original query
            
        Returns:
            List[str]: The query variants list
        """
        model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
        prompt = f"""Please generate 3 different expressions based on the following query, each expression should fully convey the meaning of the original query. These expressions will be used for code search, maintain professionalism and accuracy.
Original query: {query}

Please output 3 expressions directly, separated by two line breaks, without numbering or other markers.
"""
        variants = model.chat_until_success(prompt).strip().split('\n\n')
        variants.append(query)  # Add the original query
        return variants

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
            query_vector = self.get_embedding(query)
            query_vector = query_vector.reshape(1, -1)
            
            distances, indices = self.index.search(query_vector, top_k) # type: ignore
            
            for i, distance in zip(indices[0], distances[0]):
                if i == -1:
                    continue
                    
                similarity = 1.0 / (1.0 + float(distance))
                if similarity >= 0.5:
                    file_path = self.file_paths[i]
                    # Use the highest similarity score
                    if file_path not in results or similarity > results[file_path][1]:
                        data = self.vector_cache[file_path]
                        results[file_path] = (file_path, similarity, data["description"])
        
        return results


    def search_similar(self, query: str, top_k: int = 30) -> List[Tuple[str, float]]:
        """Search related files"""
        try:
            if self.index is None:
                return []            
            # Generate the query variants
            query_variants = self._generate_query_variants(query)
            
            # Perform vector search
            vector_results = self._vector_search(query_variants, top_k)            

            results = list(vector_results.values())
            results.sort(key=lambda x: x[1], reverse=True)

            # Take the top top_k results for reordering
            initial_results = results[:top_k]
            
            # If no results are found, return directly
            if not initial_results:
                return []
            
            # Filter low-scoring results
            initial_results = [(path, score, desc) for path, score, desc in initial_results if score >= 0.5]
                
            # Reorder the preliminary results
            return self.pick_results(query, initial_results)
            
        except Exception as e:
            PrettyOutput.print(f"Failed to search: {str(e)}", output_type=OutputType.ERROR)
            return []

    def ask_codebase(self, query: str, top_k: int=20) -> str:
        """Query the codebase"""
        results = self.search_similar(query, top_k)
        if not results:
            PrettyOutput.print("No related files found", output_type=OutputType.WARNING)
            return ""
        
        PrettyOutput.print(f"Found related files: ", output_type=OutputType.SUCCESS)
        for path, score in results:
            PrettyOutput.print(f"File: {path} Similarity: {score:.3f}", 
                             output_type=OutputType.INFO)
        
        prompt = f"""You are a code expert, please answer the user's question based on the following file information:
"""
        for path, _ in results:
            try:
                if len(prompt) > self.max_context_length:
                    PrettyOutput.print(f"Avoid context overflow, discard low-related file: {path}", OutputType.WARNING)
                    continue
                content = open(path, "r", encoding="utf-8").read()
                prompt += f"""
File path: {path}prompt
File content:
{content}
========================================
"""
            except Exception as e:
                PrettyOutput.print(f"Failed to read file {path}: {str(e)}", 
                                 output_type=OutputType.ERROR)
                continue
                
        prompt += f"""
User question: {query}

Please answer the user's question in Chinese using professional language. If the provided file content is insufficient to answer the user's question, please inform the user. Never make up information.
"""
        model = PlatformRegistry.get_global_platform_registry().get_codegen_platform()
        response = model.chat_until_success(prompt)
        return response

    def is_index_generated(self) -> bool:
        """Check if the index has been generated"""
        # Check if the cache file exists
        if not os.path.exists(self.cache_path):
            return False
        
        # Check if the cache is valid
        try:
            with lzma.open(self.cache_path, 'rb') as f:
                cache_data = pickle.load(f)
                if not cache_data.get("vectors") or not cache_data.get("file_paths"):
                    return False
        except Exception:
            return False
        
        # Check if the index has been built
        if not hasattr(self, 'index') or self.index is None:
            return False
        
        # Check if the vector cache and file path list are non-empty
        if not self.vector_cache or not self.file_paths:
            return False
        
        return True





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
            PrettyOutput.print("\nCodebase generation completed", output_type=OutputType.SUCCESS)
        except Exception as e:
            PrettyOutput.print(f"Error during codebase generation: {str(e)}", output_type=OutputType.ERROR)
    
    elif args.command == 'search':
        results = codebase.search_similar(args.query, args.top_k)
        if not results:
            PrettyOutput.print("No similar files found", output_type=OutputType.WARNING)
            return
            
        PrettyOutput.print("\nSearch Results:", output_type=OutputType.INFO)
        for path, score in results:
            PrettyOutput.print("\n" + "="*50, output_type=OutputType.INFO)
            PrettyOutput.print(f"File: {path}", output_type=OutputType.INFO)
            PrettyOutput.print(f"Similarity: {score:.3f}", output_type=OutputType.INFO)

    elif args.command == 'ask':            
        response = codebase.ask_codebase(args.question, args.top_k)
        PrettyOutput.print("\nAnswer:", output_type=OutputType.INFO)
        PrettyOutput.print(response, output_type=OutputType.INFO)

    else:
        parser.print_help()


if __name__ == "__main__":
    exit(main())