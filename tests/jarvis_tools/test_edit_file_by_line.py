# -*- coding: utf-8 -*-
"""jarvis_tools.edit_file_by_line 模块单元测试"""

import os

import pytest

from jarvis.jarvis_tools.edit_file_by_line import edit_file_by_line


class TestEditFileByLine:
    """测试 edit_file_by_line 类"""

    @pytest.fixture
    def tool(self):
        """创建测试用的 edit_file_by_line 实例"""
        return edit_file_by_line()

    @pytest.fixture
    def temp_file(self, tmp_path):
        """创建 5 行内容的临时文件"""
        path = tmp_path / "sample.txt"
        path.write_text("l1\nl2\nl3\nl4\nl5\n", encoding="utf-8")
        return str(path)

    def _read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_replace_single_line(self, tool, temp_file):
        """单行替换"""
        result = tool.execute(
            {"file_path": temp_file, "start_line": 2, "end_line": 2, "content": "X"}
        )
        assert result["success"] is True
        assert "修改成功" in result["stdout"]
        assert self._read(temp_file) == "l1\nX\nl3\nl4\nl5\n"

    def test_replace_multiple_lines(self, tool, temp_file):
        """多行区间替换（闭区间）"""
        result = tool.execute(
            {
                "file_path": temp_file,
                "start_line": 2,
                "end_line": 4,
                "content": "X\nY",
            }
        )
        assert result["success"] is True
        assert self._read(temp_file) == "l1\nX\nY\nl5\n"

    def test_replace_last_line(self, tool, temp_file):
        """替换末尾行（不额外补换行）"""
        result = tool.execute(
            {"file_path": temp_file, "start_line": 5, "end_line": 5, "content": "Z"}
        )
        assert result["success"] is True
        assert self._read(temp_file) == "l1\nl2\nl3\nl4\nZ"

    def test_delete_range(self, tool, temp_file):
        """删除区间（content=""）：原区间内容被清空，保留空行占位"""
        result = tool.execute(
            {"file_path": temp_file, "start_line": 2, "end_line": 3, "content": ""}
        )
        assert result["success"] is True
        assert self._read(temp_file) == "l1\n\nl4\nl5\n"

    def test_start_line_out_of_range(self, tool, temp_file):
        """start_line 超出总行数报错"""
        result = tool.execute(
            {"file_path": temp_file, "start_line": 99, "end_line": 100, "content": "x"}
        )
        assert result["success"] is False
        assert "超出文件总行数" in result["stderr"]
        assert self._read(temp_file) == "l1\nl2\nl3\nl4\nl5\n"

    def test_start_line_less_than_one(self, tool, temp_file):
        """start_line < 1 报错"""
        result = tool.execute(
            {"file_path": temp_file, "start_line": 0, "end_line": 1, "content": "x"}
        )
        assert result["success"] is False
        assert "start_line" in result["stderr"]

    def test_end_line_less_than_start_line(self, tool, temp_file):
        """end_line < start_line 报错"""
        result = tool.execute(
            {"file_path": temp_file, "start_line": 3, "end_line": 1, "content": "x"}
        )
        assert result["success"] is False
        assert "end_line" in result["stderr"]

    def test_non_integer_line(self, tool, temp_file):
        """行号非整数报错"""
        result = tool.execute(
            {"file_path": temp_file, "start_line": "2", "end_line": 3, "content": "x"}
        )
        assert result["success"] is False
        assert "start_line" in result["stderr"]

    def test_missing_content(self, tool, temp_file):
        """缺少 content 报错"""
        result = tool.execute({"file_path": temp_file, "start_line": 1, "end_line": 1})
        assert result["success"] is False
        assert "content" in result["stderr"]

    def test_encoding_preserved(self, tool, tmp_path):
        """保持原文件编码"""
        path = tmp_path / "enc.txt"
        path.write_text("中文一\n中文二\n", encoding="utf-8")
        result = tool.execute(
            {"file_path": str(path), "start_line": 1, "end_line": 1, "content": "替换"}
        )
        assert result["success"] is True
        assert "utf-8" in result["stdout"]
        assert path.read_text(encoding="utf-8") == "替换\n中文二\n"

    def test_no_backup_left(self, tool, temp_file):
        """成功后不残留备份文件"""
        tool.execute(
            {"file_path": temp_file, "start_line": 1, "end_line": 1, "content": "x"}
        )
        assert not os.path.exists(temp_file + ".bak")

    def test_name_matches_module(self):
        """工具 name 与模块名一致（registry 加载约定）"""
        assert edit_file_by_line.name == "edit_file_by_line"
