# -*- coding: utf-8 -*-
"""jarvis_c2rust.library_replacer_utils 模块单元测试"""

import json
from pathlib import Path


from jarvis.jarvis_c2rust.library_replacer_utils import (
    is_entry_function,
    load_additional_notes,
    normalize_disabled_libraries,
    normalize_list,
    normalize_list_lower,
    read_source_snippet,
    resolve_symbols_jsonl_path,
    setup_output_paths,
)


class TestResolveSymbolsJsonlPath:
    """测试 resolve_symbols_jsonl_path 函数"""

    def test_existing_file(self, tmp_path):
        """测试存在的文件"""
        jsonl_file = tmp_path / "symbols.jsonl"
        jsonl_file.write_text("test")
        result = resolve_symbols_jsonl_path(jsonl_file)
        assert result == jsonl_file

    def test_directory(self, tmp_path):
        """测试目录路径"""
        data_dir = tmp_path / ".jarvis" / "c2rust"
        data_dir.mkdir(parents=True)
        result = resolve_symbols_jsonl_path(tmp_path)
        expected = tmp_path / ".jarvis" / "c2rust" / "symbols.jsonl"
        assert result == expected

    def test_nonexistent_path(self):
        """测试不存在的路径"""
        result = resolve_symbols_jsonl_path(Path("/nonexistent"))
        expected = Path(".") / ".jarvis" / "c2rust" / "symbols.jsonl"
        assert result == expected

    def test_non_jsonl_file(self, tmp_path):
        """测试非 .jsonl 文件"""
        txt_file = tmp_path / "symbols.txt"
        txt_file.write_text("test")
        result = resolve_symbols_jsonl_path(txt_file)
        expected = Path(".") / ".jarvis" / "c2rust" / "symbols.jsonl"
        assert result == expected


class TestSetupOutputPaths:
    """测试 setup_output_paths 函数"""

    def test_default_paths(self, tmp_path):
        """测试默认路径"""
        data_dir = tmp_path / ".jarvis" / "c2rust"
        symbols_path, mapping_path, prune_path, order_path, alias_path = (
            setup_output_paths(data_dir, None, None)
        )
        assert symbols_path == data_dir / "symbols_library_pruned.jsonl"
        assert mapping_path == data_dir / "library_replacements.jsonl"
        assert prune_path == data_dir / "symbols_prune.jsonl"
        assert order_path == data_dir / "translation_order_prune.jsonl"
        assert alias_path == data_dir / "translation_order.jsonl"

    def test_custom_paths(self, tmp_path):
        """测试自定义路径"""
        data_dir = tmp_path / ".jarvis" / "c2rust"
        custom_symbols = tmp_path / "custom_symbols.jsonl"
        custom_mapping = tmp_path / "custom_mapping.jsonl"
        symbols_path, mapping_path, prune_path, order_path, alias_path = (
            setup_output_paths(data_dir, custom_symbols, custom_mapping)
        )
        assert symbols_path == custom_symbols
        assert mapping_path == custom_mapping
        assert prune_path == data_dir / "symbols_prune.jsonl"
        assert order_path == data_dir / "translation_order_prune.jsonl"
        assert alias_path == data_dir / "translation_order.jsonl"


class TestReadSourceSnippet:
    """测试 read_source_snippet 函数"""

    def test_basic_read(self, tmp_path):
        """测试基本读取"""
        source_file = tmp_path / "test.c"
        source_file.write_text("line1\nline2\nline3\nline4\nline5")
        rec = {
            "file": str(source_file),
            "start_line": 2,
            "end_line": 4,
        }
        result = read_source_snippet(rec)
        assert result == "line2\nline3\nline4"

    def test_single_line(self, tmp_path):
        """测试单行"""
        source_file = tmp_path / "test.c"
        source_file.write_text("line1\nline2\nline3")
        rec = {
            "file": str(source_file),
            "start_line": 2,
            "end_line": 2,
        }
        result = read_source_snippet(rec)
        assert result == "line2"

    def test_max_lines_limit(self, tmp_path):
        """测试最大行数限制"""
        source_file = tmp_path / "test.c"
        source_file.write_text("\n".join(f"line{i}" for i in range(1, 101)))
        rec = {
            "file": str(source_file),
            "start_line": 1,
            "end_line": 100,
        }
        result = read_source_snippet(rec, max_lines=50)
        assert len(result.split("\n")) == 50

    def test_nonexistent_file(self):
        """测试不存在的文件"""
        rec = {
            "file": "/nonexistent/file.c",
            "start_line": 1,
            "end_line": 10,
        }
        result = read_source_snippet(rec)
        assert result == ""

    def test_empty_file(self, tmp_path):
        """测试空文件"""
        source_file = tmp_path / "empty.c"
        source_file.write_text("")
        rec = {
            "file": str(source_file),
            "start_line": 1,
            "end_line": 1,
        }
        result = read_source_snippet(rec)
        assert result == ""

    def test_invalid_line_numbers(self, tmp_path):
        """测试无效的行号"""
        source_file = tmp_path / "test.c"
        source_file.write_text("line1\nline2\nline3")
        rec = {
            "file": str(source_file),
            "start_line": 10,
            "end_line": 5,  # end < start
        }
        result = read_source_snippet(rec)
        # 当 start_line 超出文件范围时，start_idx 会超出范围，返回空字符串
        assert result == ""

    def test_missing_file_key(self):
        """测试缺少 file 键"""
        rec = {
            "start_line": 1,
            "end_line": 10,
        }
        result = read_source_snippet(rec)
        assert result == ""


class TestNormalizeDisabledLibraries:
    """测试 normalize_disabled_libraries 函数"""

    def test_normal_list(self):
        """测试正常列表"""
        disabled = ["lib1", "lib2", "lib3"]
        norm, display = normalize_disabled_libraries(disabled)
        assert norm == ["lib1", "lib2", "lib3"]
        assert display == "lib1, lib2, lib3"

    def test_with_whitespace(self):
        """测试包含空白字符"""
        disabled = [" lib1 ", "  lib2  ", "lib3"]
        norm, display = normalize_disabled_libraries(disabled)
        assert norm == ["lib1", "lib2", "lib3"]
        assert display == "lib1, lib2, lib3"

    def test_case_insensitive(self):
        """测试大小写不敏感（转换为小写）"""
        disabled = ["LIB1", "Lib2", "lib3"]
        norm, display = normalize_disabled_libraries(disabled)
        assert norm == ["lib1", "lib2", "lib3"]
        assert display == "LIB1, Lib2, lib3"  # display 保持原样

    def test_empty_list(self):
        """测试空列表"""
        norm, display = normalize_disabled_libraries([])
        assert norm == []
        assert display == ""

    def test_none_input(self):
        """测试 None 输入"""
        norm, display = normalize_disabled_libraries(None)
        assert norm == []
        assert display == ""

    def test_empty_strings(self):
        """测试包含空字符串"""
        disabled = ["lib1", "", "lib2", "  ", "lib3"]
        norm, display = normalize_disabled_libraries(disabled)
        assert norm == ["lib1", "lib2", "lib3"]
        assert display == "lib1, lib2, lib3"


class TestLoadAdditionalNotes:
    """测试 load_additional_notes 函数"""

    def test_existing_config(self, tmp_path):
        """测试存在的配置文件"""
        data_dir = tmp_path / ".jarvis" / "c2rust"
        data_dir.mkdir(parents=True)
        config_file = data_dir / "config.json"
        config_file.write_text(json.dumps({"additional_notes": "Test notes"}))
        result = load_additional_notes(data_dir)
        assert result == "Test notes"

    def test_nonexistent_config(self, tmp_path):
        """测试不存在的配置文件"""
        data_dir = tmp_path / ".jarvis" / "c2rust"
        data_dir.mkdir(parents=True)
        result = load_additional_notes(data_dir)
        assert result == ""

    def test_empty_notes(self, tmp_path):
        """测试空的附加说明"""
        data_dir = tmp_path / ".jarvis" / "c2rust"
        data_dir.mkdir(parents=True)
        config_file = data_dir / "config.json"
        config_file.write_text(json.dumps({"additional_notes": ""}))
        result = load_additional_notes(data_dir)
        assert result == ""

    def test_invalid_json(self, tmp_path):
        """测试无效的 JSON"""
        data_dir = tmp_path / ".jarvis" / "c2rust"
        data_dir.mkdir(parents=True)
        config_file = data_dir / "config.json"
        config_file.write_text("invalid json")
        result = load_additional_notes(data_dir)
        assert result == ""


class TestNormalizeList:
    """测试 normalize_list 函数"""

    def test_normal_list(self):
        """测试正常列表"""
        result = normalize_list(["a", "b", "c"])
        assert result == ["a", "b", "c"]

    def test_with_duplicates(self):
        """测试包含重复项"""
        result = normalize_list(["a", "b", "a", "c", "b"])
        assert result == ["a", "b", "c"]  # 去重

    def test_with_whitespace(self):
        """测试包含空白字符"""
        result = normalize_list([" a ", "  b  ", "c"])
        assert result == ["a", "b", "c"]

    def test_empty_list(self):
        """测试空列表"""
        result = normalize_list([])
        assert result == []

    def test_none_input(self):
        """测试 None 输入"""
        result = normalize_list(None)
        assert result == []

    def test_non_list_input(self):
        """测试非列表输入"""
        result = normalize_list("not a list")
        assert result == []

    def test_empty_strings(self):
        """测试包含空字符串"""
        result = normalize_list(["a", "", "b", "  ", "c"])
        assert result == ["a", "b", "c"]


class TestNormalizeListLower:
    """测试 normalize_list_lower 函数"""

    def test_lowercase_conversion(self):
        """测试转换为小写"""
        result = normalize_list_lower(["A", "B", "C"])
        assert result == ["a", "b", "c"]

    def test_mixed_case(self):
        """测试混合大小写"""
        result = normalize_list_lower(["Hello", "WORLD", "test"])
        # 转小写、去重并排序
        assert result == ["hello", "test", "world"]

    def test_with_duplicates(self):
        """测试包含重复项（先转小写，再去重并排序）"""
        result = normalize_list_lower(["A", "a", "B", "b"])
        # 先转小写 -> ["a", "a", "b", "b"]
        # 再去重并排序 -> ["a", "b"]
        assert result == ["a", "b"]


class TestIsEntryFunction:
    """测试 is_entry_function 函数"""

    def test_main_function(self):
        """测试 main 函数"""
        rec = {"name": "main", "qualified_name": "main"}
        assert is_entry_function(rec) is True

    def test_qualified_main(self):
        """测试限定的 main 函数"""
        rec = {"name": "main", "qualified_name": "namespace::main"}
        assert is_entry_function(rec) is True

    def test_non_main_function(self):
        """测试非 main 函数"""
        rec = {"name": "other_func", "qualified_name": "other_func"}
        assert is_entry_function(rec) is False

    def test_custom_entry_via_env(self, monkeypatch):
        """测试通过环境变量自定义入口函数"""
        monkeypatch.setenv("c2rust_delay_entry_symbols", "custom_entry")
        rec = {"name": "custom_entry", "qualified_name": "custom_entry"}
        assert is_entry_function(rec) is True

    def test_custom_entry_multiple(self, monkeypatch):
        """测试多个自定义入口函数"""
        monkeypatch.setenv("c2rust_delay_entry_symbols", "entry1,entry2")
        rec1 = {"name": "entry1", "qualified_name": "entry1"}
        rec2 = {"name": "entry2", "qualified_name": "entry2"}
        rec3 = {"name": "other", "qualified_name": "other"}
        assert is_entry_function(rec1) is True
        assert is_entry_function(rec2) is True
        assert is_entry_function(rec3) is False

    def test_custom_entry_qualified(self, monkeypatch):
        """测试限定的自定义入口函数"""
        monkeypatch.setenv("c2rust_delay_entry_symbols", "MyClass::init")
        rec = {"name": "init", "qualified_name": "MyClass::init"}
        assert is_entry_function(rec) is True

    def test_case_insensitive(self, monkeypatch):
        """测试大小写不敏感"""
        monkeypatch.setenv("c2rust_delay_entry_symbols", "CUSTOM")
        rec = {"name": "custom", "qualified_name": "custom"}
        assert is_entry_function(rec) is True

    def test_empty_name(self):
        """测试空名称"""
        rec = {"name": "", "qualified_name": ""}
        assert is_entry_function(rec) is False
