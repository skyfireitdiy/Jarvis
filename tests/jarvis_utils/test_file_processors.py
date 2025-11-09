# -*- coding: utf-8 -*-
"""jarvis_utils.file_processors 模块单元测试"""

import pytest
import tempfile
import os

from jarvis.jarvis_utils.file_processors import FileProcessor, TextFileProcessor


class TestFileProcessor:
    """测试 FileProcessor 抽象基类"""

    def test_can_handle_not_implemented(self):
        """测试 can_handle 方法未实现"""
        with pytest.raises(NotImplementedError):
            FileProcessor.can_handle("test.txt")

    def test_extract_text_not_implemented(self):
        """测试 extract_text 方法未实现"""
        with pytest.raises(NotImplementedError):
            FileProcessor.extract_text("test.txt")


class TestTextFileProcessor:
    """测试 TextFileProcessor 类"""

    def test_can_handle_text_file(self, temp_dir):
        """测试识别文本文件"""
        test_file = temp_dir / "test.txt"
        test_file.write_text("Hello, World!", encoding="utf-8")
        
        result = TextFileProcessor.can_handle(str(test_file))
        assert result is True

    def test_can_handle_binary_file(self, temp_dir):
        """测试识别二进制文件"""
        test_file = temp_dir / "test.bin"
        test_file.write_bytes(b"\x00\x01\x02\x03\x04\x05")
        
        result = TextFileProcessor.can_handle(str(test_file))
        assert result is False

    def test_can_handle_nonexistent_file(self):
        """测试不存在的文件"""
        result = TextFileProcessor.can_handle("/nonexistent/file.txt")
        assert result is False

    def test_extract_text_basic(self, temp_dir):
        """测试提取基本文本"""
        test_file = temp_dir / "test.txt"
        content = "Hello, World!"
        test_file.write_text(content, encoding="utf-8")
        
        result = TextFileProcessor.extract_text(str(test_file))
        assert result == content

    def test_extract_text_multiline(self, temp_dir):
        """测试提取多行文本"""
        test_file = temp_dir / "test.txt"
        content = "Line 1\nLine 2\nLine 3"
        test_file.write_text(content, encoding="utf-8")
        
        result = TextFileProcessor.extract_text(str(test_file))
        assert result == content

    def test_extract_text_unicode(self, temp_dir):
        """测试提取 Unicode 文本"""
        test_file = temp_dir / "test.txt"
        content = "你好世界 🌍"
        test_file.write_text(content, encoding="utf-8")
        
        result = TextFileProcessor.extract_text(str(test_file))
        assert result == content

    def test_extract_text_empty_file(self, temp_dir):
        """测试提取空文件"""
        test_file = temp_dir / "empty.txt"
        test_file.write_text("", encoding="utf-8")
        
        result = TextFileProcessor.extract_text(str(test_file))
        assert result == ""

    def test_extract_text_gbk_encoding(self, temp_dir):
        """测试提取 GBK 编码文件"""
        test_file = temp_dir / "test_gbk.txt"
        content = "测试GBK编码"
        test_file.write_text(content, encoding="gbk")
        
        result = TextFileProcessor.extract_text(str(test_file))
        assert result == content

