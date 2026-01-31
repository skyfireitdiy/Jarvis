"""Tests for Dependency Injection Refactoring.

This module contains unit tests for the dependency injection refactoring functionality.
"""

import os
import tempfile

import pytest

from jarvis.jarvis_auto_fix.fix_history import FixHistory
from jarvis.jarvis_auto_fix.refactoring.dependency_injection import (
    DependencyInjectionAnalyzer,
    DependencyInjectionRefactorer,
    DependencyInfo,
    InjectionResult,
)


class TestDependencyInjectionAnalyzer:
    """Tests for DependencyInjectionAnalyzer class."""

    def test_detect_simple_dependency(self):
        """Test detection of simple hardcoded dependency."""
        code = """
class UserService:
    def __init__(self):
        self.db = Database()
"""
        analyzer = DependencyInjectionAnalyzer()
        deps = analyzer.analyze_file(code)

        assert "UserService" in deps
        assert len(deps["UserService"]) == 1
        assert deps["UserService"][0].attribute_name == "db"
        assert deps["UserService"][0].dependency_type == "Database"

    def test_detect_dependency_with_parameters(self):
        """Test detection of dependency with parameters."""
        code = """
class UserService:
    def __init__(self):
        self.logger = Logger("service")
"""
        analyzer = DependencyInjectionAnalyzer()
        deps = analyzer.analyze_file(code)

        assert "UserService" in deps
        assert len(deps["UserService"]) == 1
        assert deps["UserService"][0].has_parameters is True
        assert deps["UserService"][0].parameters == ['"service"']

    def test_detect_multiple_dependencies(self):
        """Test detection of multiple dependencies."""
        code = """
class UserService:
    def __init__(self):
        self.db = Database()
        self.logger = Logger()
        self.cache = Cache()
"""
        analyzer = DependencyInjectionAnalyzer()
        deps = analyzer.analyze_file(code)

        assert "UserService" in deps
        assert len(deps["UserService"]) == 3
        attr_names = [d.attribute_name for d in deps["UserService"]]
        assert "db" in attr_names
        assert "logger" in attr_names
        assert "cache" in attr_names

    def test_no_dependencies(self):
        """Test class with no hardcoded dependencies."""
        code = """
class UserService:
    def __init__(self, name):
        self.name = name
"""
        analyzer = DependencyInjectionAnalyzer()
        deps = analyzer.analyze_file(code)

        assert "UserService" not in deps or len(deps["UserService"]) == 0

    def test_multiple_classes(self):
        """Test analysis of multiple classes in same file."""
        code = """
class UserService:
    def __init__(self):
        self.db = Database()

class OrderService:
    def __init__(self):
        self.payment = PaymentProcessor()
"""
        analyzer = DependencyInjectionAnalyzer()
        deps = analyzer.analyze_file(code)

        assert "UserService" in deps
        assert "OrderService" in deps
        assert len(deps["UserService"]) == 1
        assert len(deps["OrderService"]) == 1

    def test_ignore_non_init_assignments(self):
        """Test that non-__init__ assignments are ignored."""
        code = """
class UserService:
    def __init__(self):
        self.name = "service"
    
    def setup(self):
        self.db = Database()
"""
        analyzer = DependencyInjectionAnalyzer()
        deps = analyzer.analyze_file(code)

        assert "UserService" not in deps or len(deps["UserService"]) == 0

    def test_ignore_non_self_assignments(self):
        """Test that non-self assignments are ignored."""
        code = """
class UserService:
    def __init__(self):
        db = Database()  # Not self.db
        self.name = "service"
"""
        analyzer = DependencyInjectionAnalyzer()
        deps = analyzer.analyze_file(code)

        assert "UserService" not in deps or len(deps["UserService"]) == 0


class TestDependencyInjectionRefactorer:
    """Tests for DependencyInjectionRefactorer class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_simple_refactoring(self, temp_dir):
        """Test simple dependency injection refactoring."""
        code = """
class UserService:
    def __init__(self):
        self.db = Database()
"""
        file_path = os.path.join(temp_dir, "test.py")
        with open(file_path, "w") as f:
            f.write(code)

        refactorer = DependencyInjectionRefactorer()
        result = refactorer.refactor_to_constructor_injection(file_path, "UserService")

        assert result.success is True
        assert "db: Database | None" in result.modified_code
        assert "container_code" in result.__dict__

    def test_refactoring_with_keep_defaults(self, temp_dir):
        """Test refactoring with keep_defaults=True."""
        code = """
class UserService:
    def __init__(self):
        self.db = Database()
"""
        file_path = os.path.join(temp_dir, "test.py")
        with open(file_path, "w") as f:
            f.write(code)

        refactorer = DependencyInjectionRefactorer()
        result = refactorer.refactor_to_constructor_injection(
            file_path, "UserService", keep_defaults=True
        )

        assert result.success is True
        # Accept both formats: with or without spaces around =
        assert (
            "db: Database | None = None" in result.modified_code
            or "db: Database | None=None" in result.modified_code
        )

    def test_refactoring_without_keep_defaults(self, temp_dir):
        """Test refactoring with keep_defaults=False."""
        code = """
class UserService:
    def __init__(self):
        self.db = Database()
"""
        file_path = os.path.join(temp_dir, "test.py")
        with open(file_path, "w") as f:
            f.write(code)

        refactorer = DependencyInjectionRefactorer()
        result = refactorer.refactor_to_constructor_injection(
            file_path, "UserService", keep_defaults=False
        )

        assert result.success is True
        # Should have parameter without default
        assert "self, db: Database" in result.modified_code

    def test_container_generation(self, temp_dir):
        """Test dependency container code generation."""
        code = """
class UserService:
    def __init__(self):
        self.db = Database()
        self.logger = Logger()
"""
        file_path = os.path.join(temp_dir, "test.py")
        with open(file_path, "w") as f:
            f.write(code)

        refactorer = DependencyInjectionRefactorer()
        result = refactorer.refactor_to_constructor_injection(file_path, "UserService")

        assert result.success is True
        assert "UserServiceDIContainer" in result.container_code
        assert "@property" in result.container_code
        assert "def create_userservice" in result.container_code

    def test_class_not_found(self, temp_dir):
        """Test error handling when class is not found."""
        code = """
class UserService:
    def __init__(self):
        self.db = Database()
"""
        file_path = os.path.join(temp_dir, "test.py")
        with open(file_path, "w") as f:
            f.write(code)

        refactorer = DependencyInjectionRefactorer()
        result = refactorer.refactor_to_constructor_injection(
            file_path, "NonExistentClass"
        )

        assert result.success is False
        assert "not found" in result.error_message.lower()

    def test_no_init_method(self, temp_dir):
        """Test error handling when class has no __init__ method."""
        code = """
class UserService:
    def process(self):
        pass
"""
        file_path = os.path.join(temp_dir, "test.py")
        with open(file_path, "w") as f:
            f.write(code)

        refactorer = DependencyInjectionRefactorer()
        result = refactorer.refactor_to_constructor_injection(file_path, "UserService")

        assert result.success is False
        assert "no __init__" in result.error_message.lower()

    def test_file_not_found(self):
        """Test error handling when file doesn't exist."""
        refactorer = DependencyInjectionRefactorer()
        result = refactorer.refactor_to_constructor_injection(
            "/nonexistent/file.py", "UserService"
        )

        assert result.success is False
        assert "not found" in result.error_message.lower()

    def test_syntax_error_in_file(self, temp_dir):
        """Test error handling when file has syntax error."""
        code = """
class UserService:
    def __init__(self):
        self.db = Database(
"""
        file_path = os.path.join(temp_dir, "test.py")
        with open(file_path, "w") as f:
            f.write(code)

        refactorer = DependencyInjectionRefactorer()
        result = refactorer.refactor_to_constructor_injection(file_path, "UserService")

        assert result.success is False
        assert "syntax error" in result.error_message.lower()

    def test_filter_specific_dependencies(self, temp_dir):
        """Test filtering specific dependencies by name."""
        code = """
class UserService:
    def __init__(self):
        self.db = Database()
        self.logger = Logger()
"""
        file_path = os.path.join(temp_dir, "test.py")
        with open(file_path, "w") as f:
            f.write(code)

        refactorer = DependencyInjectionRefactorer()
        result = refactorer.refactor_to_constructor_injection(
            file_path, "UserService", dependency_names=["db"]
        )

        assert result.success is True
        assert len(result.dependencies_injected) == 1
        assert result.dependencies_injected[0].attribute_name == "db"

    def test_with_fix_history(self, temp_dir):
        """Test integration with FixHistory."""
        code = """
class UserService:
    def __init__(self):
        self.db = Database()
"""
        file_path = os.path.join(temp_dir, "test.py")
        with open(file_path, "w") as f:
            f.write(code)

        # Use a temporary history file to avoid conflicts with other tests
        history_file = os.path.join(temp_dir, "test_history.json")
        history = FixHistory(history_file=history_file)
        refactorer = DependencyInjectionRefactorer(history=history)
        result = refactorer.refactor_to_constructor_injection(file_path, "UserService")

        assert result.success is True
        fixes = history.get_all_fixes()
        assert len(fixes) == 1
        assert fixes[0].issue_type == "dependency_injection"
        assert fixes[0].rollback_available is True

    def test_dependency_info_dataclass(self):
        """Test DependencyInfo dataclass fields."""
        dep_info = DependencyInfo(
            class_name="TestService",
            dependency_type="Database",
            attribute_name="db",
            instantiation_line=10,
            instantiation_code="Database()",
            has_parameters=False,
            parameters=[],
            is_optional=False,
        )

        assert dep_info.class_name == "TestService"
        assert dep_info.dependency_type == "Database"
        assert dep_info.attribute_name == "db"
        assert dep_info.has_parameters is False
        assert dep_info.is_optional is False

    def test_injection_result_dataclass(self):
        """Test InjectionResult dataclass fields."""
        result = InjectionResult(
            success=True,
            modified_code="class UserService: pass",
            container_code="class Container: pass",
            dependencies_injected=[],
        )

        assert result.success is True
        assert result.modified_code is not None
        assert result.container_code is not None
        assert result.error_message is None

    def test_failed_injection_result(self):
        """Test InjectionResult for failed refactoring."""
        result = InjectionResult(
            success=False,
            error_message="Class not found",
        )

        assert result.success is False
        assert result.error_message == "Class not found"
        assert result.modified_code is None
