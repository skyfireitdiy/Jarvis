# -*- coding: utf-8 -*-
"""
多模态内容处理器

提供多模态内容的验证、编码、压缩等功能。
"""

import base64
import os
from typing import List, Union

from jarvis.jarvis_platform.content_types import (
    ContentBlock,
    CONTENT_CONFIG,
)
from jarvis.jarvis_utils.output import PrettyOutput


class ContentProcessor:
    """多模态内容处理器"""

    @staticmethod
    def process_message(message: Union[str, List[ContentBlock]]) -> List[ContentBlock]:
        """
        统一处理多模态输入，将字符串转换为ContentBlock列表

        Args:
            message: 用户输入的消息

        Returns:
            List[ContentBlock]: 标准化后的内容块列表

        Raises:
            ValueError: 内容格式不合法
            TypeError: 不支持的内容类型
        """
        # 如果是字符串，转换为文本内容块
        if isinstance(message, str):
            return [{"type": "text", "text": message}]

        # 如果是列表，验证并处理每个内容块
        if isinstance(message, list):
            processed_blocks: List[ContentBlock] = []
            for block in message:
                if not isinstance(block, dict):
                    raise TypeError(f"内容块必须是字典类型，实际类型: {type(block)}")

                # 验证内容块
                ContentProcessor.validate_content(block)

                # 处理文件路径
                processed_block = ContentProcessor._process_file_path(block)
                processed_blocks.append(processed_block)

            return processed_blocks

        raise TypeError(f"不支持的消息类型: {type(message)}")

    @staticmethod
    def validate_content(content: ContentBlock) -> bool:
        """
        验证内容块的合法性

        Args:
            content: 待验证的内容块

        Returns:
            bool: 验证是否通过

        Raises:
            ValueError: 验证失败原因
        """
        if not isinstance(content, dict):
            raise ValueError("内容块必须是字典类型")

        content_type = content.get("type")
        if not content_type:
            raise ValueError("内容块必须包含 'type' 字段")

        # 验证文本内容
        if content_type == "text":
            text_value = content.get("text")
            if text_value is None:
                raise ValueError("文本内容块必须包含 'text' 字段")
            if not isinstance(text_value, str):
                raise ValueError("text 字段必须是字符串类型")
            return True

        # 验证图片内容
        if content_type == "image_url":
            if content.get("image_url") is None:
                raise ValueError("图片内容块必须包含 'image_url' 字段")
            return True

        # 验证音频内容
        if content_type == "audio":
            if content.get("audio_url") is None:
                raise ValueError("音频内容块必须包含 'audio_url' 字段")
            return True

        # 验证视频内容
        if content_type == "video":
            if content.get("video_url") is None:
                raise ValueError("视频内容块必须包含 'video_url' 字段")
            return True

        raise ValueError(f"不支持的内容类型: {content_type}")

    @staticmethod
    def _process_file_path(block: ContentBlock) -> ContentBlock:
        """
        处理文件路径，将本地文件路径转换为base64编码

        Args:
            block: 内容块

        Returns:
            ContentBlock: 处理后的内容块
        """
        content_type = block.get("type")

        # 处理图片文件路径
        if content_type == "image_url":
            image_url = block.get("image_url")
            if isinstance(image_url, str) and os.path.exists(image_url):
                # 读取文件并转换为base64
                base64_data = ContentProcessor._encode_file_to_base64(
                    image_url, "image"
                )
                if base64_data:
                    # 创建新的内容块，避免修改原始数据
                    new_block: dict = dict(block)
                    new_block["image_url"] = base64_data
                    return new_block  # type: ignore

        # 处理音频文件路径
        if content_type == "audio":
            audio_url = block.get("audio_url")
            if isinstance(audio_url, str) and os.path.exists(audio_url):
                base64_data = ContentProcessor._encode_file_to_base64(
                    audio_url, "audio"
                )
                if base64_data:
                    new_block: dict = dict(block)
                    new_block["audio_url"] = base64_data
                    return new_block  # type: ignore

        # 处理视频文件路径
        if content_type == "video":
            video_url = block.get("video_url")
            if isinstance(video_url, str) and os.path.exists(video_url):
                base64_data = ContentProcessor._encode_file_to_base64(
                    video_url, "video"
                )
                if base64_data:
                    new_block: dict = dict(block)
                    new_block["video_url"] = base64_data
                    return new_block  # type: ignore

        return block

    @staticmethod
    def _encode_file_to_base64(file_path: str, file_type: str) -> Union[str, None]:
        """
        将文件编码为base64字符串

        Args:
            file_path: 文件路径
            file_type: 文件类型 (image/audio/video)

        Returns:
            Union[str, None]: base64编码字符串，失败返回None
        """
        try:
            # 检查文件大小
            file_size = os.path.getsize(file_path)
            max_size_key = f"max_{file_type}_size"
            max_size = CONTENT_CONFIG.get(max_size_key, 50 * 1024 * 1024)  # 默认50MB
            # 确保max_size是整数
            if not isinstance(max_size, int):
                max_size = 50 * 1024 * 1024

            if file_size > max_size:
                PrettyOutput.auto_print(
                    f"⚠️ 文件 {file_path} 大小超过限制 ({file_size} > {max_size})"
                )
                return None

            # 读取文件并编码
            with open(file_path, "rb") as f:
                file_data = f.read()
                base64_data = base64.b64encode(file_data).decode("utf-8")

                # 获取MIME类型
                mime_type = ContentProcessor._get_mime_type(file_path, file_type)
                return f"data:{mime_type};base64,{base64_data}"

        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 文件编码失败: {str(e)}")
            return None

    @staticmethod
    def _get_mime_type(file_path: str, file_type: str) -> str:
        """
        获取文件的MIME类型

        Args:
            file_path: 文件路径
            file_type: 文件类型

        Returns:
            str: MIME类型
        """
        ext = os.path.splitext(file_path)[1].lower().lstrip(".")

        mime_map = {
            "image": {
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "png": "image/png",
                "gif": "image/gif",
                "webp": "image/webp",
            },
            "audio": {
                "mp3": "audio/mpeg",
                "wav": "audio/wav",
                "ogg": "audio/ogg",
                "m4a": "audio/mp4",
            },
            "video": {
                "mp4": "video/mp4",
                "avi": "video/x-msvideo",
                "mov": "video/quicktime",
                "webm": "video/webm",
            },
        }

        return mime_map.get(file_type, {}).get(ext, "application/octet-stream")
