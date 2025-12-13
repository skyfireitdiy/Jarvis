# -*- coding: utf-8 -*-
import os
from pathlib import Path
from typing import List

from jarvis.jarvis_utils.output import PrettyOutput

# 设置tiktoken缓存目录
script_dir = Path(__file__).parent
tiktoken_cache_dir = script_dir / "../jarvis_data/tiktoken"
os.makedirs(tiktoken_cache_dir, exist_ok=True)
os.environ["TIKTOKEN_CACHE_DIR"] = str(tiktoken_cache_dir.absolute())


def get_context_token_count(text: str) -> int:
    """使用tiktoken获取文本的token数量。

    参数：
        text: 要计算token的输入文本

    返回：
        int: 文本中的token数量
    """
    # 防御性检查：入参为 None 或空字符串时直接返回 0
    if text is None or text == "":
        return 0
    try:
        import tiktoken

        encoding = tiktoken.get_encoding("cl100k_base")
        # 调整token计算为原来的10/7倍
        return int(len(encoding.encode(text)) * 10 / 7)
    except Exception as e:
        PrettyOutput.auto_print(f"⚠️ 计算token失败: {str(e)}")
        return int(
            len(text) // 4 * 10 / 7
        )  # 每个token大约4个字符的粗略估计，调整为10/7倍


def split_text_into_chunks(
    text: str, max_length: int = 512, min_length: int = 50
) -> List[str]:
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
            chunk = text[i : i + chunk_size]
            chunk_tokens = get_context_token_count(chunk)

            # 如果当前块加上新块会超过最大长度，且当前块已经达到最小长度，则保存当前块
            if (
                current_tokens + chunk_tokens > max_length
                and current_tokens >= min_length
            ):
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
        PrettyOutput.auto_print(f"⚠️ 文本分割失败: {str(e)}")
        # 发生错误时回退到简单的字符分割
        return [text[i : i + max_length] for i in range(0, len(text), max_length)]
