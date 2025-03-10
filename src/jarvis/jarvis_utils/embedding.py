import os
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from typing import List, Any
from ..jarvis_utils.output import PrettyOutput, OutputType
from ..jarvis_utils.utils import split_text_into_chunks
def load_embedding_model():
    """Load sentence embedding model"""
    model_name = "BAAI/bge-m3"
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    
    try:
        # Load model
        embedding_model = SentenceTransformer(
            model_name,
            cache_folder=cache_dir,
            local_files_only=True
        )
    except Exception as e:
        # Load model
        embedding_model = SentenceTransformer(
            model_name,
            cache_folder=cache_dir,
            local_files_only=False
        )
    
    return embedding_model
def get_embedding(embedding_model: Any, text: str) -> np.ndarray:
    """Get the vector representation of the text"""
    embedding = embedding_model.encode(text, 
                                     normalize_embeddings=True,
                                     show_progress_bar=False)
    return np.array(embedding, dtype=np.float32)
def get_embedding_batch(embedding_model: Any, texts: List[str]) -> np.ndarray:
    """Get embeddings for a batch of texts efficiently"""
    try:
        all_vectors = []
        for text in texts:
            vectors = get_embedding_with_chunks(embedding_model, text)
            all_vectors.extend(vectors)
        return np.vstack(all_vectors)
    except Exception as e:
        PrettyOutput.print(f"批量嵌入失败: {str(e)}", OutputType.ERROR)
        return np.zeros((0, embedding_model.get_sentence_embedding_dimension()), dtype=np.float32)
def get_embedding_with_chunks(embedding_model: Any, text: str) -> List[np.ndarray]:
    """Get embeddings for text chunks"""
    chunks = split_text_into_chunks(text, 512)
    if not chunks:
        return []
    
    vectors = []
    for chunk in chunks:
        vector = get_embedding(embedding_model, chunk)
        vectors.append(vector)
    return vectors
def load_tokenizer():
    """Load tokenizer"""
    model_name = "gpt2"
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    
    try:
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            local_files_only=True
        )
    except Exception as e:
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            local_files_only=False
        )
    
    return tokenizer
def load_rerank_model():
    """Load reranking model"""
    model_name = "BAAI/bge-reranker-v2-m3"
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    
    PrettyOutput.print(f"加载重排序模型: {model_name}...", OutputType.INFO)
    
    try:
        # Load model and tokenizer
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
    except Exception as e:
        # Load model and tokenizer
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
    
    # Use GPU if available
    if torch.cuda.is_available():
        model = model.cuda()
    model.eval()
    
    return model, tokenizer