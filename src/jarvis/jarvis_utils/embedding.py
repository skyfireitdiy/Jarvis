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


def get_multimodal_token_count(content) -> int:
    """
    计算多模态内容的 token 数量

    Args:
        content: 可以是字符串或多模态内容列表

    Returns:
        int: token 数量
    """
    if isinstance(content, str):
        return get_context_token_count(content)

    if not isinstance(content, list):
        return 0

    total_tokens = 0
    for block in content:
        if not isinstance(block, dict):
            continue

        block_type = block.get("type")

        if block_type == "text":
            # 文本内容：使用 tiktoken 计算
            text = block.get("text", "")
            total_tokens += get_context_token_count(text)

        elif block_type == "image_url":
            # 图片内容：根据分辨率估算 token
            total_tokens += _estimate_image_tokens(block)

        else:
            # 未知类型：基础 token 估算
            total_tokens += 50

    return total_tokens


def _estimate_image_tokens(image_block: dict) -> int:
    """
    估算图片的 token 数量

    基于 OpenAI 和 Claude 的图片 token 计算规则：
    - OpenAI: 基于分片系统，512x512 分片约 170 tokens + 基础 85 tokens
    - Claude: 基于分辨率，约 1,380 tokens/百万像素

    Args:
        image_block: 图片内容块

    Returns:
        int: 估算的 token 数量
    """
    # 默认 token 估算（无法获取分辨率时）
    default_tokens = 85  # OpenAI 基础 token

    try:
        # 尝试从 base64 数据获取图片信息
        image_url = image_block.get("image_url", {})
        if isinstance(image_url, dict):
            url = image_url.get("url", "")
        else:
            url = str(image_url)

        # 如果是 base64 数据，尝试解析图片头信息
        if url.startswith("data:image/"):
            # 从 data URL 中提取 base64 数据
            header, data = url.split(",", 1)
            # 这里可以进一步解析图片尺寸，但需要 PIL 等库
            # 暂时返回默认值
            return default_tokens

        # 如果是 URL，无法直接获取尺寸，返回默认值
        return default_tokens

    except Exception:
        return default_tokens
