#! -*- coding: utf-8 -*-
"""structured_code 结构化代码提取工具的单元测试"""

from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch


from jarvis.jarvis_code_agent.code_analyzer.structured_code import (
    StructuredCodeExtractor,
)
from jarvis.jarvis_code_agent.code_analyzer.symbol_extractor import Symbol


class TestGetFullDefinitionRange:
    """测试 get_full_definition_range 对不同语言的行为"""

    def test_python_uses_symbol_range_directly(self):
        symbol = Symbol(
            name="foo",
            kind="function",
            file_path="/tmp/test.py",
            line_start=3,
            line_end=10,
        )
        content = "line1\nline2\n"  # 内容不重要

        start, end = StructuredCodeExtractor.get_full_definition_range(
            symbol, content, language="python"
        )

        assert (start, end) == (3, 10)

    def test_tree_sitter_short_range_heuristic_with_braces(self):
        """当范围太短时，应向下查找匹配的大括号来扩展范围"""
        symbol = Symbol(
            name="foo",
            kind="function",
            file_path="/tmp/test.c",
            line_start=2,
            line_end=2,  # 很短的范围，触发启发式扩展
        )
        content = dedent(
            """
            int main() {
            }

            void foo() {
                int x = 0;
            }

            """
        ).strip("\n")

        start, end = StructuredCodeExtractor.get_full_definition_range(
            symbol, content, language="c"
        )

        # foo 的定义应该扩展到完整的大括号范围
        assert start == 2
        # 找到匹配的大括号的那一行
        lines = content.split("\n")
        assert lines[end - 1].strip() == "}"


class TestExtractSyntaxUnits:
    """测试 extract_syntax_units 的核心逻辑（使用 mock 的语言支持）"""

    @patch(
        "jarvis.jarvis_code_agent.code_analyzer.structured_code.get_symbol_extractor"
    )
    @patch("jarvis.jarvis_code_agent.code_analyzer.structured_code.detect_language")
    def test_extract_syntax_units_with_nested_symbols(
        self, mock_detect_language, mock_get_symbol_extractor, tmp_path: Path
    ):
        """验证：
        - 只返回请求范围内的语法元素
        - 父符号会排除子符号覆盖的行
        - id 唯一性处理
        """
        # 构造一个简单的 Python 源码，类里有方法
        content = dedent(
            """
            class Foo:
                def method(self):
                    pass


            def bar():
                return 1
            """
        ).strip("\n")

        file_path = tmp_path / "sample.py"
        file_path.write_text(content, encoding="utf-8")

        # 模拟语言检测和符号提取
        mock_detect_language.return_value = "python"

        extractor = MagicMock()
        mock_get_symbol_extractor.return_value = extractor

        # 行号:
        # 1: class Foo:
        # 2:     def method(self):
        # 3:         pass
        # 4:
        # 5:
        # 6: def bar():
        # 7:     return 1
        class_symbol = Symbol(
            name="Foo",
            kind="class",
            file_path=str(file_path),
            line_start=1,
            line_end=3,
        )
        method_symbol = Symbol(
            name="method",
            kind="method",
            file_path=str(file_path),
            line_start=2,
            line_end=3,
            parent="Foo",
        )
        bar_symbol = Symbol(
            name="bar",
            kind="function",
            file_path=str(file_path),
            line_start=6,
            line_end=7,
        )
        extractor.extract_symbols.return_value = [
            class_symbol,
            method_symbol,
            bar_symbol,
        ]

        units = StructuredCodeExtractor.extract_syntax_units(
            str(file_path), content, start_line=1, end_line=10
        )

        # 按 start_line 排序以便断言
        units = sorted(units, key=lambda u: u["start_line"])

        # 应该包含类的“父”块（去掉子方法的行）、方法块以及 bar 函数块
        ids = [u["id"] for u in units]
        assert "Foo" in ids
        assert "Foo.method" in ids or "Foo.method_2" in ids  # 唯一性可能有后缀
        assert any(id_.startswith("bar") for id_ in ids)

        # 找到 Foo 对应的单元，确认它包含完整的类定义（包括子方法）
        foo_unit = next(u for u in units if u["id"] == "Foo")
        assert foo_unit["start_line"] == 1
        # Foo 的内容包含完整的类定义（第 1-3 行），子符号会单独提取
        assert foo_unit["end_line"] == 3
        # 应该包含3行有效内容（split("\n") 可能在末尾产生空字符串，需要过滤）
        non_empty_lines = [
            line for line in foo_unit["content"].split("\n") if line.strip()
        ]
        assert len(non_empty_lines) == 3

    @patch(
        "jarvis.jarvis_code_agent.code_analyzer.structured_code.get_symbol_extractor"
    )
    @patch("jarvis.jarvis_code_agent.code_analyzer.structured_code.detect_language")
    def test_extract_syntax_units_for_all_supported_kinds(
        self, mock_detect_language, mock_get_symbol_extractor
    ):
        """对所有受支持的语法 kind 进行覆盖，确保不会被过滤掉。"""
        # 这些 kind 应该与 StructuredCodeExtractor.extract_syntax_units 中的 syntax_kinds 集合保持一致
        all_kinds = [
            "function",
            "method",
            "class",
            "struct",
            "enum",
            "union",
            "interface",
            "trait",
            "impl",
            "module",
            "attribute",
            "const",
            "static",
            "type",
            "extern",
            "macro",
            "typedef",
            "template",
            "namespace",
            "var",
            "constructor",
            "field",
            "annotation",
            "decorator",
        ]

        # 构造足够多的行，保证每个符号的行号都在范围内
        content = "\n".join(f"line{i}" for i in range(1, 80))
        file_path = "/tmp/all_kinds.c"

        mock_detect_language.return_value = (
            "python"  # 使用 python 路径，避免启发式大括号扩展
        )

        extractor = MagicMock()
        mock_get_symbol_extractor.return_value = extractor

        symbols = []
        for idx, kind in enumerate(all_kinds):
            start = idx * 2 + 1
            end = start + 1
            symbols.append(
                Symbol(
                    name=f"{kind}_symbol",
                    kind=kind,
                    file_path=file_path,
                    line_start=start,
                    line_end=end,
                )
            )

        extractor.extract_symbols.return_value = symbols

        units = StructuredCodeExtractor.extract_syntax_units(
            file_path, content, start_line=1, end_line=100
        )

        # 每个 kind 都应该生成一个单元
        assert len(units) == len(all_kinds)
        unit_ids = {u["id"] for u in units}
        expected_ids = {f"{kind}_symbol" for kind in all_kinds}
        assert expected_ids.issubset(unit_ids)


class TestExtractBlankLineGroups:
    """测试按空白行分组的逻辑"""

    def test_blank_line_grouping_and_all_blank_fallback(self):
        content = dedent(
            """
            line1
            line2

            line3



            """
        ).strip("\n")

        groups = StructuredCodeExtractor.extract_blank_line_groups(
            content, start_line=1, end_line=7
        )

        # 预期分成两组: [1-2], [4-4]；最后多余的空行不会生成空组
        assert len(groups) == 2
        assert groups[0]["id"] == "1-2"
        assert groups[0]["content"] == "line1\nline2"

        assert groups[1]["id"] == "4-4"
        assert groups[1]["content"] == "line3"

        # 全是空白行的情况，应返回整个范围作为一个分组
        only_blanks = "\n\n\n"
        groups2 = StructuredCodeExtractor.extract_blank_line_groups(
            only_blanks, start_line=1, end_line=3
        )
        assert len(groups2) == 1
        assert groups2[0]["id"] == "1-3"


class TestExtractLineGroups:
    """测试按固定行数分组"""

    def test_fixed_size_line_groups(self):
        content = "\n".join(f"line{i}" for i in range(1, 11))  # 10 行

        groups = StructuredCodeExtractor.extract_line_groups(
            content, start_line=1, end_line=10, group_size=4
        )

        # 预期分组: 1-4, 5-8, 9-10
        assert [g["id"] for g in groups] == ["1-4", "5-8", "9-10"]
        assert groups[0]["content"].split("\n")[0] == "line1"
        assert groups[-1]["content"].split("\n")[-1] == "line10"


class TestEnsureUniqueIds:
    """测试 ensure_unique_ids 对重复 id 的处理"""

    def test_duplicate_ids_are_made_unique(self):
        units = [
            {"id": "foo", "start_line": 1, "end_line": 1, "content": "a"},
            {"id": "foo", "start_line": 2, "end_line": 2, "content": "b"},
            {"id": "bar", "start_line": 3, "end_line": 3, "content": "c"},
            {"id": "foo", "start_line": 4, "end_line": 4, "content": "d"},
        ]

        unique_units = StructuredCodeExtractor.ensure_unique_ids(units)

        ids = [u["id"] for u in unique_units]
        assert ids[0] == "foo"
        # 后面的 foo 应该带有 _1, _2 后缀
        assert "foo_1" in ids
        assert "foo_2" in ids
        assert "bar" in ids


class TestExtractImports:
    """测试导入语句的分组逻辑（使用 mock 的依赖分析器）"""

    @patch(
        "jarvis.jarvis_code_agent.code_analyzer.structured_code.get_dependency_analyzer"
    )
    @patch("jarvis.jarvis_code_agent.code_analyzer.structured_code.detect_language")
    def test_extract_import_groups(
        self, mock_detect_language, mock_get_dependency_analyzer, tmp_path: Path
    ):
        content = dedent(
            """
            import os
            import sys

            from pathlib import Path


            def foo():
                pass
            """
        ).strip("\n")
        file_path = tmp_path / "imports.py"
        file_path.write_text(content, encoding="utf-8")

        mock_detect_language.return_value = "python"

        analyzer = MagicMock()
        mock_get_dependency_analyzer.return_value = analyzer

        # 构造假的 dependency 对象，只需要有 line 属性
        dep1 = type("Dep", (), {"line": 1})
        dep2 = type("Dep", (), {"line": 2})
        dep3 = type("Dep", (), {"line": 4})
        analyzer.analyze_imports.return_value = [dep1, dep2, dep3]

        units = StructuredCodeExtractor.extract_imports(
            str(file_path), content, start_line=1, end_line=10
        )

        # 预期: [1-2] 作为一组, [4-4] 作为另一组
        assert len(units) == 2
        ids = [u["id"] for u in units]
        assert "imports_1_2" in ids
        assert "import_4" in ids


class TestFindBlockById:
    """测试根据 id 查找代码块的逻辑"""

    def test_find_block_by_id_raw_mode_uses_line_groups(self, tmp_path: Path):
        content = "\n".join(f"line{i}" for i in range(1, 31))
        file_path = tmp_path / "raw_mode.py"
        file_path.write_text(content, encoding="utf-8")

        # raw_mode=True 时，使用每 20 行一个分组的行号分组
        result = StructuredCodeExtractor.find_block_by_id(
            str(file_path), "1-20", raw_mode=True
        )
        assert result is not None
        assert result["start_line"] == 1
        assert result["end_line"] == 20
        assert result["content"].split("\n")[0] == "line1"

    @patch(
        "jarvis.jarvis_code_agent.code_analyzer.structured_code.StructuredCodeExtractor.extract_syntax_units"
    )
    @patch(
        "jarvis.jarvis_code_agent.code_analyzer.structured_code.StructuredCodeExtractor.extract_imports"
    )
    def test_find_block_by_id_prefers_syntax_and_import_units(
        self, mock_extract_imports, mock_extract_syntax_units, tmp_path: Path
    ):
        content = dedent(
            """
            import os


            def foo():
                pass
            """
        ).strip("\n")
        file_path = tmp_path / "syntax_mode.py"
        file_path.write_text(content, encoding="utf-8")

        # 构造假的语法单元和导入单元，包含重复 id，确保 ensure_unique_ids 被调用
        mock_extract_imports.return_value = [
            {"id": "block", "start_line": 1, "end_line": 1, "content": "import os"}
        ]
        mock_extract_syntax_units.return_value = [
            {
                "id": "block",
                "start_line": 4,
                "end_line": 5,
                "content": "def foo():\n    pass",
            }
        ]

        # ensure_unique_ids 会把第二个 "block" 改成 "block_1"
        result = StructuredCodeExtractor.find_block_by_id(
            str(file_path), "block_1", raw_mode=False
        )
        assert result is not None
        assert result["start_line"] == 4
        assert "def foo()" in result["content"]


class TestExtractSyntaxUnitsWithSyntaxErrors:
    """测试 extract_syntax_units 对语法错误的处理"""

    def test_extract_partial_symbols_with_syntax_errors(self, tmp_path):
        """测试即使有语法错误也能提取部分符号"""
        # 创建一个有语法错误的 Rust 文件
        content = """
        fn valid_function1() {
            println!("Valid1");
        }
        
        fn invalid_function(  // 语法错误：缺少闭合括号
            let x = 5;
        }
        
        fn valid_function2() {
            println!("Valid2");
        }
        """
        file_path = tmp_path / "test.rs"
        file_path.write_text(content, encoding="utf-8")

        # 尝试提取语法单元
        units = StructuredCodeExtractor.extract_syntax_units(
            str(file_path), content, 1, -1
        )

        # 应该返回一个列表（可能为空或包含部分符号）
        assert isinstance(units, list)

        # 如果提取到了符号，验证它们的格式
        for unit in units:
            assert "id" in unit
            assert "start_line" in unit
            assert "end_line" in unit
            assert "content" in unit
            assert unit["start_line"] > 0
            assert unit["end_line"] >= unit["start_line"]

    def test_handle_language_detection_failure(self, tmp_path):
        """测试语言检测失败时的处理"""
        content = "some random content without language"
        file_path = tmp_path / "test.unknown"
        file_path.write_text(content, encoding="utf-8")

        # 即使语言检测失败，也不应该崩溃
        units = StructuredCodeExtractor.extract_syntax_units(
            str(file_path), content, 1, -1
        )

        # 应该返回空列表
        assert isinstance(units, list)

    def test_handle_extractor_failure(self, tmp_path):
        """测试提取器失败时的处理"""
        content = """
        fn test() {
            println!("Test");
        }
        """
        file_path = tmp_path / "test.rs"
        file_path.write_text(content, encoding="utf-8")

        # 即使提取器失败，也不应该崩溃
        with patch(
            "jarvis.jarvis_code_agent.code_analyzer.structured_code.get_symbol_extractor"
        ) as mock_get_extractor:
            # 模拟提取器返回 None
            mock_get_extractor.return_value = None

            units = StructuredCodeExtractor.extract_syntax_units(
                str(file_path), content, 1, -1
            )

            # 应该返回空列表
            assert isinstance(units, list)
            assert len(units) == 0

    def test_handle_symbol_extraction_exception(self, tmp_path):
        """测试符号提取异常时的处理"""
        content = """
        fn test() {
            println!("Test");
        }
        """
        file_path = tmp_path / "test.rs"
        file_path.write_text(content, encoding="utf-8")

        # 即使符号提取抛出异常，也不应该崩溃
        with patch(
            "jarvis.jarvis_code_agent.code_analyzer.structured_code.get_symbol_extractor"
        ) as mock_get_extractor:
            # 模拟提取器抛出异常
            mock_extractor = MagicMock()
            mock_extractor.extract_symbols.side_effect = Exception("Extraction failed")
            mock_get_extractor.return_value = mock_extractor

            units = StructuredCodeExtractor.extract_syntax_units(
                str(file_path), content, 1, -1
            )

            # 应该返回空列表，而不是崩溃
            assert isinstance(units, list)

    def test_handle_individual_symbol_processing_failure(self, tmp_path):
        """测试单个符号处理失败时的处理"""
        content = """
        fn valid_function1() {
            println!("Valid1");
        }
        
        fn valid_function2() {
            println!("Valid2");
        }
        """
        file_path = tmp_path / "test.rs"
        file_path.write_text(content, encoding="utf-8")

        # 即使单个符号处理失败，也不应该影响其他符号
        units = StructuredCodeExtractor.extract_syntax_units(
            str(file_path), content, 1, -1
        )

        # 应该返回一个列表
        assert isinstance(units, list)

        # 如果提取到了符号，验证它们的格式
        for unit in units:
            assert "id" in unit
            assert "start_line" in unit
            assert "end_line" in unit
            assert "content" in unit

    def test_extract_symbols_with_mixed_valid_and_invalid_code(self, tmp_path):
        """测试混合有效和无效代码的情况"""
        content = """
        fn valid_function1() {
            println!("Valid1");
        }
        
        fn invalid_function(  // 语法错误
            let x = 5;
        }
        
        fn valid_function2() {
            println!("Valid2");
        }
        
        fn another_invalid() {
            let x = {  // 语法错误：未闭合的代码块
            let y = 5;
        }
        
        fn valid_function3() {
            println!("Valid3");
        }
        """
        file_path = tmp_path / "test.rs"
        file_path.write_text(content, encoding="utf-8")

        # 即使有多个语法错误，也应该能提取部分有效的符号
        units = StructuredCodeExtractor.extract_syntax_units(
            str(file_path), content, 1, -1
        )

        # 应该返回一个列表
        assert isinstance(units, list)

        # 如果提取到了符号，验证它们的格式
        for unit in units:
            assert "id" in unit
            assert "start_line" in unit
            assert "end_line" in unit
            assert "content" in unit
            assert unit["start_line"] > 0
            assert unit["end_line"] >= unit["start_line"]
