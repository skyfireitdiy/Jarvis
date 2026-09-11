# -*- coding: utf-8 -*-
"""jarvis_tools.write_file 模块单元测试"""

import os

import pytest

from jarvis.jarvis_tools.write_file import write_file


class TestWriteFile:
    """测试 write_file 类"""

    @pytest.fixture
    def tool(self):
        """创建测试用的 write_file 实例"""
        return write_file()

    @pytest.fixture
    def temp_file(self, tmp_path):
        """创建临时文件"""
        path = tmp_path / "sample.py"
        path.write_text("def hello():\n    print('hi')\n", encoding="utf-8")
        return str(path)

    def test_overwrite_existing_file(self, tool, temp_file):
        """覆写已有文件"""
        result = tool.execute({"file_path": temp_file, "content": "new content\n"})
        assert result["success"] is True
        assert "写入成功" in result["stdout"]
        assert result["stderr"] == ""
        with open(temp_file, encoding="utf-8") as f:
            assert f.read() == "new content\n"

    def test_create_new_file_with_parent_dirs(self, tool, tmp_path):
        """文件不存在时创建（含父目录）"""
        path = tmp_path / "a" / "b" / "new.txt"
        result = tool.execute({"file_path": str(path), "content": "hello"})
        assert result["success"] is True
        assert path.read_text(encoding="utf-8") == "hello"

    def test_empty_content_clears_file(self, tool, temp_file):
        """空 content 清空文件"""
        result = tool.execute({"file_path": temp_file, "content": ""})
        assert result["success"] is True
        with open(temp_file, encoding="utf-8") as f:
            assert f.read() == ""

    def test_encoding_preserved(self, tool, tmp_path):
        """保持原文件编码（utf-8）"""
        path = tmp_path / "enc.txt"
        path.write_text("中文内容\n", encoding="utf-8")
        result = tool.execute({"file_path": str(path), "content": "新的中文\n"})
        assert result["success"] is True
        assert "utf-8" in result["stdout"]
        assert path.read_text(encoding="utf-8") == "新的中文\n"

    def test_no_backup_left(self, tool, temp_file):
        """写入成功后不残留备份文件"""
        tool.execute({"file_path": temp_file, "content": "x\n"})
        assert not os.path.exists(temp_file + ".bak")

    def test_missing_file_path(self, tool):
        """缺少 file_path 报错"""
        result = tool.execute({"content": "x"})
        assert result["success"] is False
        assert "file_path" in result["stderr"]

    def test_missing_content(self, tool, temp_file):
        """缺少 content 报错"""
        result = tool.execute({"file_path": temp_file})
        assert result["success"] is False
        assert "content" in result["stderr"]

    def test_content_wrong_type(self, tool, temp_file):
        """content 类型错误报错"""
        result = tool.execute({"file_path": temp_file, "content": 123})
        assert result["success"] is False
        assert "content" in result["stderr"]

    def test_file_path_wrong_type(self, tool):
        """file_path 类型错误报错"""
        result = tool.execute({"file_path": 123, "content": "x"})
        assert result["success"] is False
        assert "file_path" in result["stderr"]

    def test_name_matches_module(self):
        """工具 name 与模块名一致（registry 加载约定）"""
        assert write_file.name == "write_file"
