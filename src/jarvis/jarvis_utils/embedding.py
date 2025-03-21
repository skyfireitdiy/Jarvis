import os
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from typing import List, Any, Optional, Tuple
import functools

from yaspin.api import Yaspin
from jarvis.jarvis_utils.output import PrettyOutput, OutputType

# 全局缓存，避免重复加载模型
_global_models = {}
_global_tokenizers = {}

def get_context_token_count(text: str) -> int:
    """使用分词器获取文本的token数量。
    
    参数：
        text: 要计算token的输入文本
        
    返回：
        int: 文本中的token数量
    """
    try:
        # 使用擅长处理通用文本的快速分词器
        tokenizer = load_tokenizer()
        chunks = split_text_into_chunks(text, 512)
        return sum([len(tokenizer.encode(chunk)) for chunk in chunks]) # type: ignore
        
    except Exception as e:
        PrettyOutput.print(f"计算token失败: {str(e)}", OutputType.WARNING)
        # 回退到基于字符的粗略估计
        return len(text) // 4  # 每个token大约4个字符的粗略估计

@functools.lru_cache(maxsize=1)
def load_embedding_model() -> SentenceTransformer:
    """
    加载句子嵌入模型，使用缓存避免重复加载。
    
    返回：
        SentenceTransformer: 加载的嵌入模型
    """
    model_name = "BAAI/bge-m3"
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    
    # 检查全局缓存中是否已有模型
    if model_name in _global_models:
        return _global_models[model_name]
    
    try:
        embedding_model = SentenceTransformer(
            model_name,
            cache_folder=cache_dir,
            local_files_only=True
        )
    except Exception:
        embedding_model = SentenceTransformer(
            model_name,
            cache_folder=cache_dir,
            local_files_only=False
        )
    
    # 如果可用，将模型移到GPU上
    if torch.cuda.is_available():
        embedding_model.to(torch.device("cuda"))
    
    # 保存到全局缓存
    _global_models[model_name] = embedding_model
    
    return embedding_model

def get_embedding(embedding_model: Any, text: str) -> np.ndarray:
    """
    为给定文本生成嵌入向量。
    
    参数：
        embedding_model: 使用的嵌入模型
        text: 要嵌入的输入文本
        
    返回：
        np.ndarray: 嵌入向量
    """
    embedding = embedding_model.encode(text, 
                                     normalize_embeddings=True,
                                     show_progress_bar=False)
    return np.array(embedding, dtype=np.float32)

def get_embedding_batch(embedding_model: Any, prefix: str, texts: List[str], spinner: Optional[Yaspin] = None, batch_size: int = 8) -> np.ndarray:
    """
    为一批文本生成嵌入向量，使用高效的批处理，针对RAG优化。
    
    参数：
        embedding_model: 使用的嵌入模型
        prefix: 进度条前缀
        texts: 要嵌入的文本列表
        spinner: 可选的进度指示器
        batch_size: 批处理大小，更大的值可能更快但需要更多内存
        
    返回：
        np.ndarray: 堆叠的嵌入向量
    """
    # 简单嵌入缓存，避免重复计算相同文本块
    embedding_cache = {}
    cache_hits = 0
    
    try:
        # 预处理：将所有文本分块
        all_chunks = []
        chunk_indices = []  # 跟踪每个原始文本对应的块索引
        
        for i, text in enumerate(texts):
            if spinner:
                spinner.text = f"{prefix} 预处理中 ({i+1}/{len(texts)}) ..."
            
            # 预处理文本：移除多余空白，规范化
            text = ' '.join(text.split()) if text else ""
            
            # 使用更优化的分块函数
            chunks = split_text_into_chunks(text, 512)
            start_idx = len(all_chunks)
            all_chunks.extend(chunks)
            end_idx = len(all_chunks)
            chunk_indices.append((start_idx, end_idx))
        
        if not all_chunks:
            return np.zeros((0, embedding_model.get_sentence_embedding_dimension()), dtype=np.float32)
        
        # 批量处理所有块
        all_vectors = []
        for i in range(0, len(all_chunks), batch_size):
            if spinner:
                spinner.text = f"{prefix} 批量处理嵌入 ({i+1}/{len(all_chunks)}) ..."
            
            batch = all_chunks[i:i+batch_size]
            batch_to_process = []
            batch_indices = []
            
            # 检查缓存，避免重复计算
            for j, chunk in enumerate(batch):
                chunk_hash = hash(chunk)
                if chunk_hash in embedding_cache:
                    all_vectors.append(embedding_cache[chunk_hash])
                    cache_hits += 1
                else:
                    batch_to_process.append(chunk)
                    batch_indices.append(j)
            
            if batch_to_process:
                # 对未缓存的块处理
                batch_vectors = embedding_model.encode(
                    batch_to_process, 
                    normalize_embeddings=True,
                    show_progress_bar=False,
                    convert_to_numpy=True
                )
                
                # 处理结果并更新缓存
                if len(batch_to_process) == 1:
                    vec = batch_vectors
                    chunk_hash = hash(batch_to_process[0])
                    embedding_cache[chunk_hash] = vec
                    all_vectors.append(vec)
                else:
                    for j, vec in enumerate(batch_vectors):
                        chunk_hash = hash(batch_to_process[j])
                        embedding_cache[chunk_hash] = vec
                        all_vectors.append(vec)
        
        # 组织结果到原始文本顺序
        result_vectors = []
        for start_idx, end_idx in chunk_indices:
            text_vectors = []
            for j in range(start_idx, end_idx):
                if j < len(all_vectors):
                    text_vectors.append(all_vectors[j])
            
            if text_vectors:
                # 当一个文本被分成多个块时，采用加权平均
                if len(text_vectors) > 1:
                    # 针对RAG优化：对多个块进行加权平均，前面的块权重略高
                    weights = np.linspace(1.0, 0.8, len(text_vectors))
                    weights = weights / weights.sum()  # 归一化权重
                    
                    # 应用权重并求和
                    weighted_sum = np.zeros_like(text_vectors[0])
                    for i, vec in enumerate(text_vectors):
                        # 确保向量形状一致，处理可能的维度不匹配问题
                        vec_array = np.asarray(vec).reshape(weighted_sum.shape)
                        weighted_sum += vec_array * weights[i]
                    
                    # 归一化结果向量
                    norm = np.linalg.norm(weighted_sum)
                    if norm > 0:
                        weighted_sum = weighted_sum / norm
                    
                    result_vectors.append(weighted_sum)
                else:
                    # 单块直接使用
                    result_vectors.append(text_vectors[0])
        
        if spinner and cache_hits > 0:
            spinner.text = f"{prefix} 缓存命中: {cache_hits}/{len(all_chunks)} 块"
        
        return np.vstack(result_vectors)
    
    except Exception as e:
        PrettyOutput.print(f"批量嵌入失败: {str(e)}", OutputType.ERROR)
        return np.zeros((0, embedding_model.get_sentence_embedding_dimension()), dtype=np.float32)
    
def split_text_into_chunks(text: str, max_length: int = 512) -> List[str]:
    """将文本分割成带重叠窗口的块，优化RAG检索效果。
    
    参数：
        text: 要分割的输入文本
        max_length: 每个块的最大长度
        
    返回：
        List[str]: 文本块列表，每个块的长度尽可能接近但不超过max_length
    """
    if not text or len(text) <= max_length:
        return [text] if text else []
    
    # 预处理：规范化文本，移除多余空白字符
    text = ' '.join(text.split())
    
    # 中英文标点符号集合，优化RAG召回的句子边界
    punctuation_marks = {
        '.', '!', '?', '\n',  # 英文标点
        '。', '！', '？',     # 中文句末标点
        '；', '：', '…',      # 中文次级分隔符
        ',', '，', '、',      # 逗号、顿号（次优先级）
        ')', '）', ']', '】', '}', '》', '"', "'", # 闭合标点（最低优先级）
    }
    
    chunks = []
    start = 0
    
    while start < len(text):
        # 初始化结束位置为最大可能长度
        end = min(start + max_length, len(text))
        
        # 只有当不是最后一块且结束位置等于最大长度时，才尝试寻找句子边界
        if end < len(text) and end == start + max_length:
            # 优先查找段落边界，这对RAG特别重要
            paragraph_boundary = text.rfind('\n\n', start, end)
            if paragraph_boundary > start and paragraph_boundary < end - 20:  # 确保不会切得太短
                end = paragraph_boundary + 2
            else:
                # 向前寻找句子边界，从end-1位置开始
                found_boundary = False
                best_boundary = -1
                
                # 扩大搜索范围以找到更好的语义边界
                search_range = min(80, end - start)
                
                # 先尝试找主要标点（句号等）
                for i in range(end-1, max(start, end-search_range), -1):
                    if text[i] in {'。', '！', '？', '.', '!', '?', '\n'}:
                        best_boundary = i
                        found_boundary = True
                        break
                
                # 如果没找到主要标点，再找次要标点（分号、冒号等）
                if not found_boundary:
                    for i in range(end-1, max(start, end-search_range), -1):
                        if text[i] in {'；', '：', '…', ';', ':'}:
                            best_boundary = i
                            found_boundary = True
                            break
                
                # 最后考虑逗号和其他可能的边界
                if not found_boundary:
                    for i in range(end-1, max(start, end-search_range), -1):
                        if text[i] in {'，', ',', '、', ')', '）', ']', '】', '}', '》', '"', "'"}:
                            best_boundary = i
                            found_boundary = True
                            break
                
                # 如果找到了任何边界，使用它
                if found_boundary:
                    end = best_boundary + 1
        
        # 添加当前块，并确保删除开头和结尾的空白字符
        chunk = text[start:end].strip()
        if chunk:  # 只添加非空块
            chunks.append(chunk)
        
        # 计算下一块的开始位置，调整重叠窗口大小以提高RAG检索质量
        next_start = end - int(max_length * 0.25)  # 增加重叠到25%以提高上下文连贯性
        
        # 确保总是有前进，避免无限循环
        if next_start <= start:
            next_start = start + 1
            
        start = next_start
    
    return chunks

def get_embedding_with_chunks(embedding_model: Any, text: str, batch_size: int = 8) -> List[np.ndarray]:
    """
    为文本块生成嵌入向量，针对RAG优化，使用批处理提高效率。
    
    参数：
        embedding_model: 使用的嵌入模型
        text: 要处理的输入文本
        batch_size: 批处理大小
        
    返回：
        List[np.ndarray]: 每个块的嵌入向量列表
    """
    # 预处理文本
    text = ' '.join(text.split()) if text else ""
    chunks = split_text_into_chunks(text, 512)
    if not chunks:
        return []
    
    # 简单缓存机制，避免重复计算相同文本的嵌入
    embedding_cache = {}
    
    # 使用批处理模式一次性处理多个块
    vectors = []
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        batch_to_process = []
        batch_indices = {}  # 记录原始索引
        
        # 检查缓存
        for j, chunk in enumerate(batch):
            chunk_hash = hash(chunk)
            if chunk_hash in embedding_cache:
                vectors.append(embedding_cache[chunk_hash])
            else:
                batch_indices[len(batch_to_process)] = j
                batch_to_process.append(chunk)
        
        if batch_to_process:
            # 处理未缓存的块
            batch_embeddings = embedding_model.encode(
                batch_to_process, 
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True
            )
            
            # 处理返回结果，确保是向量列表
            if len(batch_to_process) == 1:
                vec = batch_embeddings
                chunk_hash = hash(batch_to_process[0])
                embedding_cache[chunk_hash] = vec
                
                # 找到原始位置插入
                orig_idx = batch_indices[0]
                while len(vectors) <= i + orig_idx:
                    vectors.append(None)
                vectors[i + orig_idx] = vec
            else:
                for j, vec in enumerate(batch_embeddings):
                    chunk_hash = hash(batch_to_process[j])
                    embedding_cache[chunk_hash] = vec
                    
                    # 找到原始位置插入
                    if j in batch_indices:
                        orig_idx = batch_indices[j]
                        while len(vectors) <= i + orig_idx:
                            vectors.append(None)
                        vectors[i + orig_idx] = vec
    
    # 移除可能的None值
    vectors = [v for v in vectors if v is not None]
    
    # 针对RAG的优化：调整段落权重
    if len(vectors) > 1:
        # 前面的块通常包含更重要的信息，给予更高权重
        adjusted_vectors = []
        for i, vec in enumerate(vectors):
            # 根据位置赋予衰减权重（前面的段落权重更高）
            position_weight = 1.0 - (i * 0.05)  # 最多衰减0.05每个位置
            position_weight = max(0.7, position_weight)  # 确保最小权重为0.7
            
            # 应用权重并重新归一化
            weighted_vec = vec * position_weight
            norm = np.linalg.norm(weighted_vec)
            if norm > 0:
                weighted_vec = weighted_vec / norm
            
            adjusted_vectors.append(weighted_vec)
        return adjusted_vectors
    
    return vectors

@functools.lru_cache(maxsize=1)
def load_tokenizer() -> AutoTokenizer:
    """
    加载用于文本处理的分词器，使用缓存避免重复加载。
    
    返回：
        AutoTokenizer: 加载的分词器
    """
    model_name = "gpt2"
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    
    # 检查全局缓存
    if model_name in _global_tokenizers:
        return _global_tokenizers[model_name]
    
    try:
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            local_files_only=True
        )
    except Exception:
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            local_files_only=False
        )
    
    # 保存到全局缓存
    _global_tokenizers[model_name] = tokenizer
    
    return tokenizer # type: ignore

@functools.lru_cache(maxsize=1)
def load_rerank_model() -> Tuple[AutoModelForSequenceClassification, AutoTokenizer]:
    """
    加载重排序模型和分词器，使用缓存避免重复加载。
    
    返回：
        Tuple[AutoModelForSequenceClassification, AutoTokenizer]: 加载的模型和分词器
    """
    model_name = "BAAI/bge-reranker-v2-m3"
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    
    # 检查全局缓存
    key = f"rerank_{model_name}"
    if key in _global_models and f"{key}_tokenizer" in _global_tokenizers:
        return _global_models[key], _global_tokenizers[f"{key}_tokenizer"]
    
    PrettyOutput.print(f"加载重排序模型: {model_name}...", OutputType.INFO)
    
    try:
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            local_files_only=True
        )
        model = AutoModelForSequenceClassification.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            local_files_only=True
        )
    except Exception:
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            local_files_only=False
        )
        model = AutoModelForSequenceClassification.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            local_files_only=False
        )
    
    if torch.cuda.is_available():
        model = model.cuda()
    model.eval()
    
    # 保存到全局缓存
    _global_models[key] = model
    _global_tokenizers[f"{key}_tokenizer"] = tokenizer
    
    return model, tokenizer # type: ignore
