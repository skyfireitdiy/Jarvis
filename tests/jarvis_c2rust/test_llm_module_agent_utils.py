# -*- coding: utf-8 -*-
"""jarvis_c2rust.llm_module_agent_utils 模块单元测试"""

import json
from pathlib import Path

import pytest

from jarvis.jarvis_c2rust.llm_module_agent_utils import (
    entries_to_json,
    parse_project_json_entries,
    parse_project_json_entries_fallback,
    resolve_created_dir,
)


class TestResolveCreatedDir:
    """测试 resolve_created_dir 函数"""

    def test_current_directory(self, tmp_path, monkeypatch):
        """测试当前目录"""
        monkeypatch.chdir(tmp_path)
        result = resolve_created_dir(".")
        expected = tmp_path.parent / f"{tmp_path.name}_rs"
        assert result == expected

    def test_resolved_current_directory(self, tmp_path, monkeypatch):
        """测试解析后的当前目录"""
        monkeypatch.chdir(tmp_path)
        result = resolve_created_dir(tmp_path)
        expected = tmp_path.parent / f"{tmp_path.name}_rs"
        assert result == expected

    def test_different_directory(self, tmp_path):
        """测试不同的目录"""
        other_dir = tmp_path / "other"
        result = resolve_created_dir(other_dir)
        assert result == other_dir

    def test_string_path(self, tmp_path):
        """测试字符串路径"""
        other_dir = tmp_path / "other"
        result = resolve_created_dir(str(other_dir))
        assert result == other_dir

    def test_exception_handling(self):
        """测试异常处理"""
        result = resolve_created_dir("/nonexistent/path")
        assert isinstance(result, Path)
        assert str(result) == "/nonexistent/path"


class TestParseProjectJsonEntriesFallback:
    """测试 parse_project_json_entries_fallback 函数"""

    def test_valid_list(self):
        """测试有效的列表"""
        json_text = '["file1.rs", "file2.rs"]'
        result = parse_project_json_entries_fallback(json_text)
        assert result == ["file1.rs", "file2.rs"]

    def test_nested_structure(self):
        """测试嵌套结构"""
        json_text = '[{"src/": ["lib.rs", "main.rs"]}]'
        result = parse_project_json_entries_fallback(json_text)
        assert result == [{"src/": ["lib.rs", "main.rs"]}]

    def test_empty_list(self):
        """测试空列表"""
        json_text = "[]"
        result = parse_project_json_entries_fallback(json_text)
        assert result == []

    def test_invalid_json(self):
        """测试无效的 JSON"""
        json_text = "invalid json"
        result = parse_project_json_entries_fallback(json_text)
        assert result == []

    def test_non_list_json(self):
        """测试非列表的 JSON"""
        json_text = '{"key": "value"}'
        result = parse_project_json_entries_fallback(json_text)
        assert result == []


class TestParseProjectJsonEntries:
    """测试 parse_project_json_entries 函数"""

    def test_valid_list(self):
        """测试有效的列表"""
        json_text = '["file1.rs", "file2.rs"]'
        result, error = parse_project_json_entries(json_text)
        assert error is None
        assert result == ["file1.rs", "file2.rs"]

    def test_nested_structure(self):
        """测试嵌套结构"""
        json_text = '[{"src/": ["lib.rs", "main.rs"]}]'
        result, error = parse_project_json_entries(json_text)
        assert error is None
        assert result == [{"src/": ["lib.rs", "main.rs"]}]

    def test_with_trailing_comma(self):
        """测试包含尾随逗号（jsonnet 兼容）"""
        json_text = '["file1.rs", "file2.rs",]'
        result, error = parse_project_json_entries(json_text)
        # jsonnet 应该能处理尾随逗号
        assert error is None or result == ["file1.rs", "file2.rs"]

    def test_with_comments(self):
        """测试包含注释（jsonnet 兼容）"""
        json_text = '["file1.rs", // comment\n"file2.rs"]'
        result, error = parse_project_json_entries(json_text)
        # jsonnet 应该能处理注释
        assert error is None or result == ["file1.rs", "file2.rs"]

    def test_empty_list(self):
        """测试空列表"""
        json_text = "[]"
        result, error = parse_project_json_entries(json_text)
        assert error is None
        assert result == []

    def test_invalid_json(self):
        """测试无效的 JSON"""
        json_text = "invalid json"
        result, error = parse_project_json_entries(json_text)
        assert error is not None
        assert result == []

    def test_non_list_json(self):
        """测试非列表的 JSON"""
        json_text = '{"key": "value"}'
        result, error = parse_project_json_entries(json_text)
        assert error is not None
        assert result == []


class TestEntriesToJson:
    """测试 entries_to_json 函数"""

    def test_simple_list(self):
        """测试简单列表"""
        entries = ["file1.rs", "file2.rs"]
        result = entries_to_json(entries)
        parsed = json.loads(result)
        assert parsed == entries

    def test_nested_structure(self):
        """测试嵌套结构"""
        entries = [{"src/": ["lib.rs", "main.rs"]}]
        result = entries_to_json(entries)
        parsed = json.loads(result)
        assert parsed == entries

    def test_complex_structure(self):
        """测试复杂结构"""
        entries = [
            "Cargo.toml",
            {"src/": ["lib.rs", {"math/": ["arithmetic.rs", "number_theory.rs"]}]},
        ]
        result = entries_to_json(entries)
        parsed = json.loads(result)
        assert parsed == entries

    def test_empty_list(self):
        """测试空列表"""
        entries = []
        result = entries_to_json(entries)
        parsed = json.loads(result)
        assert parsed == entries

    def test_unicode_content(self):
        """测试 Unicode 内容"""
        entries = ["文件.rs", {"目录/": ["测试.rs"]}]
        result = entries_to_json(entries)
        parsed = json.loads(result)
        assert parsed == entries
