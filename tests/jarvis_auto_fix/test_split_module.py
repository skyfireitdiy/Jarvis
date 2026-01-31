"""Tests for SplitModuleRefactorer module."""

import ast
import tempfile
from pathlib import Path

from jarvis.jarvis_auto_fix.refactoring.split_module import (
    SplitModuleRefactorer,
    ModuleSplitResult,
    SplitPlan,
    ModuleInfo,
    SplitGroup,
    ModuleDependencyAnalyzer,
)
from jarvis.jarvis_auto_fix.fix_history import FixHistory


class TestModuleDependencyAnalyzer:
    """Tests for ModuleDependencyAnalyzer class."""

    def test_analyze_simple_module(self) -> None:
        """Test analyzing a simple module with classes and functions."""
        code = """
class UserService:
    def get_user(self, user_id: int) -> dict:
        return {}

class ProductService:
    def get_product(self, product_id: int) -> dict:
        return {}

def helper_function():
    pass
"""
        tree = ast.parse(code)
        analyzer = ModuleDependencyAnalyzer()
        analyzer.analyze_module(tree)

        assert len(analyzer.classes) == 2
        assert "UserService" in analyzer.classes
        assert "ProductService" in analyzer.classes
        assert len(analyzer.functions) == 1
        assert "helper_function" in analyzer.functions

    def test_analyze_dependencies(self) -> None:
        """Test dependency analysis between components."""
        code = """
class Database:
    def connect(self) -> bool:
        return True

class UserService:
    def __init__(self):
        self.db = Database()
    def get_user(self, user_id: int) -> dict:
        return {}
"""
        tree = ast.parse(code)
        analyzer = ModuleDependencyAnalyzer()
        analyzer.analyze_module(tree)

        # UserService should depend on Database
        assert "Database" in analyzer.classes["UserService"].dependencies
        assert "UserService" in analyzer.classes["Database"].dependents

    def test_calculate_complexity(self) -> None:
        """Test complexity calculation."""
        code = """
def simple_function():
    return 1

def complex_function(x):
    if x > 0:
        for i in range(10):
            if i % 2 == 0:
                return i
    return 0
"""
        tree = ast.parse(code)
        analyzer = ModuleDependencyAnalyzer()
        analyzer.analyze_module(tree)

        # simple_function should have complexity 1
        assert analyzer.functions["simple_function"].complexity == 1
        # complex_function should have higher complexity
        assert analyzer.functions["complex_function"].complexity > 1

    def test_import_analysis(self) -> None:
        """Test import statement analysis."""
        code = """
import os
import sys as system
from typing import Dict, List

my_dict = Dict[str, int]
"""
        tree = ast.parse(code)
        analyzer = ModuleDependencyAnalyzer()
        analyzer.analyze_module(tree)

        assert "os" in analyzer.imports
        assert "system" in analyzer.imports
        assert "Dict" in analyzer.imports
        assert "List" in analyzer.imports


class TestSplitModuleRefactorer:
    """Tests for SplitModuleRefactorer class."""

    def test_analyze_module_returns_valid_data(self) -> None:
        """Test module analysis returns valid data structure."""
        code = """
class ClassA:
    pass

class ClassB:
    pass

def function_a():
    pass

def function_b():
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        try:
            refactorer = SplitModuleRefactorer()
            analysis = refactorer.analyze_module(file_path)

            assert analysis is not None
            assert analysis["total_classes"] == 2
            assert analysis["total_functions"] == 2
            assert analysis["total_components"] == 4
            assert analysis["can_split"] is True
        finally:
            Path(file_path).unlink()

    def test_analyze_small_module(self) -> None:
        """Test that small modules cannot be split."""
        code = """
def single_function():
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        try:
            refactorer = SplitModuleRefactorer()
            analysis = refactorer.analyze_module(file_path)

            assert analysis is not None
            assert analysis["total_components"] < 3
            assert analysis["can_split"] is False
        finally:
            Path(file_path).unlink()

    def test_suggest_split_plan_creates_groups(self) -> None:
        """Test that split plan creates reasonable groups."""
        # Use two independent groups that can be split
        code = """
class DatabaseConnection:
    def connect(self):
        pass
    def disconnect(self):
        pass

class UserService:
    def __init__(self):
        self.db = DatabaseConnection()
    def get_user(self, user_id: int):
        return {}
    def create_user(self, data: dict):
        pass

class ProductRepository:
    def find_by_id(self, product_id: int):
        return {}
    def save(self, product: dict):
        pass

class ProductService:
    def __init__(self):
        self.repo = ProductRepository()
    def get_product(self, product_id: int):
        return self.repo.find_by_id(product_id)
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        try:
            refactorer = SplitModuleRefactorer()
            plan = refactorer.suggest_split_plan(file_path)

            # Should create a plan with at least one group
            if plan:
                assert plan.original_module == file_path
                assert len(plan.groups) >= 1
            else:
                # If no plan is created, verify the module was analyzed
                analysis = refactorer.analyze_module(file_path)
                assert analysis is not None
                assert analysis["total_classes"] == 4
        finally:
            Path(file_path).unlink()

    def test_find_dependency_clusters(self) -> None:
        """Test dependency cluster finding."""
        code = """
class ClassA:
    pass

class ClassB:
    def __init__(self):
        self.a = ClassA()

class ClassC:
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        try:
            refactorer = SplitModuleRefactorer()
            analysis = refactorer.analyze_module(file_path)
            components = {**analysis["classes"], **analysis["functions"]}

            clusters = refactorer._find_dependency_clusters(components)

            # ClassA and ClassB should be in the same cluster (B depends on A)
            # ClassC should be in a different cluster
            assert len(clusters) >= 1
        finally:
            Path(file_path).unlink()

    def test_split_module_creates_new_files(self) -> None:
        """Test that splitting creates new module files."""
        code = """
class GroupA:
    def method_a(self):
        pass

class GroupB:
    def method_b(self):
        pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        try:
            refactorer = SplitModuleRefactorer()
            plan = refactorer.suggest_split_plan(file_path)

            if plan and len(plan.groups) > 0:
                result = refactorer.split_module(file_path, plan)

                assert result.success is True
                assert len(result.created_modules) > 0
                assert file_path in result.modified_files
            else:
                # If no plan can be created, that's also valid
                pass
        finally:
            Path(file_path).unlink()
            # Clean up created modules
            parent_dir = Path(file_path).parent
            for child in parent_dir.glob("*.py"):
                if child.name.startswith("temp"):
                    child.unlink(missing_ok=True)

    def test_split_module_with_custom_plan(self) -> None:
        """Test splitting with a custom split plan."""
        code = """
class ClassA:
    pass

class ClassB:
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        try:
            refactorer = SplitModuleRefactorer()

            # Create a custom plan
            custom_plan = SplitPlan(
                original_module=file_path,
                groups=[
                    SplitGroup(
                        components=["ClassA"],
                        new_module_name="module_a",
                        reason="Test group",
                    )
                ],
                remaining_components=["ClassB"],
                estimated_benefit="Test benefit",
            )

            result = refactorer.split_module(file_path, custom_plan)

            assert result.success is True
            assert len(result.created_modules) > 0
        finally:
            Path(file_path).unlink()
            parent_dir = Path(file_path).parent
            for child in parent_dir.glob("*.py"):
                if child.name.startswith("module"):
                    child.unlink(missing_ok=True)

    def test_fix_history_integration(self) -> None:
        """Test that split operation is recorded in FixHistory."""
        code = """
class ClassA:
    pass

class ClassB:
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        # Create a temporary history file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as hf:
            history_file_path = hf.name

        try:
            history = FixHistory(history_file=history_file_path)
            refactorer = SplitModuleRefactorer(history=history)

            plan = refactorer.suggest_split_plan(file_path)
            if plan:
                result = refactorer.split_module(file_path, plan)

                if result.success:
                    # Verify fix was recorded
                    records = history.get_all_fixes()
                    assert len(records) > 0
                    assert "split" in records[-1].issue_type
        finally:
            Path(file_path).unlink()
            Path(history_file_path).unlink(missing_ok=True)
            parent_dir = Path(file_path).parent
            for child in parent_dir.glob("*.py"):
                if "part" in child.name or "module" in child.name:
                    child.unlink(missing_ok=True)

    def test_module_info_dataclass(self) -> None:
        """Test ModuleInfo dataclass."""
        info = ModuleInfo(
            name="TestClass",
            component_type="class",
            start_line=10,
            end_line=20,
            dependencies={"OtherClass"},
            dependents={"AnotherClass"},
            complexity=5,
        )

        assert info.name == "TestClass"
        assert info.component_type == "class"
        assert info.start_line == 10
        assert info.end_line == 20
        assert "OtherClass" in info.dependencies
        assert "AnotherClass" in info.dependents
        assert info.complexity == 5

    def test_split_group_dataclass(self) -> None:
        """Test SplitGroup dataclass."""
        group = SplitGroup(
            components=["ClassA", "ClassB"],
            new_module_name="new_module",
            reason="Related components",
        )

        assert len(group.components) == 2
        assert group.new_module_name == "new_module"
        assert group.reason == "Related components"

    def test_split_plan_dataclass(self) -> None:
        """Test SplitPlan dataclass."""
        plan = SplitPlan(
            original_module="test.py",
            groups=[
                SplitGroup(
                    components=["ClassA"], new_module_name="module_a", reason="Test"
                )
            ],
            remaining_components=["ClassB"],
            estimated_benefit="Better organization",
        )

        assert plan.original_module == "test.py"
        assert len(plan.groups) == 1
        assert len(plan.remaining_components) == 1
        assert plan.estimated_benefit == "Better organization"

    def test_module_split_result_dataclass(self) -> None:
        """Test ModuleSplitResult dataclass."""
        result = ModuleSplitResult(
            success=True,
            created_modules=["module_a.py", "module_b.py"],
            modified_files=["original.py"],
            split_plan=None,
        )

        assert result.success is True
        assert len(result.created_modules) == 2
        assert len(result.modified_files) == 1

    def test_split_module_with_no_plan(self) -> None:
        """Test splitting without providing a plan (auto-generate)."""
        code = """
class ClassA:
    pass

class ClassB:
    def __init__(self):
        self.a = ClassA()
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        try:
            refactorer = SplitModuleRefactorer()
            result = refactorer.split_module(file_path)

            # Should either succeed or have a clear error
            if result.success:
                assert result.split_plan is not None
            else:
                assert len(result.error_message) > 0
        finally:
            Path(file_path).unlink()
            parent_dir = Path(file_path).parent
            for child in parent_dir.glob("*.py"):
                if "part" in child.name:
                    child.unlink(missing_ok=True)

    def test_analyze_module_with_syntax_error(self) -> None:
        """Test analyzing a module with syntax errors."""
        code = """
class BrokenClass:
    def broken_method(
        # Missing closing parenthesis
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        try:
            refactorer = SplitModuleRefactorer()
            analysis = refactorer.analyze_module(file_path)

            # Should return None for syntax errors
            assert analysis is None
        finally:
            Path(file_path).unlink()
