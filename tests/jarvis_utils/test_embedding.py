# -*- coding: utf-8 -*-
"""jarvis_utils.embedding 模块单元测试"""


from jarvis.jarvis_utils.embedding import get_context_token_count, split_text_into_chunks


class TestGetContextTokenCount:
    """测试 get_context_token_count 函数"""

    def test_empty_string(self):
        """测试空字符串"""
        assert get_context_token_count("") == 0

    def test_none_input(self):
        """测试 None 输入"""
        assert get_context_token_count(None) == 0

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

