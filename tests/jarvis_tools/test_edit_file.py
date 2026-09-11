# -*- coding: utf-8 -*-
"""jarvis_tools.edit_file 模块单元测试（查找替换工具）"""

import os

import pytest

from jarvis.jarvis_tools.edit_file import edit_file


class TestEditFile:
    """测试 edit_file 类（查找替换）"""

    @pytest.fixture
    def tool(self):
        """创建测试用的 edit_file 实例"""
        return edit_file()

    @pytest.fixture
    def temp_file(self, tmp_path):
        """创建临时文件"""
        path = tmp_path / "sample.py"
        path.write_text(
            "def hello():\n    print('Hello, World!')\n\ndef add(a, b):\n    return a + b\n",
            encoding="utf-8",
        )
        return str(path)

    def _read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_unique_match_replace(self, tool, temp_file):
        """唯一匹配替换"""
        result = tool.execute(
            {
                "file_path": temp_file,
                "search": "return a + b",
                "replace": "return a - b",
            }
        )
        assert result["success"] is True
        assert "修改成功" in result["stdout"]
        assert "return a - b" in self._read(temp_file)

    def test_multiple_match_fails_by_default(self, tool, tmp_path):
        """多处匹配默认报错"""
        path = tmp_path / "multi.txt"
        path.write_text("x\nx\n", encoding="utf-8")
        result = tool.execute({"file_path": str(path), "search": "x", "replace": "y"})
        assert result["success"] is False
        assert "匹配到" in result["stderr"]
        assert path.read_text(encoding="utf-8") == "x\nx\n"

    def test_replace_all(self, tool, tmp_path):
        """replace_all=true 全替换"""
        path = tmp_path / "multi.txt"
        path.write_text("x\nx\n", encoding="utf-8")
        result = tool.execute(
            {
                "file_path": str(path),
                "search": "x",
                "replace": "y",
                "replace_all": True,
            }
        )
        assert result["success"] is True
        assert path.read_text(encoding="utf-8") == "y\ny\n"

    def test_not_found(self, tool, temp_file):
        """未找到文本报错"""
        result = tool.execute(
            {"file_path": temp_file, "search": "nonexistent_text", "replace": "x"}
        )
        assert result["success"] is False
        assert "未找到" in result["stderr"]

    def test_search_equals_replace(self, tool, temp_file):
        """search == replace 视为无效操作"""
        result = tool.execute(
            {
                "file_path": temp_file,
                "search": "return a + b",
                "replace": "return a + b",
            }
        )
        assert result["success"] is False
        assert "无效操作" in result["stderr"]

    def test_empty_search_rejected(self, tool, temp_file):
        """空 search 被拒绝并提示用 write_file"""
        result = tool.execute(
            {"file_path": temp_file, "search": "", "replace": "whole new content"}
        )
        assert result["success"] is False
        assert "write_file" in result["stderr"]

    def test_delete_by_empty_replace(self, tool, tmp_path):
        """replace="" 删除匹配文本"""
        path = tmp_path / "del.txt"
        path.write_text("keep\ndel\n", encoding="utf-8")
        result = tool.execute(
            {"file_path": str(path), "search": "del\n", "replace": ""}
        )
        assert result["success"] is True
        assert path.read_text(encoding="utf-8") == "keep\n"

    def test_quote_normalization_match(self, tool, tmp_path):
        """直引号 search 可匹配弯引号文件，且保留弯引号风格"""
        path = tmp_path / "quote.txt"
        path.write_text("s = \u201chello\u201d\n", encoding="utf-8")
        result = tool.execute(
            {"file_path": str(path), "search": 's = "hello"', "replace": 's = "world"'}
        )
        assert result["success"] is True
        assert path.read_text(encoding="utf-8") == "s = \u201cworld\u201d\n"

    def test_missing_search(self, tool, temp_file):
        """缺少 search 报错"""
        result = tool.execute({"file_path": temp_file, "replace": "x"})
        assert result["success"] is False
        assert "search" in result["stderr"]

    def test_missing_replace(self, tool, temp_file):
        """缺少 replace 报错"""
        result = tool.execute({"file_path": temp_file, "search": "x"})
        assert result["success"] is False
        assert "replace" in result["stderr"]

    def test_replace_all_wrong_type(self, tool, temp_file):
        """replace_all 非布尔报错"""
        result = tool.execute(
            {
                "file_path": temp_file,
                "search": "x",
                "replace": "y",
                "replace_all": "yes",
            }
        )
        assert result["success"] is False
        assert "replace_all" in result["stderr"]

    def test_no_backup_left(self, tool, temp_file):
        """成功后不残留备份文件"""
        tool.execute(
            {
                "file_path": temp_file,
                "search": "return a + b",
                "replace": "return a - b",
            }
        )
        assert not os.path.exists(temp_file + ".bak")

    def test_name_matches_module(self):
        """工具 name 与模块名一致（registry 加载约定）"""
        assert edit_file.name == "edit_file"
