# -*- coding: utf-8 -*-
import functools
import os
from typing import List

from transformers import AutoTokenizer

from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

# 全局缓存，避免重复加载模型
_global_tokenizers = {}

def get_context_token_count(text: str) -> int:
    """使用分词器获取文本的token数量。

    参数：
        text: 要计算token的输入文本

    返回：
        int: 文本中的token数量
    """
    try:
        tokenizer = load_tokenizer()
        # 分批处理长文本，确保不超过模型最大长度
        total_tokens = 0
        chunk_size = 100  # 每次处理100个字符，避免超过模型最大长度（考虑到中文字符可能被编码成多个token）
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            tokens = tokenizer.encode(chunk)  # type: ignore
            total_tokens += len(tokens)
        return total_tokens
    except Exception as e:
        PrettyOutput.print(f"计算token失败: {str(e)}", OutputType.WARNING)
        return len(text) // 4  # 每个token大约4个字符的粗略估计

def split_text_into_chunks(text: str, max_length: int = 512, min_length: int = 50) -> List[str]:
    """将文本分割成块，基于token数量进行切割。

    参数：
        text: 要分割的输入文本
        max_length: 每个块的最大token数量
        min_length: 每个块的最小token数量（除了最后一块可能较短）

    返回：
        List[str]: 文本块列表，每个块的token数量不超过max_length且不小于min_length
    """
    if not text:
        return []

    try:
        chunks = []
        current_chunk = ""
        current_tokens = 0
        
        # 按较大的块处理文本，避免破坏token边界
        chunk_size = 50  # 每次处理50个字符
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            chunk_tokens = get_context_token_count(chunk)
            
            # 如果当前块加上新块会超过最大长度，且当前块已经达到最小长度，则保存当前块
            if current_tokens + chunk_tokens > max_length and current_tokens >= min_length:
                chunks.append(current_chunk)
                current_chunk = chunk
                current_tokens = chunk_tokens
            else:
                current_chunk += chunk
                current_tokens += chunk_tokens

        # 处理最后一个块
        if current_chunk:
            chunks.append(current_chunk)  # 直接添加最后一个块，无论长度如何

        return chunks

    except Exception as e:
        PrettyOutput.print(f"文本分割失败: {str(e)}", OutputType.WARNING)
        # 发生错误时回退到简单的字符分割
        return [text[i:i + max_length] for i in range(0, len(text), max_length)]


@functools.lru_cache(maxsize=1)
def load_tokenizer() -> AutoTokenizer:
    """
    加载用于文本处理的分词器，使用缓存避免重复加载。

    返回：
        AutoTokenizer: 加载的分词器
    """
    model_name = "gpt2"
    cache_dir = os.path.join(get_data_dir(), "huggingface", "hub")

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
