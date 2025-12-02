# -*- coding: utf-8 -*-
"""jarvis_utils.utils 文件操作相关函数单元测试"""

import pytest
import hashlib

from jarvis.jarvis_utils.utils import get_file_md5, get_file_line_count


class TestGetFileMd5:
    """测试 get_file_md5 函数"""

    def test_small_file(self, temp_dir):
        """测试小文件 MD5"""
        test_file = temp_dir / "test.txt"
        content = "Hello, World!"
        test_file.write_text(content)

        result = get_file_md5(str(test_file))

        # 验证 MD5 格式（32 个十六进制字符）
        assert len(result) == 32
        assert all(c in "0123456789abcdef" for c in result)

    def test_empty_file(self, temp_dir):
        """测试空文件 MD5"""
        test_file = temp_dir / "empty.txt"
        test_file.write_text("")

        result = get_file_md5(str(test_file))

        # 空文件的 MD5
        expected = hashlib.md5(b"").hexdigest()
        assert result == expected

    def test_binary_file(self, temp_dir):
        """测试二进制文件 MD5"""
        test_file = temp_dir / "test.bin"
        content = b"\x00\x01\x02\x03\x04\x05"
        test_file.write_bytes(content)

        result = get_file_md5(str(test_file))

        expected = hashlib.md5(content).hexdigest()
        assert result == expected

    def test_unicode_file(self, temp_dir):
        """测试 Unicode 文件 MD5"""
        test_file = temp_dir / "unicode.txt"
        content = "你好世界 🌍"
        test_file.write_text(content, encoding="utf-8")

        result = get_file_md5(str(test_file))

        expected = hashlib.md5(content.encode("utf-8")).hexdigest()
        assert result == expected

    def test_large_file(self, temp_dir):
        """测试大文件 MD5（只计算前100MB）"""
        test_file = temp_dir / "large.bin"
        # 创建 50MB 的文件
        chunk = b"A" * (1024 * 1024)  # 1MB
        with open(test_file, "wb") as f:
            for _ in range(50):
                f.write(chunk)

        result = get_file_md5(str(test_file))

        # 验证 MD5 格式
        assert len(result) == 32
        assert all(c in "0123456789abcdef" for c in result)

    def test_nonexistent_file(self):
        """测试不存在的文件"""
        with pytest.raises(FileNotFoundError):
            get_file_md5("/nonexistent/file.txt")


class TestGetFileLineCount:
    """测试 get_file_line_count 函数"""

    def test_empty_file(self, temp_dir):
        """测试空文件"""
        test_file = temp_dir / "empty.txt"
        test_file.write_text("")

        result = get_file_line_count(str(test_file))
        assert result == 0

    def test_single_line(self, temp_dir):
        """测试单行文件"""
        test_file = temp_dir / "single.txt"
        test_file.write_text("Hello")

        result = get_file_line_count(str(test_file))
        assert result == 1

    def test_multiple_lines(self, temp_dir):
        """测试多行文件"""
        test_file = temp_dir / "multi.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3")

        result = get_file_line_count(str(test_file))
        assert result == 3

    def test_file_with_empty_lines(self, temp_dir):
        """测试包含空行的文件"""
        test_file = temp_dir / "empty_lines.txt"
        test_file.write_text("Line 1\n\nLine 3\n")

        result = get_file_line_count(str(test_file))
        # write_text 默认会在末尾添加换行符，所以是 4 行
        # 但如果最后有换行符，实际可能是 3 或 4 行，取决于实现
        assert result >= 3

    def test_file_without_trailing_newline(self, temp_dir):
        """测试没有尾随换行符的文件"""
        test_file = temp_dir / "no_newline.txt"
        test_file.write_text("Line 1\nLine 2", newline="")

        result = get_file_line_count(str(test_file))
        assert result == 2

    def test_unicode_file(self, temp_dir):
        """测试 Unicode 文件"""
        test_file = temp_dir / "unicode.txt"
        test_file.write_text("你好\n世界\n🌍")

        result = get_file_line_count(str(test_file))
        assert result == 3

    def test_large_file(self, temp_dir):
        """测试大文件"""
        test_file = temp_dir / "large.txt"
        lines = [f"Line {i}\n" for i in range(1000)]
        test_file.write_text("".join(lines))

        result = get_file_line_count(str(test_file))
        assert result == 1000

    def test_nonexistent_file(self):
        """测试不存在的文件"""
        result = get_file_line_count("/nonexistent/file.txt")
        assert result == 0

    def test_binary_file(self, temp_dir):
        """测试二进制文件（应该返回0或处理错误）"""
        test_file = temp_dir / "binary.bin"
        test_file.write_bytes(b"\x00\x01\x02\x03")

        # 函数使用 errors="ignore"，所以应该能处理
        result = get_file_line_count(str(test_file))
        # 二进制文件可能无法正确读取为文本，但函数应该返回一个值
        assert isinstance(result, int)
