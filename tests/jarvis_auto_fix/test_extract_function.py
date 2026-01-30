"""Tests for ExtractFunctionRefactorer.

This module contains unit tests for the extract function refactoring functionality.
"""

import os
import tempfile

import pytest

from jarvis.jarvis_auto_fix.fix_history import FixHistory
from jarvis.jarvis_auto_fix.refactoring.extract_function import (
    ExtractFunctionRefactorer,
    ExtractionResult,
    VariableAnalyzer,
    VariableInfo,
)


class TestVariableAnalyzer:
    """Tests for VariableAnalyzer class."""

    def test_simple_assignment(self):
        """Test detection of simple variable assignment."""
        import ast

        code = "x = 1\ny = x + 2"
        tree = ast.parse(code)
        analyzer = VariableAnalyzer()
        analyzer.visit(tree)

        assert "x" in analyzer.defined
        assert "y" in analyzer.defined
        assert "x" in analyzer.used

    def test_function_definition(self):
        """Test detection of function definition."""
        import ast

        code = "def foo():\n    pass"
        tree = ast.parse(code)
        analyzer = VariableAnalyzer()
        analyzer.visit(tree)

        assert "foo" in analyzer.defined

    def test_for_loop_variable(self):
        """Test detection of for loop variable."""
        import ast

        code = "for i in range(10):\n    print(i)"
        tree = ast.parse(code)
        analyzer = VariableAnalyzer()
        analyzer.visit(tree)

        assert "i" in analyzer.defined
        assert "range" in analyzer.used
        assert "print" in analyzer.used

    def test_import_statement(self):
        """Test detection of import statement."""
        import ast

        code = "import os\nfrom pathlib import Path"
        tree = ast.parse(code)
        analyzer = VariableAnalyzer()
        analyzer.visit(tree)

        assert "os" in analyzer.defined
        assert "Path" in analyzer.defined


class TestExtractFunctionRefactorer:
    """Tests for ExtractFunctionRefactorer class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def refactorer(self, temp_dir):
        """Create a refactorer with a temporary history file."""
        history_file = os.path.join(temp_dir, "fix_history.json")
        history = FixHistory(history_file=history_file)
        return ExtractFunctionRefactorer(history=history)

    def test_extract_simple_block(self, temp_dir, refactorer):
        """Test extracting a simple code block."""
        code = """def main():
    x = 1
    y = 2
    result = x + y
    print(result)
"""
        file_path = os.path.join(temp_dir, "test_simple.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.extract_function(
            file_path=file_path,
            start_line=3,
            end_line=4,
            function_name="calculate_sum",
        )

        assert result.success
        assert "def calculate_sum" in result.new_function
        assert "calculate_sum(" in result.call_statement

    def test_extract_with_inputs(self, temp_dir, refactorer):
        """Test extracting code that uses external variables."""
        code = """def main():
    x = 10
    y = 20
    result = x * y
    print(result)
"""
        file_path = os.path.join(temp_dir, "test_inputs.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.extract_function(
            file_path=file_path,
            start_line=4,
            end_line=4,
            function_name="multiply",
        )

        assert result.success
        # Should have x and y as parameters
        assert "x" in result.new_function or "y" in result.new_function

    def test_extract_with_outputs(self, temp_dir, refactorer):
        """Test extracting code that produces output variables."""
        code = """def main():
    a = 5
    b = a * 2
    print(b)
"""
        file_path = os.path.join(temp_dir, "test_outputs.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.extract_function(
            file_path=file_path,
            start_line=3,
            end_line=3,
            function_name="double_value",
        )

        assert result.success
        # Should return b since it's used after
        assert "return" in result.new_function

    def test_invalid_line_range(self, temp_dir, refactorer):
        """Test with invalid line range."""
        code = "x = 1\ny = 2\n"
        file_path = os.path.join(temp_dir, "test_invalid.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.extract_function(
            file_path=file_path,
            start_line=10,
            end_line=20,
            function_name="invalid",
        )

        assert not result.success
        assert "Invalid line range" in result.error_message

    def test_invalid_function_name(self, temp_dir, refactorer):
        """Test with invalid function name."""
        code = "x = 1\ny = 2\n"
        file_path = os.path.join(temp_dir, "test_name.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.extract_function(
            file_path=file_path,
            start_line=1,
            end_line=1,
            function_name="123invalid",
        )

        assert not result.success
        assert "Invalid function name" in result.error_message

    def test_file_not_found(self, refactorer):
        """Test with non-existent file."""
        result = refactorer.extract_function(
            file_path="/nonexistent/file.py",
            start_line=1,
            end_line=1,
            function_name="test",
        )

        assert not result.success
        assert "File not found" in result.error_message

    def test_syntax_error_in_file(self, temp_dir, refactorer):
        """Test with file containing syntax error."""
        code = "def broken(:\n    pass\n"
        file_path = os.path.join(temp_dir, "test_syntax.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.extract_function(
            file_path=file_path,
            start_line=1,
            end_line=1,
            function_name="test",
        )

        assert not result.success
        assert "Syntax error" in result.error_message

    def test_rollback_available(self, temp_dir, refactorer):
        """Test that rollback is available after extraction."""
        code = """def main():
    x = 1
    y = 2
    print(x + y)
"""
        file_path = os.path.join(temp_dir, "test_rollback.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.extract_function(
            file_path=file_path,
            start_line=2,
            end_line=3,
            function_name="init_vars",
        )

        assert result.success

        # Check that fix was recorded
        fixes = refactorer.history.get_fixes_for_file(file_path)
        assert len(fixes) > 0
        assert fixes[0].rollback_available

    def test_no_return_option(self, temp_dir, refactorer):
        """Test extraction without return statement."""
        code = """def main():
    print("hello")
    print("world")
"""
        file_path = os.path.join(temp_dir, "test_no_return.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.extract_function(
            file_path=file_path,
            start_line=2,
            end_line=3,
            function_name="greet",
            add_return=False,
        )

        assert result.success
        # Should not have return statement for void function
        assert (
            "return" not in result.new_function
            or result.new_function.count("return") == 0
        )

    def test_analyze_extraction_candidates(self, temp_dir, refactorer):
        """Test analyzing file for extraction candidates."""
        # Create a file with a long function
        lines = ["def long_function():"]
        for i in range(60):
            lines.append(f"    x{i} = {i}")
        code = "\n".join(lines)

        file_path = os.path.join(temp_dir, "test_candidates.py")
        with open(file_path, "w") as f:
            f.write(code)

        candidates = refactorer.analyze_extraction_candidates(file_path)

        # Should find the long function as a candidate
        assert len(candidates) > 0
        assert "long_function" in candidates[0][2]

    def test_is_valid_identifier(self, refactorer):
        """Test identifier validation."""
        assert refactorer._is_valid_identifier("valid_name")
        assert refactorer._is_valid_identifier("validName")
        assert not refactorer._is_valid_identifier("123invalid")
        assert not refactorer._is_valid_identifier("")
        assert not refactorer._is_valid_identifier("_private")  # Starts with underscore

    def test_dedent_code(self, refactorer):
        """Test code dedentation."""
        code = "    x = 1\n    y = 2"
        dedented = refactorer._dedent_code(code)
        assert dedented == "x = 1\ny = 2"

    def test_detect_indentation(self, refactorer):
        """Test indentation detection."""
        lines = ["    x = 1\n", "    y = 2\n"]
        indent = refactorer._detect_indentation(lines)
        assert indent == "    "


class TestVariableInfo:
    """Tests for VariableInfo dataclass."""

    def test_variable_info_creation(self):
        """Test creating VariableInfo."""
        info = VariableInfo(
            inputs={"a", "b"},
            outputs={"c"},
            locals={"temp"},
        )
        assert "a" in info.inputs
        assert "b" in info.inputs
        assert "c" in info.outputs
        assert "temp" in info.locals


class TestExtractionResult:
    """Tests for ExtractionResult dataclass."""

    def test_successful_result(self):
        """Test creating successful result."""
        result = ExtractionResult(
            success=True,
            new_function="def foo(): pass",
            call_statement="foo()",
        )
        assert result.success
        assert result.new_function == "def foo(): pass"
        assert result.call_statement == "foo()"
        assert result.error_message == ""

    def test_failed_result(self):
        """Test creating failed result."""
        result = ExtractionResult(
            success=False,
            error_message="Something went wrong",
        )
        assert not result.success
        assert result.error_message == "Something went wrong"
        assert result.new_function == ""
        assert result.call_statement == ""
