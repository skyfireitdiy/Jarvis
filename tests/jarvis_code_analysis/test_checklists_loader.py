# -*- coding: utf-8 -*-
"""jarvis_code_analysis.checklists.loader 模块单元测试"""

import pytest

from jarvis.jarvis_code_analysis.checklists.loader import (
    get_language_checklist,
    get_all_checklists,
    CHECKLIST_MAP,
)


class TestGetLanguageChecklist:
    """测试 get_language_checklist 函数"""

    def test_existing_language(self):
        """测试存在的语言"""
        result = get_language_checklist("python")
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    def test_existing_language_c_cpp(self):
        """测试 C/C++ 语言"""
        result = get_language_checklist("c_cpp")
        assert result is not None
        assert isinstance(result, str)

    def test_existing_language_go(self):
        """测试 Go 语言"""
        result = get_language_checklist("go")
        assert result is not None
        assert isinstance(result, str)

    def test_existing_language_rust(self):
        """测试 Rust 语言"""
        result = get_language_checklist("rust")
        assert result is not None
        assert isinstance(result, str)

    def test_existing_language_java(self):
        """测试 Java 语言"""
        result = get_language_checklist("java")
        assert result is not None
        assert isinstance(result, str)

    def test_existing_language_javascript(self):
        """测试 JavaScript 语言"""
        result = get_language_checklist("javascript")
        assert result is not None
        assert isinstance(result, str)

    def test_typescript_uses_javascript(self):
        """测试 TypeScript 使用 JavaScript 检查清单"""
        js_result = get_language_checklist("javascript")
        ts_result = get_language_checklist("typescript")
        assert ts_result is not None
        assert ts_result == js_result

    def test_nonexistent_language(self):
        """测试不存在的语言"""
        result = get_language_checklist("nonexistent_language")
        assert result is None

    def test_empty_string(self):
        """测试空字符串"""
        result = get_language_checklist("")
        assert result is None

    def test_all_mapped_languages(self):
        """测试所有映射的语言都有检查清单"""
        for language in CHECKLIST_MAP.keys():
            result = get_language_checklist(language)
            assert result is not None, f"Language {language} should have a checklist"
            assert isinstance(result, str)
            assert len(result) > 0


class TestGetAllChecklists:
    """测试 get_all_checklists 函数"""

    def test_returns_dict(self):
        """测试返回字典类型"""
        result = get_all_checklists()
        assert isinstance(result, dict)

    def test_contains_languages(self):
        """测试包含语言"""
        result = get_all_checklists()
        assert "python" in result
        assert "java" in result
        assert "rust" in result

    def test_all_values_are_strings(self):
        """测试所有值都是字符串"""
        result = get_all_checklists()
        for language, checklist in result.items():
            assert isinstance(checklist, str), f"Checklist for {language} should be a string"
            assert len(checklist) > 0, f"Checklist for {language} should not be empty"

    def test_matches_checklist_map(self):
        """测试与 CHECKLIST_MAP 匹配"""
        result = get_all_checklists()
        assert result == CHECKLIST_MAP

