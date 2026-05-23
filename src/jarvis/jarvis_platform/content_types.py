# -*- coding: utf-8 -*-
"""
多模态内容类型定义

定义了支持多模态输入所需的数据结构，包括文本、图片、音频、视频等内容块类型。
"""

from typing import TypedDict, Union, Literal
from typing_extensions import NotRequired


class TextContent(TypedDict):
    """文本内容块"""

    type: Literal["text"]
    text: str


class ImageURLContent(TypedDict):
    """图片内容块"""

    type: Literal["image_url"]
    image_url: Union[str, dict]  # URL或base64数据
    detail: NotRequired[Literal["low", "high", "auto"]]  # 图片解析精度


class AudioContent(TypedDict):
    """音频内容块"""

    type: Literal["audio"]
    audio_url: Union[str, dict]  # URL或base64数据
    format: NotRequired[str]  # mp3, wav, etc.


class VideoContent(TypedDict):
    """视频内容块"""

    type: Literal["video"]
    video_url: Union[str, dict]  # URL或base64数据
    format: NotRequired[str]  # mp4, avi, etc.


# 内容块联合类型
ContentBlock = Union[TextContent, ImageURLContent, AudioContent, VideoContent]


# 内容类型配置
CONTENT_CONFIG = {
    "max_image_size": 20 * 1024 * 1024,  # 20MB
    "max_audio_size": 25 * 1024 * 1024,  # 25MB
    "max_video_size": 100 * 1024 * 1024,  # 100MB
    "supported_image_formats": ["jpg", "jpeg", "png", "gif", "webp"],
    "supported_audio_formats": ["mp3", "wav", "ogg", "m4a"],
    "supported_video_formats": ["mp4", "avi", "mov", "webm"],
    "image_detail_default": "auto",
}
