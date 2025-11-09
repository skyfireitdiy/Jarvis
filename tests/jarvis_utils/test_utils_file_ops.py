# -*- coding: utf-8 -*-
"""jarvis_utils.utils 文件操作函数单元测试"""

import pytest
import tempfile
import os
import hashlib

from jarvis.jarvis_utils.utils import get_file_md5, get_file_line_count


class TestGetFileMd5:
    """测试 get_file_md5 函数"""

    def test_small_file(self, temp_dir):
        """测试小文件"""
        test_file = temp_dir / "test.txt"
        test_file.write_text("Hello, World!")
        
        md5_hash = get_file_md5(str(test_file))
        assert isinstance(md5_hash, str)
        assert len(md5_hash) == 32  # MD5 hash 是 32 个字符

    def test_empty_file(self, temp_dir):
        """测试空文件"""
        test_file = temp_dir / "empty.txt"
        test_file.write_text("")
        
        md5_hash = get_file_md5(str(test_file))
        assert isinstance(md5_hash, str)
        assert len(md5_hash) == 32
        # 空文件的 MD5 应该是已知值
        expected = hashlib.md5(b"").hexdigest()
        assert md5_hash == expected

    def test_large_file(self, temp_dir):
        """测试大文件（超过100MB限制）"""
        test_file = temp_dir / "large.txt"
        # 创建大于100MB的文件
        content = "A" * (101 * 1024 * 1024)  # 101MB
        test_file.write_text(content)
        
        md5_hash = get_file_md5(str(test_file))
        assert isinstance(md5_hash, str)
        assert len(md5_hash) == 32
        # 应该只计算前100MB的hash
        expected = hashlib.md5(content[:100 * 1024 * 1024].encode()).hexdigest()
        assert md5_hash == expected

    def test_binary_file(self, temp_dir):
        """测试二进制文件"""
        test_file = temp_dir / "binary.bin"
        binary_data = b"\x00\x01\x02\x03\x04\x05"
        test_file.write_bytes(binary_data)
        
        md5_hash = get_file_md5(str(test_file))
        assert isinstance(md5_hash, str)
        assert len(md5_hash) == 32
        expected = hashlib.md5(binary_data).hexdigest()
        assert md5_hash == expected

    def test_unicode_file(self, temp_dir):
        """测试 Unicode 文件"""
        test_file = temp_dir / "unicode.txt"
        content = "你好世界 🌍 测试"
        test_file.write_text(content, encoding="utf-8")
        
        md5_hash = get_file_md5(str(test_file))
        assert isinstance(md5_hash, str)
        assert len(md5_hash) == 32


class TestGetFileLineCount:
    """测试 get_file_line_count 函数"""

    def test_empty_file(self, temp_dir):
        """测试空文件"""
        test_file = temp_dir / "empty.txt"
        test_file.write_text("")
        
        count = get_file_line_count(str(test_file))
        assert count == 0

    def test_single_line(self, temp_dir):
        """测试单行文件"""
        test_file = temp_dir / "single.txt"
        test_file.write_text("Single line")
        
        count = get_file_line_count(str(test_file))
        assert count == 1

    def test_multiple_lines(self, temp_dir):
        """测试多行文件"""
        test_file = temp_dir / "multi.txt"
        content = "Line 1\nLine 2\nLine 3\n"
        test_file.write_text(content)
        
        count = get_file_line_count(str(test_file))
        assert count == 3

    def test_no_trailing_newline(self, temp_dir):
        """测试没有尾随换行符的文件"""
        test_file = temp_dir / "no_newline.txt"
        content = "Line 1\nLine 2\nLine 3"  # 没有尾随换行符
        test_file.write_text(content)
        
        count = get_file_line_count(str(test_file))
        assert count == 3

    def test_empty_lines(self, temp_dir):
        """测试包含空行的文件"""
        test_file = temp_dir / "empty_lines.txt"
        content = "Line 1\n\nLine 3\n\n"
        test_file.write_text(content)
        
        count = get_file_line_count(str(test_file))
        assert count == 4  # 包括空行

    def test_nonexistent_file(self):
        """测试不存在的文件"""
        count = get_file_line_count("/nonexistent/file.txt")
        assert count == 0

    def test_unicode_content(self, temp_dir):
        """测试包含 Unicode 内容的文件"""
        test_file = temp_dir / "unicode.txt"
        content = "你好\n世界\n测试"
        test_file.write_text(content, encoding="utf-8")
        
        count = get_file_line_count(str(test_file))
        assert count == 3

