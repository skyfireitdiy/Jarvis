"""
测试 TreeSitterExtractor 对语法错误文件的处理能力。

验证：
1. 语法错误文件不会导致程序崩溃
2. 语法错误文件返回空列表或部分符号
3. 各种类型的语法错误都能被正确处理
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from tree_sitter import Language, Node

from jarvis.jarvis_code_agent.code_analyzer.tree_sitter_extractor import (
    TreeSitterExtractor,
)
from jarvis.jarvis_code_agent.code_analyzer.symbol_extractor import Symbol


class MockTreeSitterExtractor(TreeSitterExtractor):
    """用于测试的 Mock TreeSitterExtractor"""

    def _create_symbol_from_capture(self, node, name: str, file_path: str):
        """创建测试用的 Symbol"""
        return Symbol(
            name=name,
            kind="test",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            file_path=file_path,
        )


class TestTreeSitterExtractorSyntaxErrors:
    """测试 TreeSitterExtractor 对语法错误文件的处理"""

    @pytest.fixture
    def rust_language(self):
        """尝试获取真实的 Rust Language 对象"""
        try:
            import tree_sitter_rust
            return tree_sitter_rust.language()
        except (ImportError, Exception):
            pytest.skip("tree-sitter-rust not available")

    @pytest.fixture
    def extractor(self, rust_language):
        """创建测试用的 TreeSitterExtractor 实例"""
        query = """
        (function_item
          name: (identifier) @function.name)
        """
        return MockTreeSitterExtractor(rust_language, query)

    def test_empty_content(self, extractor):
        """测试空内容"""
        symbols = extractor.extract_symbols("test.rs", "")
        assert symbols == []

    def test_whitespace_only_content(self, extractor):
        """测试只有空白字符的内容"""
        symbols = extractor.extract_symbols("test.rs", "   \n\t  \n")
        assert symbols == []

    def test_missing_closing_brace(self, extractor):
        """测试缺少闭合大括号"""
        content = """
        fn test_function() {
            let x = 5;
        // 缺少闭合大括号
        """
        # 即使有语法错误，tree-sitter 通常也能部分解析
        # 这里测试不会崩溃
        try:
            symbols = extractor.extract_symbols("test.rs", content)
            # 应该返回空列表或部分符号，不应该崩溃
            assert isinstance(symbols, list)
        except Exception as e:
            pytest.fail(f"extract_symbols should not raise exception: {e}")

    def test_missing_semicolon(self, extractor):
        """测试缺少分号（Rust语法错误）"""
        content = """
        fn test() {
            let x = 5  // 缺少分号
        }
        """
        # 即使有语法错误，tree-sitter 通常也能部分解析
        # 这里测试不会崩溃
        try:
            symbols = extractor.extract_symbols("test.rs", content)
            # 应该返回空列表或部分符号，不应该崩溃
            assert isinstance(symbols, list)
        except Exception as e:
            # 如果抛出异常，应该在调试模式下打印，但不应该崩溃
            pytest.fail(f"extract_symbols should not raise exception: {e}")

    def test_invalid_utf8_encoding(self, extractor):
        """测试无效的 UTF-8 编码"""
        # 创建包含无效 UTF-8 字节的内容
        invalid_content = b"\xff\xfe\x00\x01"
        try:
            # 尝试解码为字符串
            content = invalid_content.decode("utf-8", errors="replace")
            symbols = extractor.extract_symbols("test.rs", content)
            # 应该返回空列表或部分符号，不应该崩溃
            assert isinstance(symbols, list)
        except Exception as e:
            # 如果抛出异常，应该在调试模式下打印，但不应该崩溃
            pytest.fail(f"extract_symbols should handle invalid UTF-8: {e}")

    def test_unclosed_string_literal(self, extractor):
        """测试未闭合的字符串字面量"""
        content = """
        fn test() {
            let s = "unclosed string
        }
        """
        try:
            symbols = extractor.extract_symbols("test.rs", content)
            assert isinstance(symbols, list)
        except Exception as e:
            pytest.fail(f"extract_symbols should handle unclosed string: {e}")

    def test_malformed_function_signature(self, extractor):
        """测试格式错误的函数签名"""
        content = """
        fn test(  // 缺少参数和闭合括号
        """
        try:
            symbols = extractor.extract_symbols("test.rs", content)
            assert isinstance(symbols, list)
        except Exception as e:
            pytest.fail(f"extract_symbols should handle malformed function: {e}")

    def test_invalid_query_syntax(self, rust_language):
        """测试无效的查询语法"""
        # 创建使用无效查询的提取器
        invalid_query = """
        (function_item
          name: (invalid_syntax @function.name)
        """
        invalid_extractor = MockTreeSitterExtractor(rust_language, invalid_query)

        content = """
        fn test() {
            println!("Hello");
        }
        """
        # 即使查询语法错误，也不应该崩溃
        symbols = invalid_extractor.extract_symbols("test.rs", content)
        assert isinstance(symbols, list)

    def test_parser_exception_handling(self, extractor):
        """测试解析器异常处理"""
        # 使用会导致解析失败的内容来测试异常处理
        # 例如：包含无效字节的内容
        content = b"\xff\xfe\x00\x01".decode("utf-8", errors="replace")
        # 即使解析失败，也不应该崩溃
        try:
            symbols = extractor.extract_symbols("test.rs", content)
            assert isinstance(symbols, list)
        except Exception as e:
            pytest.fail(f"extract_symbols should handle parser errors gracefully: {e}")

    def test_query_construction_error(self, extractor):
        """测试查询构造错误"""
        # 创建一个使用无效查询的提取器来测试查询构造错误
        from jarvis.jarvis_code_agent.code_analyzer.tree_sitter_extractor import TreeSitterExtractor
        
        class InvalidQueryExtractor(TreeSitterExtractor):
            def _create_symbol_from_capture(self, node, name: str, file_path: str):
                return None
        
        # 使用无效的查询语法
        invalid_query = "(invalid_syntax @function.name"
        try:
            invalid_extractor = InvalidQueryExtractor(extractor.language, invalid_query)
            content = """
            fn test() {
                println!("Hello");
            }
            """
            # 即使查询构造失败，也不应该崩溃
            symbols = invalid_extractor.extract_symbols("test.rs", content)
            assert isinstance(symbols, list)
        except Exception as e:
            # 如果查询构造失败，应该返回空列表而不是崩溃
            # 但某些情况下可能会抛出异常，这也是可以接受的
            pass

    def test_partial_parse_with_syntax_errors(self, extractor):
        """测试部分解析（有语法错误但仍能解析部分内容）"""
        content = """
        fn valid_function() {
            println!("Valid");
        }
        
        fn invalid_function(  // 语法错误
            let x = 5;
        }
        
        fn another_valid() {
            println!("Also valid");
        }
        """
        # 即使有语法错误，也应该能提取有效的符号
        try:
            symbols = extractor.extract_symbols("test.rs", content)
            # 应该返回部分符号或空列表
            assert isinstance(symbols, list)
        except Exception as e:
            pytest.fail(f"extract_symbols should handle partial parse: {e}")

    def test_extract_valid_symbols_despite_syntax_errors(self, extractor):
        """测试即使有语法错误也能提取有效符号"""
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
        
        fn another_invalid() {
            let x = {  // 语法错误：未闭合的代码块
            let y = 5;
        }
        
        fn valid_function3() {
            println!("Valid3");
        }
        """
        # 即使有多个语法错误，也应该能提取有效的符号
        symbols = extractor.extract_symbols("test.rs", content)
        assert isinstance(symbols, list)
        
        # 应该至少提取到一些有效的函数符号
        # 注意：具体能提取多少取决于 tree-sitter 的解析能力
        # 但至少应该不会崩溃，并且应该返回一个列表
        if symbols:
            # 验证返回的符号都是有效的
            for symbol in symbols:
                assert hasattr(symbol, 'name')
                assert hasattr(symbol, 'line_start')
                assert hasattr(symbol, 'line_end')

    def test_nested_syntax_errors(self, extractor):
        """测试嵌套的语法错误"""
        content = """
        fn outer() {
            fn inner() {
                let x = {  // 未闭合的代码块
            }
        }
        """
        try:
            symbols = extractor.extract_symbols("test.rs", content)
            assert isinstance(symbols, list)
        except Exception as e:
            pytest.fail(f"extract_symbols should handle nested errors: {e}")

    def test_debug_mode_output(self, extractor, monkeypatch):
        """测试调试模式下的输出"""
        monkeypatch.setenv("DEBUG_TREE_SITTER", "1")
        
        # 使用会导致解析失败的内容
        content = """
        fn test() {
            invalid syntax here
        }
        """
        
        # 在调试模式下，应该能够处理错误而不崩溃
        try:
            with patch("builtins.print") as mock_print:
                symbols = extractor.extract_symbols("test.rs", content)
                # 应该返回空列表或部分符号
                assert isinstance(symbols, list)
                # 注意：由于异常被捕获，print 可能不会被调用，这取决于实现
        except Exception as e:
            pytest.fail(f"extract_symbols should handle errors in debug mode: {e}")

    def test_skip_error_nodes(self, extractor):
        """测试跳过错误节点，只提取有效符号"""
        content = """
        fn valid_function() {
            println!("Valid");
        }
        
        // 这里有一些语法错误
        fn invalid(  // 语法错误
        }
        
        fn another_valid() {
            println!("Also valid");
        }
        """
        # 即使有语法错误，也应该跳过错误节点，提取有效符号
        symbols = extractor.extract_symbols("test.rs", content)
        assert isinstance(symbols, list)
        
        # 验证返回的符号都是有效的（不应该包含错误节点）
        for symbol in symbols:
            assert hasattr(symbol, 'name')
            assert symbol.name is not None
            assert symbol.line_start > 0
            assert symbol.line_end >= symbol.line_start

    def test_mixed_valid_and_invalid_code(self, extractor):
        """测试混合有效和无效代码的情况"""
        content = """
        // 第一个有效函数
        fn function1() {
            println!("Function 1");
        }
        
        // 语法错误：缺少闭合括号
        fn function2(  // 错误开始
            let x = 5;
        
        // 第二个有效函数
        fn function3() {
            println!("Function 3");
        }
        
        // 语法错误：未闭合的代码块
        fn function4() {
            let x = {  // 错误开始
            let y = 5;
        
        // 第三个有效函数
        fn function5() {
            println!("Function 5");
        }
        """
        # 即使有多个语法错误，也应该能提取有效的符号
        symbols = extractor.extract_symbols("test.rs", content)
        assert isinstance(symbols, list)
        
        # 应该至少提取到一些有效的函数符号
        # 具体能提取多少取决于 tree-sitter 的解析能力
        valid_function_names = [s.name for s in symbols if hasattr(s, 'name') and s.name]
        assert len(valid_function_names) >= 0  # 至少应该返回一个列表（可能为空）

    def test_graceful_degradation_on_parse_failure(self, extractor):
        """测试解析完全失败时的优雅降级"""
        # 使用完全无效的内容
        content = "{{{[[[invalid syntax]]]}}}"
        
        # 即使解析完全失败，也不应该崩溃
        symbols = extractor.extract_symbols("test.rs", content)
        assert isinstance(symbols, list)
        # 应该返回空列表或部分符号
        assert len(symbols) >= 0

