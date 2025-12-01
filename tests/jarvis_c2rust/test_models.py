# -*- coding: utf-8 -*-
"""jarvis_c2rust.models 模块单元测试"""

import pytest

from jarvis.jarvis_c2rust.models import FnRecord


class TestFnRecord:
    """测试 FnRecord 数据类"""

    def test_basic_creation(self):
        """测试基本创建"""
        rec = FnRecord(
            id=1,
            name="test_func",
            qname="test::test_func",
            file="test.c",
            start_line=10,
            start_col=5,
            end_line=20,
            end_col=15,
            refs=["ref1", "ref2"],
        )
        assert rec.id == 1
        assert rec.name == "test_func"
        assert rec.qname == "test::test_func"
        assert rec.file == "test.c"
        assert rec.start_line == 10
        assert rec.start_col == 5
        assert rec.end_line == 20
        assert rec.end_col == 15
        assert rec.refs == ["ref1", "ref2"]

    def test_default_values(self):
        """测试默认值"""
        rec = FnRecord(
            id=1,
            name="test_func",
            qname="test_func",
            file="test.c",
            start_line=1,
            start_col=1,
            end_line=1,
            end_col=1,
            refs=[],
        )
        assert rec.signature == ""
        assert rec.return_type == ""
        assert rec.params is None
        assert rec.lib_replacement is None

    def test_with_signature(self):
        """测试包含签名"""
        rec = FnRecord(
            id=1,
            name="test_func",
            qname="test_func",
            file="test.c",
            start_line=1,
            start_col=1,
            end_line=1,
            end_col=1,
            refs=[],
            signature="int test_func(int x)",
            return_type="int",
            params=[{"name": "x", "type": "int"}],
        )
        assert rec.signature == "int test_func(int x)"
        assert rec.return_type == "int"
        assert rec.params == [{"name": "x", "type": "int"}]

    def test_with_lib_replacement(self):
        """测试包含库替换信息"""
        lib_replacement = {
            "library": "std",
            "function": "memcpy",
            "confidence": 0.9,
        }
        rec = FnRecord(
            id=1,
            name="test_func",
            qname="test_func",
            file="test.c",
            start_line=1,
            start_col=1,
            end_line=1,
            end_col=1,
            refs=[],
            lib_replacement=lib_replacement,
        )
        assert rec.lib_replacement == lib_replacement

    def test_empty_refs(self):
        """测试空引用列表"""
        rec = FnRecord(
            id=1,
            name="test_func",
            qname="test_func",
            file="test.c",
            start_line=1,
            start_col=1,
            end_line=1,
            end_col=1,
            refs=[],
        )
        assert rec.refs == []

    def test_multiple_refs(self):
        """测试多个引用"""
        refs = ["func1", "func2", "func3", "func4", "func5"]
        rec = FnRecord(
            id=1,
            name="test_func",
            qname="test_func",
            file="test.c",
            start_line=1,
            start_col=1,
            end_line=1,
            end_col=1,
            refs=refs,
        )
        assert len(rec.refs) == 5
        assert rec.refs == refs

    def test_complex_qname(self):
        """测试复杂的限定名"""
        rec = FnRecord(
            id=1,
            name="method",
            qname="namespace::Class::method",
            file="test.cpp",
            start_line=1,
            start_col=1,
            end_line=1,
            end_col=1,
            refs=[],
        )
        assert rec.qname == "namespace::Class::method"
        assert rec.name == "method"

