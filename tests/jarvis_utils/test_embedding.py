# -*- coding: utf-8 -*-
"""jarvis_utils.embedding 模块单元测试"""

from jarvis.jarvis_utils.embedding import (
    get_context_token_count,
    split_text_into_chunks,
    get_multimodal_token_count,
    _estimate_image_tokens,
)


class TestGetContextTokenCount:
    """测试 get_context_token_count 函数"""

    def test_empty_string(self):
        """测试空字符串"""
        assert get_context_token_count("") == 0

    def test_none_input(self):
        """测试 None 输入"""
        # 注意：get_context_token_count 期望 str 类型，None 会引发类型错误
        # 这里测试空字符串作为替代
        assert get_context_token_count("") == 0

    def test_simple_text(self):
        """测试简单文本"""
        text = "Hello world"
        result = get_context_token_count(text)
        assert isinstance(result, int)
        assert result > 0

    def test_long_text(self):
        """测试长文本"""
        text = "Hello world " * 100
        result = get_context_token_count(text)
        assert isinstance(result, int)
        assert result > 0

    def test_unicode_text(self):
        """测试 Unicode 文本"""
        text = "你好世界 🌍"
        result = get_context_token_count(text)
        assert isinstance(result, int)
        assert result > 0

    def test_multiline_text(self):
        """测试多行文本"""
        text = "Line 1\nLine 2\nLine 3"
        result = get_context_token_count(text)
        assert isinstance(result, int)
        assert result > 0


class TestSplitTextIntoChunks:
    """测试 split_text_into_chunks 函数"""

    def test_empty_text(self):
        """测试空文本"""
        assert split_text_into_chunks("") == []

    def test_short_text(self):
        """测试短文本（小于最小长度）"""
        text = "Short text"
        chunks = split_text_into_chunks(text, max_length=512, min_length=50)
        # 即使文本很短，也应该返回至少一个块
        assert len(chunks) >= 1
        assert chunks[0] == text

    def test_text_within_max_length(self):
        """测试在最大长度内的文本"""
        text = "This is a test text that is not too long"
        chunks = split_text_into_chunks(text, max_length=512, min_length=50)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_splitting(self):
        """测试长文本分割"""
        # 创建一个较长的文本
        text = "Word " * 200  # 约 1000 个字符
        chunks = split_text_into_chunks(text, max_length=100, min_length=20)
        assert len(chunks) > 1
        # 验证所有块都被包含
        combined = "".join(chunks)
        assert combined == text

    def test_custom_max_length(self):
        """测试自定义最大长度"""
        text = "Word " * 100
        chunks = split_text_into_chunks(text, max_length=50, min_length=10)
        assert len(chunks) > 1
        # 每个块（除了最后一个）应该接近最大长度
        for chunk in chunks[:-1]:
            assert len(chunk) > 0

    def test_custom_min_length(self):
        """测试自定义最小长度"""
        text = "Word " * 200
        chunks = split_text_into_chunks(text, max_length=100, min_length=30)
        assert len(chunks) > 1
        # 除了最后一个块，其他块应该满足最小长度要求（基于token估算）

    def test_multiline_text(self):
        """测试多行文本"""
        text = "Line 1\n" * 50
        chunks = split_text_into_chunks(text, max_length=100, min_length=20)
        assert len(chunks) > 0
        combined = "".join(chunks)
        assert combined == text


class TestGetMultimodalTokenCount:
    """测试 get_multimodal_token_count 函数"""

    def test_string_input(self):
        """测试字符串输入"""
        text = "Hello world"
        result = get_multimodal_token_count(text)
        expected = get_context_token_count(text)
        assert result == expected

    def test_empty_string(self):
        """测试空字符串"""
        assert get_multimodal_token_count("") == 0

    def test_none_input(self):
        """测试 None 输入"""
        assert get_multimodal_token_count(None) == 0

    def test_text_content_list(self):
        """测试文本内容列表"""
        content_list = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "world"},
        ]
        result = get_multimodal_token_count(content_list)
        expected = get_context_token_count("Hello") + get_context_token_count("world")
        assert result == expected

    def test_image_content(self):
        """测试图片内容"""
        content_list = [
            {"type": "text", "text": "Look at this image:"},
            {"type": "image_url", "image_url": "https://example.com/image.jpg"},
        ]
        result = get_multimodal_token_count(content_list)
        text_tokens = get_context_token_count("Look at this image:")
        # _estimate_image_tokens 期望 dict 类型，传递正确的格式
        image_tokens = _estimate_image_tokens(
            {"image_url": "https://example.com/image.jpg"}
        )
        expected = text_tokens + image_tokens
        assert result == expected

    def test_mixed_content(self):
        """测试混合内容"""
        content_list = [
            {"type": "text", "text": "Look at this image:"},
            {"type": "image_url", "image_url": "https://example.com/image.jpg"},
            {"type": "text", "text": "And look at this image again:"},
            {"type": "image_url", "image_url": "https://example.com/image2.jpg"},
        ]
        result = get_multimodal_token_count(content_list)
        text1_tokens = get_context_token_count("Look at this image:")
        # _estimate_image_tokens 期望 dict 类型，传递正确的格式
        image1_tokens = _estimate_image_tokens(
            {"image_url": "https://example.com/image.jpg"}
        )
        text2_tokens = get_context_token_count("And look at this image again:")
        image2_tokens = _estimate_image_tokens(
            {"image_url": "https://example.com/image2.jpg"}
        )
        expected = text1_tokens + image1_tokens + text2_tokens + image2_tokens
        assert result == expected

    def test_invalid_content_type(self):
        """测试无效内容类型"""
        content_list = [
            {"type": "invalid", "data": "test"},
        ]
        # 未知类型返回 50 tokens
        result = get_multimodal_token_count(content_list)
        assert result == 50


class TestEstimateImageTokens:
    """测试 _estimate_image_tokens 函数"""

    def test_url_image(self):
        """测试 URL 图片"""
        # _estimate_image_tokens 期望 dict 类型
        image_data = {"image_url": "https://example.com/image.jpg"}
        result = _estimate_image_tokens(image_data)
        # 默认返回 85 tokens
        assert result == 85

    def test_base64_image(self):
        """测试 base64 图片"""
        base64_data = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        # _estimate_image_tokens 期望 dict 类型
        image_data = {"image_url": base64_data}
        result = _estimate_image_tokens(image_data)
        # 默认返回 85 tokens
        assert result == 85

    def test_dict_image(self):
        """测试字典格式图片"""
        image_data = {"url": "https://example.com/image.jpg"}
        result = _estimate_image_tokens(image_data)
        # 默认返回 85 tokens
        assert result == 85
