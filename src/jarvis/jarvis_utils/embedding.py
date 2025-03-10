import os
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from typing import List, Any, Tuple
from jarvis.jarvis_utils.output import PrettyOutput, OutputType
from jarvis.jarvis_utils.utils import split_text_into_chunks
def load_embedding_model() -> SentenceTransformer:
    """
    Load the sentence embedding model.
    
    Returns:
        SentenceTransformer: The loaded embedding model
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
    Generate embedding vector for the given text.
    
    Args:
        embedding_model: The embedding model to use
        text: The input text to embed
        
    Returns:
        np.ndarray: The embedding vector
    """
    embedding = embedding_model.encode(text, 
                                     normalize_embeddings=True,
                                     show_progress_bar=False)
    return np.array(embedding, dtype=np.float32)
def get_embedding_batch(embedding_model: Any, texts: List[str]) -> np.ndarray:
    """
    Generate embeddings for a batch of texts.
    
    Args:
        embedding_model: The embedding model to use
        texts: List of texts to embed
        
    Returns:
        np.ndarray: Stacked embedding vectors
    """
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
    """
    Generate embeddings for text chunks.
    
    Args:
        embedding_model: The embedding model to use
        text: The input text to process
        
    Returns:
        List[np.ndarray]: List of embedding vectors for each chunk
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
    Load the tokenizer for text processing.
    
    Returns:
        AutoTokenizer: The loaded tokenizer
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
    Load the reranking model and tokenizer.
    
    Returns:
        Tuple[AutoModelForSequenceClassification, AutoTokenizer]: The loaded model and tokenizer
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