"""Tests for MoveMethodRefactorer.

This module contains unit tests for the move method refactoring functionality.
"""

import ast
import os
import tempfile

import pytest

from jarvis.jarvis_auto_fix.fix_history import FixHistory
from jarvis.jarvis_auto_fix.refactoring.move_method import (
    MethodAnalyzer,
    MoveMethodRefactorer,
)


class TestMethodAnalyzer:
    """Tests for MethodAnalyzer class."""

    def test_analyze_methods(self):
        """Test detection of class methods."""
        code = """
class MyClass:
    def method1(self):
        pass

    def method2(self):
        self.method1()
"""
        tree = ast.parse(code)
        class_node = tree.body[0]
        analyzer = MethodAnalyzer()
        analyzer.analyze_class(class_node)

        assert "method1" in analyzer.methods
        assert "method2" in analyzer.methods
        assert len(analyzer.methods) == 2

    def test_analyze_method_params(self):
        """Test detection of method parameters."""
        code = """
class MyClass:
    def method_with_params(self, a, b, c=10):
        pass
"""
        tree = ast.parse(code)
        class_node = tree.body[0]
        analyzer = MethodAnalyzer()
        analyzer.analyze_class(class_node)

        method_info = analyzer.methods["method_with_params"]
        assert method_info.params == ["a", "b", "c"]

    def test_analyze_self_references(self):
        """Test detection of self.xxx references."""
        code = """
class MyClass:
    def method(self):
        return self.value + self.other
"""
        tree = ast.parse(code)
        class_node = tree.body[0]
        analyzer = MethodAnalyzer()
        analyzer.analyze_class(class_node)

        method_info = analyzer.methods["method"]
        assert "value" in method_info.self_references
        assert "other" in method_info.self_references

    def test_analyze_method_calls(self):
        """Test detection of self.method() calls."""
        code = """
class MyClass:
    def helper(self):
        return 42

    def main_method(self):
        return self.helper() + 1
"""
        tree = ast.parse(code)
        class_node = tree.body[0]
        analyzer = MethodAnalyzer()
        analyzer.analyze_class(class_node)

        method_info = analyzer.methods["main_method"]
        assert "helper" in method_info.method_calls
        assert "helper" in method_info.dependencies

    def test_detect_abstract_method(self):
        """Test detection of abstract methods."""
        code = """
from abc import abstractmethod

class MyClass:
    @abstractmethod
    def abstract_method(self):
        pass
"""
        tree = ast.parse(code)
        class_node = tree.body[1]
        analyzer = MethodAnalyzer()
        analyzer.analyze_class(class_node)

        method_info = analyzer.methods["abstract_method"]
        assert method_info.is_abstract is True

    def test_detect_static_method(self):
        """Test detection of static methods."""
        code = """
class MyClass:
    @staticmethod
    def static_method():
        pass
"""
        tree = ast.parse(code)
        class_node = tree.body[0]
        analyzer = MethodAnalyzer()
        analyzer.analyze_class(class_node)

        method_info = analyzer.methods["static_method"]
        assert method_info.is_static is True

    def test_detect_classmethod(self):
        """Test detection of class methods."""
        code = """
class MyClass:
    @classmethod
    def class_method(cls):
        pass
"""
        tree = ast.parse(code)
        class_node = tree.body[0]
        analyzer = MethodAnalyzer()
        analyzer.analyze_class(class_node)

        method_info = analyzer.methods["class_method"]
        assert method_info.is_classmethod is True


class TestMoveMethodRefactorer:
    """Tests for MoveMethodRefactorer class."""

    @pytest.fixture
    def temp_history_file(self):
        """Create a temporary history file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("[]")
            temp_path = f.name
        yield temp_path
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.fixture
    def refactorer(self, temp_history_file):
        """Create a MoveMethodRefactorer instance."""
        history = FixHistory(temp_history_file)
        return MoveMethodRefactorer(history)

    def test_move_simple_method(self, refactorer):
        """Test moving a simple method between classes."""
        code = """
class SourceClass:
    def method_to_move(self):
        return 42

class TargetClass:
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            result = refactorer.move_method(
                file_path=temp_path,
                source_class="SourceClass",
                method_name="method_to_move",
                target_class="TargetClass",
            )

            assert result.success is True

            with open(temp_path, "r") as f:
                modified_code = f.read()

            # Verify method is in target class
            assert "def method_to_move(self):" in modified_code
            tree = ast.parse(modified_code)

            # Find TargetClass and verify it has the method
            target_class = None
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == "TargetClass":
                    target_class = node
                    break

            assert target_class is not None
            method_names = [
                n.name for n in target_class.body if isinstance(n, ast.FunctionDef)
            ]
            assert "method_to_move" in method_names

        finally:
            os.unlink(temp_path)

    def test_move_method_source_class_not_found(self, refactorer):
        """Test error when source class is not found."""
        code = """
class TargetClass:
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            result = refactorer.move_method(
                file_path=temp_path,
                source_class="NonExistentClass",
                method_name="method",
                target_class="TargetClass",
            )

            assert result.success is False
            assert "not found" in result.error_message.lower()
        finally:
            os.unlink(temp_path)

    def test_move_method_target_class_not_found(self, refactorer):
        """Test error when target class is not found."""
        code = """
class SourceClass:
    def method(self):
        pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            result = refactorer.move_method(
                file_path=temp_path,
                source_class="SourceClass",
                method_name="method",
                target_class="NonExistentClass",
            )

            assert result.success is False
            assert "not found" in result.error_message.lower()
        finally:
            os.unlink(temp_path)

    def test_move_method_not_found(self, refactorer):
        """Test error when method is not found."""
        code = """
class SourceClass:
    def other_method(self):
        pass

class TargetClass:
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            result = refactorer.move_method(
                file_path=temp_path,
                source_class="SourceClass",
                method_name="non_existent_method",
                target_class="TargetClass",
            )

            assert result.success is False
            assert "not found" in result.error_message.lower()
        finally:
            os.unlink(temp_path)

    def test_cannot_move_abstract_method(self, refactorer):
        """Test that abstract methods cannot be moved."""
        code = """
from abc import abstractmethod

class SourceClass:
    @abstractmethod
    def abstract_method(self):
        pass

class TargetClass:
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            result = refactorer.move_method(
                file_path=temp_path,
                source_class="SourceClass",
                method_name="abstract_method",
                target_class="TargetClass",
            )

            assert result.success is False
            assert "abstract" in result.error_message.lower()
        finally:
            os.unlink(temp_path)

    def test_cannot_move_to_class_with_same_method_name(self, refactorer):
        """Test error when target class already has method with same name."""
        code = """
class SourceClass:
    def method(self):
        return 1

class TargetClass:
    def method(self):
        return 2
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            result = refactorer.move_method(
                file_path=temp_path,
                source_class="SourceClass",
                method_name="method",
                target_class="TargetClass",
            )

            assert result.success is False
            assert "already has" in result.error_message.lower()
        finally:
            os.unlink(temp_path)

    def test_move_method_with_body(self, refactorer):
        """Test moving a method with a complex body."""
        code = """
class SourceClass:
    def complex_method(self, x, y):
        result = x + y
        if result > 10:
            return result * 2
        return result

class TargetClass:
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            result = refactorer.move_method(
                file_path=temp_path,
                source_class="SourceClass",
                method_name="complex_method",
                target_class="TargetClass",
            )

            assert result.success is True

            with open(temp_path, "r") as f:
                modified_code = f.read()

            # Verify the method body is preserved
            assert "result = x + y" in modified_code
            assert "if result > 10:" in modified_code
            assert "return result * 2" in modified_code

        finally:
            os.unlink(temp_path)

    def test_file_not_found(self, refactorer):
        """Test error when file is not found."""
        result = refactorer.move_method(
            file_path="/non/existent/file.py",
            source_class="SourceClass",
            method_name="method",
            target_class="TargetClass",
        )

        assert result.success is False
        assert "not found" in result.error_message.lower()

    def test_analyze_method_dependencies(self, refactorer):
        """Test analyzing method dependencies."""
        code = """
class MyClass:
    def helper(self):
        return self.value

    def main_method(self):
        return self.helper() + self.other_value
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            deps = refactorer.analyze_method_dependencies(
                file_path=temp_path,
                class_name="MyClass",
                method_name="main_method",
            )

            assert "helper" in deps["method_calls"]
            assert "other_value" in deps["self_references"]
        finally:
            os.unlink(temp_path)

    def test_suggest_target_class(self, refactorer):
        """Test suggesting target classes."""
        code = """
class SourceClass:
    def method(self):
        pass

class TargetClass1:
    pass

class TargetClass2:
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            suggestions = refactorer.suggest_target_class(
                file_path=temp_path,
                source_class="SourceClass",
                method_name="method",
            )

            class_names = [s[0] for s in suggestions]
            assert "TargetClass1" in class_names
            assert "TargetClass2" in class_names
            assert "SourceClass" not in class_names
        finally:
            os.unlink(temp_path)

    def test_fix_history_recorded(self, refactorer, temp_history_file):
        """Test that fix is recorded in history."""
        code = """
class SourceClass:
    def method_to_move(self):
        return 42

class TargetClass:
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            result = refactorer.move_method(
                file_path=temp_path,
                source_class="SourceClass",
                method_name="method_to_move",
                target_class="TargetClass",
            )

            assert result.success is True

            # Check history
            fixes = refactorer.history.get_all_fixes()
            assert len(fixes) == 1
            assert fixes[0].issue_type == "move_method"
            assert "method_to_move" in fixes[0].fix_applied
        finally:
            os.unlink(temp_path)

    def test_move_method_with_multiple_methods_in_source(self, refactorer):
        """Test moving a method when source class has multiple methods."""
        code = """
class SourceClass:
    def method1(self):
        return 1

    def method_to_move(self):
        return 42

    def method2(self):
        return 2

class TargetClass:
    def existing_method(self):
        pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            result = refactorer.move_method(
                file_path=temp_path,
                source_class="SourceClass",
                method_name="method_to_move",
                target_class="TargetClass",
            )

            assert result.success is True

            with open(temp_path, "r") as f:
                modified_code = f.read()

            # Verify source class still has other methods
            tree = ast.parse(modified_code)
            source_class = None
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == "SourceClass":
                    source_class = node
                    break

            assert source_class is not None
            method_names = [
                n.name for n in source_class.body if isinstance(n, ast.FunctionDef)
            ]
            assert "method1" in method_names
            assert "method2" in method_names
            assert "method_to_move" not in method_names

        finally:
            os.unlink(temp_path)

    def test_move_method_target_before_source(self, refactorer):
        """Test moving method when target class is defined before source class."""
        code = """
class TargetClass:
    pass

class SourceClass:
    def method_to_move(self):
        return 42
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            result = refactorer.move_method(
                file_path=temp_path,
                source_class="SourceClass",
                method_name="method_to_move",
                target_class="TargetClass",
            )

            assert result.success is True

            with open(temp_path, "r") as f:
                modified_code = f.read()

            # Verify method is in target class
            tree = ast.parse(modified_code)
            target_class = None
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == "TargetClass":
                    target_class = node
                    break

            assert target_class is not None
            method_names = [
                n.name for n in target_class.body if isinstance(n, ast.FunctionDef)
            ]
            assert "method_to_move" in method_names

        finally:
            os.unlink(temp_path)

    def test_analyze_dependencies_class_not_found(self, refactorer):
        """Test analyze_method_dependencies when class is not found."""
        code = """
class OtherClass:
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            deps = refactorer.analyze_method_dependencies(
                file_path=temp_path,
                class_name="NonExistentClass",
                method_name="method",
            )

            assert deps["self_references"] == set()
            assert deps["method_calls"] == set()
            assert deps["dependencies"] == set()
        finally:
            os.unlink(temp_path)

    def test_analyze_dependencies_method_not_found(self, refactorer):
        """Test analyze_method_dependencies when method is not found."""
        code = """
class MyClass:
    def other_method(self):
        pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            deps = refactorer.analyze_method_dependencies(
                file_path=temp_path,
                class_name="MyClass",
                method_name="non_existent_method",
            )

            assert deps["self_references"] == set()
            assert deps["method_calls"] == set()
            assert deps["dependencies"] == set()
        finally:
            os.unlink(temp_path)

    def test_suggest_target_class_file_error(self, refactorer):
        """Test suggest_target_class with invalid file."""
        suggestions = refactorer.suggest_target_class(
            file_path="/non/existent/file.py",
            source_class="SourceClass",
            method_name="method",
        )

        assert suggestions == []

    def test_analyze_dependencies_file_error(self, refactorer):
        """Test analyze_method_dependencies with invalid file."""
        deps = refactorer.analyze_method_dependencies(
            file_path="/non/existent/file.py",
            class_name="MyClass",
            method_name="method",
        )

        assert deps["self_references"] == set()
        assert deps["method_calls"] == set()
        assert deps["dependencies"] == set()
