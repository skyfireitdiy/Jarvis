import os
from transformers import AutoTokenizer
from typing import List
import functools

from jarvis.jarvis_utils.output import PrettyOutput, OutputType
from jarvis.jarvis_utils.config import get_data_dir

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
        # 使用擅长处理通用文本的快速分词器
        tokenizer = load_tokenizer()
        chunks = split_text_into_chunks(text, 512)
        return sum([len(tokenizer.encode(chunk)) for chunk in chunks]) # type: ignore

    except Exception as e:
        PrettyOutput.print(f"计算token失败: {str(e)}", OutputType.WARNING)
        # 回退到基于字符的粗略估计
        return len(text) // 4  # 每个token大约4个字符的粗略估计

def split_text_into_chunks(text: str, max_length: int = 512, min_length: int = 50) -> List[str]:
    """将文本分割成带重叠窗口的块，优化RAG检索效果。

    参数：
        text: 要分割的输入文本
        max_length: 每个块的最大长度
        min_length: 每个块的最小长度（除了最后一块可能较短）

    返回：
        List[str]: 文本块列表，每个块的长度尽可能接近但不超过max_length
    """
    if not text:
        return []

    # 如果文本长度小于最大长度，直接返回整个文本
    if len(text) <= max_length:
        return [text]

    # 预处理：规范化文本，移除多余空白字符
    text = ' '.join(text.split())

    # 中英文标点符号集合，优化RAG召回的句子边界
    primary_punctuation = {'.', '!', '?', '\n', '。', '！', '？'}  # 主要句末标点
    secondary_punctuation = {'；', '：', '…', ';', ':'}  # 次级分隔符
    tertiary_punctuation = {',', '，', '、', ')', '）', ']', '】', '}', '》', '"', "'"}  # 最低优先级

    chunks = []
    start = 0

    while start < len(text):
        # 初始化结束位置为最大可能长度
        end = min(start + max_length, len(text))

        # 只有当不是最后一块且结束位置等于最大长度时，才尝试寻找句子边界
        if end < len(text) and end == start + max_length:
            # 优先查找段落边界，这对RAG特别重要
            paragraph_boundary = text.rfind('\n\n', start, end)
            if paragraph_boundary > start and paragraph_boundary < end - min_length:  # 确保不会切得太短
                end = paragraph_boundary + 2
            else:
                # 寻找句子边界，从end-1位置开始
                found_boundary = False
                best_boundary = -1

                # 扩大搜索范围以找到更好的语义边界
                search_range = min(120, end - start - min_length)  # 扩大搜索范围，但确保新块不小于min_length

                # 先尝试找主要标点（句号等）
                for i in range(end-1, max(start, end-search_range), -1):
                    if text[i] in primary_punctuation:
                        best_boundary = i
                        found_boundary = True
                        break

                # 如果没找到主要标点，再找次要标点（分号、冒号等）
                if not found_boundary:
                    for i in range(end-1, max(start, end-search_range), -1):
                        if text[i] in secondary_punctuation:
                            best_boundary = i
                            found_boundary = True
                            break

                # 最后考虑逗号和其他可能的边界
                if not found_boundary:
                    for i in range(end-1, max(start, end-search_range), -1):
                        if text[i] in tertiary_punctuation:
                            best_boundary = i
                            found_boundary = True
                            break

                # 如果找到了合适的边界且不会导致太短的块，使用它
                if found_boundary and (best_boundary - start) >= min_length:
                    end = best_boundary + 1

        # 添加当前块，并确保删除开头和结尾的空白字符
        chunk = text[start:end].strip()
        if chunk and len(chunk) >= min_length:  # 只添加符合最小长度的非空块
            chunks.append(chunk)
        elif chunk and not chunks:  # 如果是第一个块且小于最小长度，也添加它
            chunks.append(chunk)
        elif chunk:  # 如果块太小，尝试与前一个块合并
            if chunks:
                if len(chunks[-1]) + len(chunk) <= max_length * 1.1:  # 允许略微超过最大长度
                    chunks[-1] = chunks[-1] + " " + chunk
                else:
                    # 如果合并会导致太长，添加这个小块（特殊情况）
                    chunks.append(chunk)

        # 计算下一块的开始位置，调整重叠窗口大小以提高RAG检索质量
        next_start = end - int(max_length * 0.2)  # 20%的重叠窗口大小

        # 确保总是有前进，避免无限循环
        if next_start <= start:
            next_start = start + max(1, min_length // 2)

        start = next_start

    # 最后检查是否有太短的块，尝试合并相邻的短块
    if len(chunks) > 1:
        merged_chunks = []
        i = 0
        while i < len(chunks):
            current = chunks[i]
            # 如果当前块太短且不是最后一个块，尝试与下一个合并
            if len(current) < min_length and i < len(chunks) - 1:
                next_chunk = chunks[i + 1]
                if len(current) + len(next_chunk) <= max_length * 1.1:
                    merged_chunks.append(current + " " + next_chunk)
                    i += 2  # 跳过下一个块
                    continue
            merged_chunks.append(current)
            i += 1
        chunks = merged_chunks

    return chunks


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
