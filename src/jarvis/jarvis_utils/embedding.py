import os
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from typing import List, Any, Optional, Tuple

from yaspin.api import Yaspin
from jarvis.jarvis_utils.output import PrettyOutput, OutputType

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

def load_embedding_model() -> SentenceTransformer:
    """
    加载句子嵌入模型。
    
    返回：
        SentenceTransformer: 加载的嵌入模型
    """
    model_name = "BAAI/bge-m3"
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    
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

def get_embedding_batch(embedding_model: Any, prefix: str,texts: List[str], spinner: Optional[Yaspin] = None) -> np.ndarray:
    """
    为一批文本生成嵌入向量。
    
    参数：
        embedding_model: 使用的嵌入模型
        texts: 要嵌入的文本列表
        
    返回：
        np.ndarray: 堆叠的嵌入向量
    """
    try:
        all_vectors = []
        for index, text in enumerate(texts):
            if spinner:
                spinner.text = f"{prefix} 处理中 ({index+1}/{len(texts)}) ..."
            vectors = get_embedding_with_chunks(embedding_model, text)
            all_vectors.extend(vectors)
        return np.vstack(all_vectors)
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
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_length
        # 找到最近的句子边界
        if end < len(text):
            while end > start and text[end] not in {'.', '!', '?', '\n'}:
                end -= 1
            if end == start:  # 未找到标点，强制分割
                end = start + max_length
        chunk = text[start:end]
        chunks.append(chunk)
        # 重叠20%的窗口
        start = end - int(max_length * 0.2)
    return chunks

def get_embedding_with_chunks(embedding_model: Any, text: str) -> List[np.ndarray]:
    """
    为文本块生成嵌入向量。
    
    参数：
        embedding_model: 使用的嵌入模型
        text: 要处理的输入文本
        
    返回：
        List[np.ndarray]: 每个块的嵌入向量列表
    """
    chunks = split_text_into_chunks(text, 512)
    if not chunks:
        return []
    
    vectors = []
    for chunk in chunks:
        vector = get_embedding(embedding_model, chunk)
        vectors.append(vector)
    return vectors

def load_tokenizer() -> AutoTokenizer:
    """
    加载用于文本处理的分词器。
    
    返回：
        AutoTokenizer: 加载的分词器
    """
    model_name = "gpt2"
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    
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
    
    return tokenizer # type: ignore

def load_rerank_model() -> Tuple[AutoModelForSequenceClassification, AutoTokenizer]:
    """
    加载重排序模型和分词器。
    
    返回：
        Tuple[AutoModelForSequenceClassification, AutoTokenizer]: 加载的模型和分词器
    """
    model_name = "BAAI/bge-reranker-v2-m3"
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    
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
    
    return model, tokenizer # type: ignore
