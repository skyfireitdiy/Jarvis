"""Tests for ExtractClassRefactorer.

This module contains unit tests for the extract class refactoring functionality.
"""

import os
import tempfile

import pytest

from jarvis.jarvis_auto_fix.fix_history import FixHistory
from jarvis.jarvis_auto_fix.refactoring.extract_class import (
    ClassExtractionResult,
    ClassMemberAnalyzer,
    ClassMemberInfo,
    ExtractClassRefactorer,
    ExtractionPlan,
)


class TestClassMemberAnalyzer:
    """Tests for ClassMemberAnalyzer class."""

    def test_analyze_methods(self):
        """Test detection of class methods."""
        import ast

        code = """
class MyClass:
    def method1(self):
        pass

    def method2(self):
        self.method1()
"""
        tree = ast.parse(code)
        class_node = tree.body[0]
        analyzer = ClassMemberAnalyzer()
        analyzer.analyze_class(class_node)

        assert "method1" in analyzer.methods
        assert "method2" in analyzer.methods
        assert len(analyzer.methods) == 2

    def test_analyze_class_attributes(self):
        """Test detection of class attributes."""
        import ast

        code = """
class MyClass:
    class_var = 10
    another_var: int = 20
"""
        tree = ast.parse(code)
        class_node = tree.body[0]
        analyzer = ClassMemberAnalyzer()
        analyzer.analyze_class(class_node)

        assert "class_var" in analyzer.class_attributes
        assert "another_var" in analyzer.class_attributes

    def test_analyze_dependencies(self):
        """Test detection of method dependencies."""
        import ast

        code = """
class MyClass:
    def helper(self):
        return 42

    def main_method(self):
        return self.helper() + 1
"""
        tree = ast.parse(code)
        class_node = tree.body[0]
        analyzer = ClassMemberAnalyzer()
        analyzer.analyze_class(class_node)

        assert "helper" in analyzer.methods["main_method"].dependencies
        assert "main_method" in analyzer.methods["helper"].used_by

    def test_analyze_attribute_usage(self):
        """Test detection of attribute usage in methods."""
        import ast

        code = """
class MyClass:
    value = 10

    def get_value(self):
        return self.value
"""
        tree = ast.parse(code)
        class_node = tree.body[0]
        analyzer = ClassMemberAnalyzer()
        analyzer.analyze_class(class_node)

        assert "value" in analyzer.methods["get_value"].dependencies


class TestExtractClassRefactorer:
    """Tests for ExtractClassRefactorer class."""

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
        return ExtractClassRefactorer(history=history)

    def test_extract_simple_methods(self, temp_dir, refactorer):
        """Test extracting simple methods into a new class."""
        code = """
class OriginalClass:
    def method_a(self):
        return 1

    def method_b(self):
        return 2

    def keep_method(self):
        return 3
"""
        file_path = os.path.join(temp_dir, "test_simple.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.extract_class(
            file_path=file_path,
            source_class="OriginalClass",
            methods_to_extract=["method_a", "method_b"],
            new_class_name="ExtractedClass",
        )

        assert result.success
        assert "class ExtractedClass" in result.new_class_code
        assert "def method_a" in result.new_class_code
        assert "def method_b" in result.new_class_code

    def test_extract_with_dependencies(self, temp_dir, refactorer):
        """Test extracting methods with dependencies."""
        code = """
class OriginalClass:
    def helper(self):
        return 42

    def main_method(self):
        return self.helper() + 1

    def other_method(self):
        return 0
"""
        file_path = os.path.join(temp_dir, "test_deps.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.extract_class(
            file_path=file_path,
            source_class="OriginalClass",
            methods_to_extract=["main_method"],
            new_class_name="ExtractedClass",
            include_dependencies=True,
        )

        assert result.success
        # helper should be included due to dependency
        assert "def helper" in result.new_class_code
        assert "def main_method" in result.new_class_code

    def test_class_not_found(self, temp_dir, refactorer):
        """Test with non-existent class."""
        code = "class SomeClass:\n    pass\n"
        file_path = os.path.join(temp_dir, "test_notfound.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.extract_class(
            file_path=file_path,
            source_class="NonExistentClass",
            methods_to_extract=["method"],
            new_class_name="NewClass",
        )

        assert not result.success
        assert "not found" in result.error_message

    def test_method_not_found(self, temp_dir, refactorer):
        """Test with non-existent method."""
        code = "class MyClass:\n    def existing(self):\n        pass\n"
        file_path = os.path.join(temp_dir, "test_method.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.extract_class(
            file_path=file_path,
            source_class="MyClass",
            methods_to_extract=["nonexistent"],
            new_class_name="NewClass",
        )

        assert not result.success
        assert "not found" in result.error_message

    def test_invalid_class_name(self, temp_dir, refactorer):
        """Test with invalid new class name."""
        code = "class MyClass:\n    def method(self):\n        pass\n"
        file_path = os.path.join(temp_dir, "test_invalid.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.extract_class(
            file_path=file_path,
            source_class="MyClass",
            methods_to_extract=["method"],
            new_class_name="123Invalid",
        )

        assert not result.success
        assert "Invalid class name" in result.error_message

    def test_file_not_found(self, refactorer):
        """Test with non-existent file."""
        result = refactorer.extract_class(
            file_path="/nonexistent/file.py",
            source_class="MyClass",
            methods_to_extract=["method"],
            new_class_name="NewClass",
        )

        assert not result.success
        assert "File not found" in result.error_message

    def test_syntax_error_in_file(self, temp_dir, refactorer):
        """Test with file containing syntax error."""
        code = "class Broken(:\n    pass\n"
        file_path = os.path.join(temp_dir, "test_syntax.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.extract_class(
            file_path=file_path,
            source_class="Broken",
            methods_to_extract=["method"],
            new_class_name="NewClass",
        )

        assert not result.success
        assert "Syntax error" in result.error_message

    def test_rollback_available(self, temp_dir, refactorer):
        """Test that rollback is available after extraction."""
        code = """
class MyClass:
    def method(self):
        return 1
"""
        file_path = os.path.join(temp_dir, "test_rollback.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.extract_class(
            file_path=file_path,
            source_class="MyClass",
            methods_to_extract=["method"],
            new_class_name="ExtractedClass",
        )

        assert result.success
        fixes = refactorer.history.get_fixes_for_file(file_path)
        assert len(fixes) > 0
        assert fixes[0].rollback_available


class TestClassMemberInfo:
    """Tests for ClassMemberInfo dataclass."""

    def test_member_info_creation(self):
        """Test creating ClassMemberInfo."""
        info = ClassMemberInfo(
            name="test_method",
            member_type="method",
            start_line=10,
            end_line=20,
            dependencies={"helper"},
            used_by={"main"},
        )
        assert info.name == "test_method"
        assert info.member_type == "method"
        assert info.start_line == 10
        assert info.end_line == 20
        assert "helper" in info.dependencies
        assert "main" in info.used_by


class TestExtractionPlan:
    """Tests for ExtractionPlan dataclass."""

    def test_plan_creation(self):
        """Test creating ExtractionPlan."""
        plan = ExtractionPlan(
            members_to_extract=["method1", "method2"],
            new_class_name="NewClass",
            reference_name="new_class",
            additional_dependencies=["helper"],
        )
        assert "method1" in plan.members_to_extract
        assert plan.new_class_name == "NewClass"
        assert plan.reference_name == "new_class"
        assert "helper" in plan.additional_dependencies


class TestClassExtractionResult:
    """Tests for ClassExtractionResult dataclass."""

    def test_successful_result(self):
        """Test creating successful result."""
        result = ClassExtractionResult(
            success=True,
            new_class_code="class NewClass: pass",
            modified_original_class="class Original: pass",
        )
        assert result.success
        assert result.new_class_code == "class NewClass: pass"
        assert result.error_message == ""

    def test_failed_result(self):
        """Test creating failed result."""
        result = ClassExtractionResult(
            success=False,
            error_message="Something went wrong",
        )
        assert not result.success
        assert result.error_message == "Something went wrong"
        assert result.new_class_code == ""


class TestExtractClassRefactorerAdvanced:
    """Advanced tests for ExtractClassRefactorer."""

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
        return ExtractClassRefactorer(history=history)

    def test_extract_with_class_attributes(self, temp_dir, refactorer):
        """Test extracting methods along with class attributes."""
        code = """
class OriginalClass:
    class_var = 10

    def get_var(self):
        return self.class_var

    def other_method(self):
        return 0
"""
        file_path = os.path.join(temp_dir, "test_attrs.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.extract_class(
            file_path=file_path,
            source_class="OriginalClass",
            methods_to_extract=["get_var"],
            new_class_name="ExtractedClass",
            include_dependencies=True,
        )

        assert result.success
        assert "class ExtractedClass" in result.new_class_code

    def test_extract_without_dependencies(self, temp_dir, refactorer):
        """Test extracting methods without including dependencies."""
        code = """
class OriginalClass:
    def helper(self):
        return 42

    def main_method(self):
        return self.helper() + 1
"""
        file_path = os.path.join(temp_dir, "test_no_deps.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.extract_class(
            file_path=file_path,
            source_class="OriginalClass",
            methods_to_extract=["main_method"],
            new_class_name="ExtractedClass",
            include_dependencies=False,
        )

        assert result.success
        # helper should NOT be included
        assert "def helper" not in result.new_class_code
        assert "def main_method" in result.new_class_code

    def test_custom_reference_name(self, temp_dir, refactorer):
        """Test extraction with custom reference name."""
        code = """
class OriginalClass:
    def method(self):
        return 1
"""
        file_path = os.path.join(temp_dir, "test_ref.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.extract_class(
            file_path=file_path,
            source_class="OriginalClass",
            methods_to_extract=["method"],
            new_class_name="ExtractedClass",
            reference_name="my_custom_ref",
        )

        assert result.success

    def test_analyze_class_cohesion(self, temp_dir, refactorer):
        """Test analyzing class cohesion."""
        code = """
class MyClass:
    def method_a(self):
        return self.method_b()

    def method_b(self):
        return 42

    def unrelated(self):
        return 0
"""
        file_path = os.path.join(temp_dir, "test_cohesion.py")
        with open(file_path, "w") as f:
            f.write(code)

        candidates = refactorer.analyze_class_cohesion(file_path, "MyClass")
        # Should find cohesive groups
        assert isinstance(candidates, list)

    def test_analyze_class_cohesion_class_not_found(self, temp_dir, refactorer):
        """Test analyzing cohesion for non-existent class."""
        code = "class SomeClass:\n    pass\n"
        file_path = os.path.join(temp_dir, "test_cohesion2.py")
        with open(file_path, "w") as f:
            f.write(code)

        candidates = refactorer.analyze_class_cohesion(file_path, "NonExistent")
        assert candidates == []

    def test_analyze_class_cohesion_file_not_found(self, refactorer):
        """Test analyzing cohesion for non-existent file."""
        candidates = refactorer.analyze_class_cohesion("/nonexistent.py", "MyClass")
        assert candidates == []

    def test_to_snake_case(self, refactorer):
        """Test CamelCase to snake_case conversion."""
        assert refactorer._to_snake_case("MyClass") == "my_class"
        assert refactorer._to_snake_case("HTTPServer") == "h_t_t_p_server"
        assert refactorer._to_snake_case("simple") == "simple"

    def test_is_valid_identifier(self, refactorer):
        """Test identifier validation."""
        assert refactorer._is_valid_identifier("valid_name")
        assert refactorer._is_valid_identifier("ValidName")
        assert not refactorer._is_valid_identifier("")
        assert not refactorer._is_valid_identifier("123invalid")
        # Note: 'class' is a keyword but isidentifier() returns True
        # Our implementation only checks isidentifier(), not keywords
        assert refactorer._is_valid_identifier("class")  # isidentifier returns True
