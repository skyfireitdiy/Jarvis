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
    为一批文本生成嵌入向量，使用高效的批处理。
    
    参数：
        embedding_model: 使用的嵌入模型
        prefix: 进度条前缀
        texts: 要嵌入的文本列表
        spinner: 可选的进度指示器
        batch_size: 批处理大小，更大的值可能更快但需要更多内存
        
    返回：
        np.ndarray: 堆叠的嵌入向量
    """
    try:
        # 预处理：将所有文本分块
        all_chunks = []
        chunk_indices = []  # 跟踪每个原始文本对应的块索引
        
        for i, text in enumerate(texts):
            if spinner:
                spinner.text = f"{prefix} 预处理中 ({i+1}/{len(texts)}) ..."
            
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
            # 直接使用模型的批处理能力
            batch_vectors = embedding_model.encode(batch, 
                                                normalize_embeddings=True,
                                                show_progress_bar=False,
                                                convert_to_numpy=True)
            
            if isinstance(batch_vectors, list):
                all_vectors.extend(batch_vectors)
            else:
                # 如果返回的是单个数组，拆分为列表
                for j in range(len(batch)):
                    all_vectors.append(batch_vectors[j])
        
        # 组织结果到原始文本顺序
        result_vectors = []
        for start_idx, end_idx in chunk_indices:
            text_vectors = all_vectors[start_idx:end_idx]
            result_vectors.extend(text_vectors)
        
        return np.vstack(result_vectors)
    
    except Exception as e:
        PrettyOutput.print(f"批量嵌入失败: {str(e)}", OutputType.ERROR)
        return np.zeros((0, embedding_model.get_sentence_embedding_dimension()), dtype=np.float32)
    
def split_text_into_chunks(text: str, max_length: int = 512) -> List[str]:
    """将文本分割成带重叠窗口的块。
    
    参数：
        text: 要分割的输入文本
        max_length: 每个块的最大长度
        
    返回：
        List[str]: 文本块列表
    """
    if not text or len(text) <= max_length:
        return [text] if text else []
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_length
        # 找到最近的句子边界
        if end < len(text):
            # 优化：先检查一个小范围内的句子边界，提高性能
            search_range = min(50, end - start)
            boundary_found = False
            
            for i in range(end, end - search_range, -1):
                if i < len(text) and text[i] in {'.', '!', '?', '\n'}:
                    end = i + 1  # 包含标点符号
                    boundary_found = True
                    break
            
            if not boundary_found:
                # 如果小范围内没找到，再搜索完整范围
                while end > start and end < len(text) and text[end] not in {'.', '!', '?', '\n'}:
                    end -= 1
                if end == start:  # 未找到标点，强制分割
                    end = start + max_length
                else:
                    end += 1  # 包含标点符号
        
        chunk = text[start:end]
        chunks.append(chunk)
        # 重叠20%的窗口
        start = end - int(max_length * 0.2)
    
    return chunks

def get_embedding_with_chunks(embedding_model: Any, text: str, batch_size: int = 8) -> List[np.ndarray]:
    """
    为文本块生成嵌入向量，使用批处理提高效率。
    
    参数：
        embedding_model: 使用的嵌入模型
        text: 要处理的输入文本
        batch_size: 批处理大小
        
    返回：
        List[np.ndarray]: 每个块的嵌入向量列表
    """
    chunks = split_text_into_chunks(text, 512)
    if not chunks:
        return []
    
    # 使用批处理模式一次性处理多个块
    vectors = []
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        batch_embeddings = embedding_model.encode(batch, 
                                              normalize_embeddings=True,
                                              show_progress_bar=False,
                                              convert_to_numpy=True)
        
        # 处理返回结果，确保是向量列表
        if len(batch) == 1:
            vectors.append(batch_embeddings)
        else:
            for emb in batch_embeddings:
                vectors.append(emb)
    
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
