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


# 内容块联合类型
ContentBlock = Union[TextContent, ImageURLContent]


# 内容类型配置
CONTENT_CONFIG = {
    "max_image_size": 20 * 1024 * 1024,  # 20MB
    "supported_image_formats": ["jpg", "jpeg", "png", "gif", "webp"],
    "image_detail_default": "auto",
}
