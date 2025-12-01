# -*- coding: utf-8 -*-
"""jarvis_c2rust.utils 模块单元测试"""

import json
import tempfile
from pathlib import Path

import pytest

from jarvis.jarvis_c2rust.utils import (
    default_crate_dir,
    dir_tree,
    extract_json_from_summary,
    iter_order_steps,
    read_json,
    write_json,
)


class TestIterOrderSteps:
    """测试 iter_order_steps 函数"""

    def test_empty_file(self, tmp_path):
        """测试空文件"""
        order_file = tmp_path / "order.jsonl"
        order_file.write_text("")
        result = iter_order_steps(order_file)
        assert result == []

    def test_new_format_with_ids(self, tmp_path):
        """测试新格式（包含 ids）"""
        order_file = tmp_path / "order.jsonl"
        order_file.write_text('{"ids": [1, 2, 3]}\n{"ids": [4, 5]}')
        result = iter_order_steps(order_file)
        assert result == [[1, 2, 3], [4, 5]]

    def test_ids_as_strings(self, tmp_path):
        """测试 ids 为字符串格式"""
        order_file = tmp_path / "order.jsonl"
        order_file.write_text('{"ids": ["1", "2", "3"]}')
        result = iter_order_steps(order_file)
        assert result == [[1, 2, 3]]

    def test_mixed_ids(self, tmp_path):
        """测试混合格式的 ids"""
        order_file = tmp_path / "order.jsonl"
        order_file.write_text('{"ids": [1, "2", 3]}')
        result = iter_order_steps(order_file)
        assert result == [[1, 2, 3]]

    def test_empty_ids(self, tmp_path):
        """测试空的 ids"""
        order_file = tmp_path / "order.jsonl"
        order_file.write_text('{"ids": []}')
        result = iter_order_steps(order_file)
        assert result == []

    def test_invalid_json_line(self, tmp_path):
        """测试无效的 JSON 行"""
        order_file = tmp_path / "order.jsonl"
        order_file.write_text('{"ids": [1, 2]}\ninvalid json\n{"ids": [3]}')
        result = iter_order_steps(order_file)
        assert result == [[1, 2], [3]]

    def test_no_ids_key(self, tmp_path):
        """测试没有 ids 键的行"""
        order_file = tmp_path / "order.jsonl"
        order_file.write_text('{"other": "value"}\n{"ids": [1]}')
        result = iter_order_steps(order_file)
        assert result == [[1]]

    def test_whitespace_lines(self, tmp_path):
        """测试空白行"""
        order_file = tmp_path / "order.jsonl"
        order_file.write_text('\n{"ids": [1]}\n\n{"ids": [2]}\n')
        result = iter_order_steps(order_file)
        assert result == [[1], [2]]


class TestDirTree:
    """测试 dir_tree 函数"""

    def test_empty_directory(self, tmp_path):
        """测试空目录"""
        result = dir_tree(tmp_path)
        assert result == ""

    def test_simple_structure(self, tmp_path):
        """测试简单目录结构"""
        (tmp_path / "file1.txt").write_text("content")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file2.txt").write_text("content")
        result = dir_tree(tmp_path)
        assert "- file1.txt" in result
        assert "- subdir/" in result
        assert "  - file2.txt" in result

    def test_excludes_git(self, tmp_path):
        """测试排除 .git 目录"""
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("content")
        (tmp_path / "file.txt").write_text("content")
        result = dir_tree(tmp_path)
        assert ".git" not in result
        assert "file.txt" in result

    def test_excludes_target(self, tmp_path):
        """测试排除 target 目录"""
        (tmp_path / "target").mkdir()
        (tmp_path / "target" / "file.txt").write_text("content")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "lib.rs").write_text("content")
        result = dir_tree(tmp_path)
        assert "target" not in result
        assert "src" in result

    def test_excludes_jarvis(self, tmp_path):
        """测试排除 .jarvis 目录"""
        (tmp_path / ".jarvis").mkdir()
        (tmp_path / ".jarvis" / "config.json").write_text("content")
        (tmp_path / "file.txt").write_text("content")
        result = dir_tree(tmp_path)
        assert ".jarvis" not in result
        assert "file.txt" in result

    def test_nonexistent_directory(self):
        """测试不存在的目录"""
        result = dir_tree(Path("/nonexistent/path"))
        assert result == ""


class TestDefaultCrateDir:
    """测试 default_crate_dir 函数"""

    def test_current_directory(self, tmp_path, monkeypatch):
        """测试当前目录为项目根目录"""
        monkeypatch.chdir(tmp_path)
        result = default_crate_dir(tmp_path)
        expected = tmp_path.parent / f"{tmp_path.name}_rs"
        assert result == expected

    def test_different_directory(self, tmp_path):
        """测试不同的目录"""
        project_root = tmp_path / "project"
        project_root.mkdir()
        result = default_crate_dir(project_root)
        assert result == project_root

    def test_exception_handling(self, monkeypatch):
        """测试异常处理"""

        def mock_resolve():
            raise OSError("Cannot resolve")

        monkeypatch.setattr(Path, "resolve", lambda self: mock_resolve())
        project_root = Path("test")
        result = default_crate_dir(project_root)
        assert result == project_root


class TestReadJson:
    """测试 read_json 函数"""

    def test_existing_file(self, tmp_path):
        """测试存在的文件"""
        json_file = tmp_path / "test.json"
        json_file.write_text('{"key": "value"}')
        result = read_json(json_file, {})
        assert result == {"key": "value"}

    def test_nonexistent_file(self, tmp_path):
        """测试不存在的文件"""
        json_file = tmp_path / "nonexistent.json"
        result = read_json(json_file, {"default": "value"})
        assert result == {"default": "value"}

    def test_invalid_json(self, tmp_path):
        """测试无效的 JSON"""
        json_file = tmp_path / "invalid.json"
        json_file.write_text("invalid json content")
        result = read_json(json_file, {"default": "value"})
        assert result == {"default": "value"}

    def test_empty_file(self, tmp_path):
        """测试空文件"""
        json_file = tmp_path / "empty.json"
        json_file.write_text("")
        result = read_json(json_file, {"default": "value"})
        assert result == {"default": "value"}


class TestWriteJson:
    """测试 write_json 函数"""

    def test_write_simple_object(self, tmp_path):
        """测试写入简单对象"""
        json_file = tmp_path / "test.json"
        data = {"key": "value", "number": 42}
        write_json(json_file, data)
        assert json_file.exists()
        result = json.loads(json_file.read_text())
        assert result == data

    def test_write_nested_object(self, tmp_path):
        """测试写入嵌套对象"""
        json_file = tmp_path / "test.json"
        data = {"nested": {"key": "value"}, "list": [1, 2, 3]}
        write_json(json_file, data)
        result = json.loads(json_file.read_text())
        assert result == data

    def test_create_parent_directories(self, tmp_path):
        """测试创建父目录"""
        json_file = tmp_path / "subdir" / "test.json"
        data = {"key": "value"}
        write_json(json_file, data)
        assert json_file.exists()
        result = json.loads(json_file.read_text())
        assert result == data

    def test_unicode_content(self, tmp_path):
        """测试 Unicode 内容"""
        json_file = tmp_path / "test.json"
        data = {"中文": "测试", "emoji": "🚀"}
        write_json(json_file, data)
        result = json.loads(json_file.read_text())
        assert result == data


class TestExtractJsonFromSummary:
    """测试 extract_json_from_summary 函数"""

    def test_valid_summary_block(self):
        """测试有效的 SUMMARY 块"""
        text = '<SUMMARY>{"key": "value"}</SUMMARY>'
        result, error = extract_json_from_summary(text)
        assert error is None
        assert result == {"key": "value"}

    def test_summary_with_whitespace(self):
        """测试包含空白字符的 SUMMARY 块"""
        text = '<SUMMARY>\n{"key": "value"}\n</SUMMARY>'
        result, error = extract_json_from_summary(text)
        assert error is None
        assert result == {"key": "value"}

    def test_summary_with_trailing_comma(self):
        """测试包含尾随逗号的 JSON（jsonnet 兼容）"""
        text = '<SUMMARY>{"key": "value",}</SUMMARY>'
        result, error = extract_json_from_summary(text)
        # jsonnet 应该能处理尾随逗号
        assert error is None or result == {"key": "value"}

    def test_no_summary_tags(self):
        """测试没有 SUMMARY 标签"""
        text = '{"key": "value"}'
        result, error = extract_json_from_summary(text)
        assert error is None
        assert result == {"key": "value"}

    def test_empty_summary_block(self):
        """测试空的 SUMMARY 块"""
        text = "<SUMMARY></SUMMARY>"
        result, error = extract_json_from_summary(text)
        assert error is not None
        assert result == {}

    def test_invalid_json(self):
        """测试无效的 JSON"""
        text = "<SUMMARY>{invalid json}</SUMMARY>"
        result, error = extract_json_from_summary(text)
        assert error is not None
        assert result == {}

    def test_non_dict_result(self):
        """测试非字典结果"""
        text = '<SUMMARY>["array"]</SUMMARY>'
        result, error = extract_json_from_summary(text)
        assert error is not None
        assert result == {}

    def test_empty_string(self):
        """测试空字符串"""
        result, error = extract_json_from_summary("")
        assert error is not None
        assert result == {}

    def test_none_input(self):
        """测试 None 输入"""
        result, error = extract_json_from_summary(None)
        assert error is not None
        assert result == {}

    def test_case_insensitive_tags(self):
        """测试大小写不敏感的标签"""
        text = '<summary>{"key": "value"}</summary>'
        result, error = extract_json_from_summary(text)
        assert error is None
        assert result == {"key": "value"}
