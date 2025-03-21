"""
方法论管理模块
该模块提供了加载和搜索方法论的实用工具。
包含以下功能：
- 创建方法论嵌入向量
- 加载和处理方法论数据
- 构建和搜索方法论索引
- 生成方法论提示
"""
import os
import yaml
import glob
import json
import hashlib
import pickle
import numpy as np
import faiss
from typing import Dict, Any, List, Tuple, Optional
from jarvis.jarvis_utils.output import PrettyOutput, OutputType
from jarvis.jarvis_utils.embedding import load_embedding_model
from jarvis.jarvis_utils.config import dont_use_local_model

# 全局缓存，避免重复计算嵌入向量
_methodology_embeddings_cache = {}
_methodology_index_cache: Optional[Tuple[faiss.IndexIDMap, List[Dict[str, str]], str]] = None

def _get_cache_directory() -> str:
    """
    获取缓存目录路径，如果不存在则创建
    
    返回：
        str: 缓存目录的路径
    """
    cache_dir = os.path.expanduser("~/.jarvis/cache")
    if not os.path.exists(cache_dir):
        try:
            os.makedirs(cache_dir, exist_ok=True)
        except Exception as e:
            PrettyOutput.print(f"创建缓存目录失败: {str(e)}", OutputType.ERROR)
    return cache_dir

def _get_embeddings_cache_path() -> str:
    """
    获取嵌入向量缓存文件的路径
    
    返回：
        str: 嵌入向量缓存文件的路径
    """
    return os.path.join(_get_cache_directory(), "methodology_embeddings.pkl")

def _get_index_cache_path() -> str:
    """
    获取索引缓存文件的路径
    
    返回：
        str: 索引缓存文件的路径
    """
    return os.path.join(_get_cache_directory(), "methodology_index.faiss")

def _get_index_metadata_path() -> str:
    """
    获取索引元数据文件的路径
    
    返回：
        str: 索引元数据文件的路径
    """
    return os.path.join(_get_cache_directory(), "methodology_index_metadata.pkl")

def _load_embeddings_cache() -> Dict[int, np.ndarray]:
    """
    从文件系统加载嵌入向量缓存
    
    返回：
        Dict[int, np.ndarray]: 嵌入向量缓存字典
    """
    cache_path = _get_embeddings_cache_path()
    if not os.path.exists(cache_path):
        return {}
    
    try:
        with open(cache_path, "rb") as f:
            embeddings_cache = pickle.load(f)
        PrettyOutput.print(f"已从文件加载 {len(embeddings_cache)} 个嵌入向量缓存", OutputType.DEBUG)
        return embeddings_cache
    except Exception as e:
        PrettyOutput.print(f"加载嵌入向量缓存失败: {str(e)}", OutputType.WARNING)
        return {}

def _save_embeddings_cache(cache: Dict[int, np.ndarray]) -> bool:
    """
    将嵌入向量缓存保存到文件系统
    
    参数：
        cache: 要保存的嵌入向量缓存字典
        
    返回：
        bool: 保存是否成功
    """
    if not cache:
        return False
    
    cache_path = _get_embeddings_cache_path()
    
    try:
        with open(cache_path, "wb") as f:
            pickle.dump(cache, f)
        return True
    except Exception as e:
        PrettyOutput.print(f"保存嵌入向量缓存失败: {str(e)}", OutputType.WARNING)
        return False

def _load_index_cache() -> Optional[Tuple[faiss.IndexIDMap, List[Dict[str, str]], str]]:
    """
    从文件系统加载索引缓存
    
    返回：
        Optional[Tuple[faiss.IndexIDMap, List[Dict[str, str]], str]]: 索引缓存元组
    """
    index_path = _get_index_cache_path()
    metadata_path = _get_index_metadata_path()
    
    if not os.path.exists(index_path) or not os.path.exists(metadata_path):
        return None
    
    try:
        # 加载索引
        index = faiss.read_index(index_path)
        
        # 加载元数据
        with open(metadata_path, "rb") as f:
            metadata = pickle.load(f)
            
        methodology_data = metadata.get("methodology_data", [])
        methodology_hash = metadata.get("methodology_hash", "")
        
        if isinstance(index, faiss.IndexIDMap) and methodology_data and methodology_hash:
            return index, methodology_data, methodology_hash
    except Exception as e:
        PrettyOutput.print(f"加载索引缓存失败: {str(e)}", OutputType.WARNING)
    
    return None

def _save_index_cache(index: faiss.IndexIDMap, methodology_data: List[Dict[str, str]], methodology_hash: str) -> bool:
    """
    将索引缓存保存到文件系统
    
    参数：
        index: FAISS索引
        methodology_data: 方法论数据列表
        methodology_hash: 方法论文件哈希值
        
    返回：
        bool: 保存是否成功
    """
    index_path = _get_index_cache_path()
    metadata_path = _get_index_metadata_path()
    
    try:
        # 保存索引
        faiss.write_index(index, index_path)
        
        # 保存元数据
        metadata = {
            "methodology_data": methodology_data,
            "methodology_hash": methodology_hash
        }
        
        with open(metadata_path, "wb") as f:
            pickle.dump(metadata, f)
            
        return True
    except Exception as e:
        PrettyOutput.print(f"保存索引缓存失败: {str(e)}", OutputType.WARNING)
        return False

def _create_methodology_embedding(embedding_model: Any, methodology_text: str) -> np.ndarray:
    """
    为方法论文本创建嵌入向量。
    
    参数：
        embedding_model: 使用的嵌入模型
        methodology_text: 要创建嵌入的文本
        
    返回：
        np.ndarray: 嵌入向量
    """
    try:
        # 检查缓存中是否已有此文本的嵌入向量
        cache_key = hash(methodology_text)
        if cache_key in _methodology_embeddings_cache:
            return _methodology_embeddings_cache[cache_key]
            
        # 截断长文本
        max_length = 512
        text = ' '.join(methodology_text.split()[:max_length])
        
        # 使用sentence_transformers模型获取嵌入向量
        embedding = embedding_model.encode([text], 
                                          convert_to_tensor=True,
                                          normalize_embeddings=True)
        vector = np.array(embedding.cpu().numpy(), dtype=np.float32)
        result = vector[0]  # 返回第一个向量，因为我们只编码了一个文本
        
        # 缓存嵌入向量以便后续使用
        _methodology_embeddings_cache[cache_key] = result
        
        return result
    except Exception as e:
        PrettyOutput.print(f"创建方法论嵌入向量失败: {str(e)}", OutputType.ERROR)
        return np.zeros(1536, dtype=np.float32)

def make_methodology_prompt(data: Dict[str, str]) -> str:
    """
    从方法论数据生成格式化提示
    
    参数：
        data: 方法论数据字典
        
    返回：
        str: 格式化后的提示字符串
    """
    ret = """这是处理以往问题的标准方法论，如果当前任务类似，可以参考使用，如果不相关，请忽略：\n""" 
    for key, value in data.items():
        ret += f"问题: {key}\n方法论: {value}\n"
    return ret

def _get_methodology_directory() -> str:
    """
    获取方法论目录路径，如果不存在则创建
    
    返回：
        str: 方法论目录的路径
    """
    methodology_dir = os.path.expanduser("~/.jarvis/methodologies")
    if not os.path.exists(methodology_dir):
        try:
            os.makedirs(methodology_dir, exist_ok=True)
        except Exception as e:
            PrettyOutput.print(f"创建方法论目录失败: {str(e)}", OutputType.ERROR)
    return methodology_dir

def _get_methodology_files_hash() -> str:
    """
    计算所有方法论文件的组合哈希值，用于检测文件变化
    
    返回：
        str: 所有方法论文件的组合哈希值
    """
    methodology_dir = _get_methodology_directory()
    if not os.path.exists(methodology_dir):
        return ""
    
    # 获取所有方法论文件的路径和修改时间
    files_data = []
    for filepath in glob.glob(os.path.join(methodology_dir, "*.json")):
        mtime = os.path.getmtime(filepath)
        files_data.append((filepath, mtime))
    
    # 按路径排序，保证哈希值的一致性
    files_data.sort(key=lambda x: x[0])
    
    # 计算组合哈希值
    if not files_data:
        return ""
    
    hasher = hashlib.md5()
    for filepath, mtime in files_data:
        hasher.update(f"{filepath}:{mtime}".encode("utf-8"))
    
    return hasher.hexdigest()

def _load_all_methodologies() -> Dict[str, str]:
    """
    加载所有方法论文件
    
    返回：
        Dict[str, str]: 方法论字典，键为问题类型，值为方法论内容
    """
    methodology_dir = _get_methodology_directory()
    all_methodologies = {}
    
    if not os.path.exists(methodology_dir):
        return all_methodologies
    
    for filepath in glob.glob(os.path.join(methodology_dir, "*.json")):
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                methodology = json.load(f)
                problem_type = methodology.get("problem_type", "")
                content = methodology.get("content", "")
                if problem_type and content:
                    all_methodologies[problem_type] = content
        except Exception as e:
            filename = os.path.basename(filepath)
            PrettyOutput.print(f"加载方法论文件 {filename} 失败: {str(e)}", OutputType.WARNING)
    
    return all_methodologies

def _migrate_from_old_format():
    """
    从旧的单文件格式迁移到新的多文件格式
    """
    old_format_file = os.path.expanduser("~/.jarvis/methodology")
    if not os.path.exists(old_format_file):
        return
    
    try:
        # 加载旧格式文件
        with open(old_format_file, "r", encoding="utf-8", errors="ignore") as f:
            old_data = yaml.safe_load(f) or {}
        
        if not old_data:
            return
        
        # 创建新目录
        methodology_dir = _get_methodology_directory()
        
        # 迁移每个方法论
        migrated_count = 0
        for problem_type, content in old_data.items():
            # 为每个方法论创建文件名（使用问题类型的MD5哈希作为文件名）
            safe_filename = hashlib.md5(problem_type.encode('utf-8')).hexdigest()
            file_path = os.path.join(methodology_dir, f"{safe_filename}.json")
            
            # 保存为新格式
            with open(file_path, "w", encoding="utf-8", errors="ignore") as f:
                json.dump({
                    "problem_type": problem_type,
                    "content": content
                }, f, ensure_ascii=False, indent=2)
            
            migrated_count += 1
        
        if migrated_count > 0:
            # 备份旧文件
            backup_path = old_format_file + ".bak"
            try:
                os.rename(old_format_file, backup_path)
                PrettyOutput.print(f"已成功迁移 {migrated_count} 个方法论，旧文件已备份为 {backup_path}", OutputType.INFO)
            except Exception as e:
                PrettyOutput.print(f"备份旧文件失败，但已完成迁移: {str(e)}", OutputType.WARNING)
    except Exception as e:
        PrettyOutput.print(f"迁移方法论失败: {str(e)}", OutputType.ERROR)

def load_methodology(user_input: str) -> str:
    """
    加载方法论并构建向量索引以进行相似性搜索。
    
    参数：
        user_input: 要搜索方法论的输入文本
        
    返回：
        str: 相关的方法论提示，如果未找到方法论则返回空字符串
    """
    from yaspin import yaspin
    
    # 加载嵌入向量缓存
    global _methodology_embeddings_cache
    if not _methodology_embeddings_cache:
        with yaspin(text="加载嵌入向量缓存...", color="yellow") as spinner:
            _methodology_embeddings_cache = _load_embeddings_cache()
            spinner.text = f"加载嵌入向量缓存完成 ({len(_methodology_embeddings_cache)} 个向量)"
            spinner.ok("✅")
    
    # 检查是否需要从旧格式迁移
    with yaspin(text="检查方法论格式...", color="yellow") as spinner:
        _migrate_from_old_format()
        spinner.text = "检查方法论格式完成"
        spinner.ok("✅")
    
    # 获取方法论目录
    methodology_dir = _get_methodology_directory()
    if not os.path.exists(methodology_dir) or not glob.glob(os.path.join(methodology_dir, "*.json")):
        return ""
    
    try:
        # 获取文件的修改时间戳组合哈希，用于检测文件是否被修改
        methodology_hash = _get_methodology_files_hash()
        
        with yaspin(text="加载方法论文件...", color="yellow") as spinner:
            data = _load_all_methodologies()
            if dont_use_local_model():
                spinner.text = "加载方法论文件完成"
                spinner.ok("✅")
                return make_methodology_prompt(data)
        
        # 检查缓存的索引是否可用且方法论文件未被修改
        global _methodology_index_cache
        if _methodology_index_cache is None:
            # 尝试从文件系统加载索引缓存
            with yaspin(text="加载索引缓存...", color="yellow") as spinner:
                _methodology_index_cache = _load_index_cache()
                if _methodology_index_cache:
                    spinner.text = "加载索引缓存完成"
                    spinner.ok("✅")
                else:
                    spinner.text = "没有可用的索引缓存"
                    spinner.fail("❌")
        
        if _methodology_index_cache is not None:
            cached_index, cached_data, cache_hash = _methodology_index_cache
            if cache_hash == methodology_hash:
                # 直接使用缓存的索引和数据
                with yaspin(text="使用缓存的方法论索引...", color="yellow") as spinner:
                    methodology_index = cached_index
                    methodology_data = cached_data
                    spinner.text = "使用缓存的方法论索引完成"
                    spinner.ok("✅")
                
                with yaspin(text="加载嵌入模型...", color="yellow") as spinner:
                    embedding_model = load_embedding_model()
                    spinner.text = "加载嵌入模型完成"
                    spinner.ok("✅")
                
                with yaspin(text="执行搜索...", color="yellow") as spinner:
                    # 使用缓存构造输入文本的嵌入
                    query_embedding = _create_methodology_embedding(embedding_model, user_input)
                    k = min(3, len(methodology_data))
                    distances, indices = methodology_index.search(
                        query_embedding.reshape(1, -1), k
                    ) # type: ignore
                    spinner.text = "执行搜索完成"
                    spinner.ok("✅")
                
                with yaspin(text="处理搜索结果...", color="yellow") as spinner:
                    relevant_methodologies = {}
                    for dist, idx in zip(distances[0], indices[0]):
                        if idx >= 0:
                            similarity = 1.0 / (1.0 + float(dist))
                            methodology = methodology_data[idx]
                            if similarity >= 0.5:
                                relevant_methodologies[methodology["key"]] = methodology["value"]
                    spinner.text = "处理搜索结果完成"
                    spinner.ok("✅")
                
                if relevant_methodologies:
                    return make_methodology_prompt(relevant_methodologies)
                return make_methodology_prompt(data)
        
        # 如果缓存无效，从头构建索引
        with yaspin(text="初始化数据结构...", color="yellow") as spinner:
            methodology_data: List[Dict[str, str]] = []
            vectors: List[np.ndarray] = []
            ids: List[int] = []
            spinner.text = "初始化数据结构完成"
            spinner.ok("✅")
            
            with yaspin(text="加载嵌入模型...", color="yellow") as spinner:
                embedding_model = load_embedding_model()
                spinner.text = "加载嵌入模型完成"
                spinner.ok("✅")
            
            with yaspin(text="创建测试嵌入...", color="yellow") as spinner:
                test_embedding = _create_methodology_embedding(embedding_model, "test")
                embedding_dimension = len(test_embedding)
                spinner.text = "创建测试嵌入完成"
                spinner.ok("✅")
            
            with yaspin(text="处理方法论数据...", color="yellow") as spinner:
                for i, (key, value) in enumerate(data.items()):
                    methodology_text = f"{key}\n{value}"
                    embedding = _create_methodology_embedding(embedding_model, methodology_text)
                    vectors.append(embedding)
                    ids.append(i)
                    methodology_data.append({"key": key, "value": value})
                spinner.text = "处理方法论数据完成"
                spinner.ok("✅")
            
            if vectors:
                with yaspin(text="构建索引...", color="yellow") as spinner:
                    vectors_array = np.vstack(vectors)
                    hnsw_index = faiss.IndexHNSWFlat(embedding_dimension, 16)
                    hnsw_index.hnsw.efConstruction = 40
                    hnsw_index.hnsw.efSearch = 16
                    methodology_index = faiss.IndexIDMap(hnsw_index)
                    methodology_index.add_with_ids(vectors_array, np.array(ids)) # type: ignore
                    # 缓存构建好的索引和数据以及时间戳哈希
                    _methodology_index_cache = (methodology_index, methodology_data, methodology_hash)
                    
                    # 将索引和嵌入向量缓存保存到文件系统
                    _save_index_cache(methodology_index, methodology_data, methodology_hash)
                    
                    spinner.text = "构建索引完成"
                    spinner.ok("✅")
                
                with yaspin(text="执行搜索...", color="yellow") as spinner:
                    query_embedding = _create_methodology_embedding(embedding_model, user_input)
                    k = min(3, len(methodology_data))
                    distances, indices = methodology_index.search(
                        query_embedding.reshape(1, -1), k
                    ) # type: ignore
                    spinner.text = "执行搜索完成"
                    spinner.ok("✅")
                
                with yaspin(text="处理搜索结果...", color="yellow") as spinner:
                    relevant_methodologies = {}
                    for dist, idx in zip(distances[0], indices[0]):
                        if idx >= 0:
                            similarity = 1.0 / (1.0 + float(dist))
                            methodology = methodology_data[idx]
                            if similarity >= 0.5:
                                relevant_methodologies[methodology["key"]] = methodology["value"]
                    spinner.text = "处理搜索结果完成"
                    spinner.ok("✅")
                
                # 保存嵌入向量缓存到文件系统
                with yaspin(text="保存嵌入向量缓存...", color="yellow") as spinner:
                    if _save_embeddings_cache(_methodology_embeddings_cache):
                        spinner.text = f"保存嵌入向量缓存完成 ({len(_methodology_embeddings_cache)} 个向量)"
                        spinner.ok("✅")
                    else:
                        spinner.text = "保存嵌入向量缓存失败"
                        spinner.fail("❌")
                
                if relevant_methodologies:
                    return make_methodology_prompt(relevant_methodologies)
            return make_methodology_prompt(data)
    except Exception as e:
        PrettyOutput.print(f"加载方法论失败: {str(e)}", OutputType.ERROR)
        return ""
