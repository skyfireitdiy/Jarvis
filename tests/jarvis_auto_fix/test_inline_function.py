"""Tests for InlineFunctionRefactorer.

This module contains unit tests for the inline function refactoring functionality.
"""

import os
import tempfile

import pytest

from jarvis.jarvis_auto_fix.fix_history import FixHistory
from jarvis.jarvis_auto_fix.refactoring.inline_function import (
    InlineFunctionRefactorer,
    SideEffectChecker,
)


class TestSideEffectChecker:
    """Tests for SideEffectChecker class."""

    def test_simple_function_no_side_effects(self):
        """Test that simple functions are detected as safe."""
        import ast

        code = """
def add(a, b):
    return a + b
"""
        tree = ast.parse(code)
        func_node = tree.body[0]
        checker = SideEffectChecker()
        checker.check_function(func_node, "add")

        assert not checker.has_side_effects
        assert not checker.is_recursive
        assert not checker.has_multiple_returns

    def test_recursive_function(self):
        """Test detection of recursive functions."""
        import ast

        code = """
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)
"""
        tree = ast.parse(code)
        func_node = tree.body[0]
        checker = SideEffectChecker()
        checker.check_function(func_node, "factorial")

        assert checker.is_recursive

    def test_function_with_print(self):
        """Test detection of side-effect functions like print."""
        import ast

        code = """
def greet(name):
    print(f"Hello, {name}")
    return name
"""
        tree = ast.parse(code)
        func_node = tree.body[0]
        checker = SideEffectChecker()
        checker.check_function(func_node, "greet")

        assert checker.has_side_effects
        assert "print" in checker.side_effect_reason

    def test_function_with_global(self):
        """Test detection of global statement."""
        import ast

        code = """
def increment():
    global counter
    counter += 1
    return counter
"""
        tree = ast.parse(code)
        func_node = tree.body[0]
        checker = SideEffectChecker()
        checker.check_function(func_node, "increment")

        assert checker.has_side_effects
        assert "global" in checker.side_effect_reason

    def test_multiple_returns(self):
        """Test detection of multiple return statements."""
        import ast

        code = """
def abs_value(x):
    if x < 0:
        return -x
    return x
"""
        tree = ast.parse(code)
        func_node = tree.body[0]
        checker = SideEffectChecker()
        checker.check_function(func_node, "abs_value")

        assert checker.has_multiple_returns


class TestInlineFunctionRefactorer:
    """Tests for InlineFunctionRefactorer class."""

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
        return InlineFunctionRefactorer(history=history)

    def test_inline_simple_function(self, temp_dir, refactorer):
        """Test inlining a simple function."""
        code = """def add(a, b):
    return a + b

result = add(1, 2)
"""
        file_path = os.path.join(temp_dir, "test_simple.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.inline_function(file_path, "add")

        assert result.success
        assert result.inlined_count == 1

        with open(file_path, "r") as f:
            new_code = f.read()

        assert "1 + 2" in new_code

    def test_inline_function_with_multiple_calls(self, temp_dir, refactorer):
        """Test inlining a function with multiple call sites."""
        code = """def double(x):
    return x * 2

a = double(5)
b = double(10)
c = double(a)
"""
        file_path = os.path.join(temp_dir, "test_multiple.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.inline_function(file_path, "double")

        assert result.success
        assert result.inlined_count == 3

        with open(file_path, "r") as f:
            new_code = f.read()

        assert "5 * 2" in new_code
        assert "10 * 2" in new_code

    def test_cannot_inline_recursive_function(self, temp_dir, refactorer):
        """Test that recursive functions cannot be inlined."""
        code = """def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

result = factorial(5)
"""
        file_path = os.path.join(temp_dir, "test_recursive.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.inline_function(file_path, "factorial")

        assert not result.success
        assert "recursive" in result.error_message

    def test_cannot_inline_function_with_side_effects(self, temp_dir, refactorer):
        """Test that functions with side effects cannot be inlined."""
        code = """def greet(name):
    print(f"Hello, {name}")
    return name

result = greet("World")
"""
        file_path = os.path.join(temp_dir, "test_side_effects.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.inline_function(file_path, "greet")

        assert not result.success
        assert "side-effect" in result.error_message or "print" in result.error_message

    def test_cannot_inline_function_with_default_args(self, temp_dir, refactorer):
        """Test that functions with default arguments cannot be inlined."""
        code = """def greet(name="World"):
    return f"Hello, {name}"

result = greet()
"""
        file_path = os.path.join(temp_dir, "test_default_args.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.inline_function(file_path, "greet")

        assert not result.success
        assert "default" in result.error_message

    def test_cannot_inline_function_with_varargs(self, temp_dir, refactorer):
        """Test that functions with *args cannot be inlined."""
        code = """def sum_all(*args):
    return sum(args)

result = sum_all(1, 2, 3)
"""
        file_path = os.path.join(temp_dir, "test_varargs.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.inline_function(file_path, "sum_all")

        assert not result.success
        assert "args" in result.error_message.lower()

    def test_function_not_found(self, temp_dir, refactorer):
        """Test error when function is not found."""
        code = """def add(a, b):
    return a + b

result = add(1, 2)
"""
        file_path = os.path.join(temp_dir, "test_not_found.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.inline_function(file_path, "subtract")

        assert not result.success
        assert "not found" in result.error_message

    def test_no_call_sites(self, temp_dir, refactorer):
        """Test error when no call sites are found."""
        code = """def add(a, b):
    return a + b

# No calls to add
result = 1 + 2
"""
        file_path = os.path.join(temp_dir, "test_no_calls.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.inline_function(file_path, "add")

        assert not result.success
        assert "No call sites" in result.error_message

    def test_can_inline_check(self, temp_dir, refactorer):
        """Test the can_inline method."""
        code = """def add(a, b):
    return a + b

result = add(1, 2)
"""
        file_path = os.path.join(temp_dir, "test_can_inline.py")
        with open(file_path, "w") as f:
            f.write(code)

        can_inline, reason = refactorer.can_inline(file_path, "add")

        assert can_inline
        assert "safely" in reason.lower()

    def test_inline_with_remove_function(self, temp_dir, refactorer):
        """Test inlining with function removal."""
        code = """def add(a, b):
    return a + b

result = add(1, 2)
"""
        file_path = os.path.join(temp_dir, "test_remove.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.inline_function(file_path, "add", remove_function=True)

        assert result.success

        with open(file_path, "r") as f:
            new_code = f.read()

        assert "def add" not in new_code
        assert "1 + 2" in new_code

    def test_file_not_found(self, temp_dir, refactorer):
        """Test error when file is not found."""
        result = refactorer.inline_function("/nonexistent/file.py", "add")

        assert not result.success
        assert "not found" in result.error_message.lower()

    def test_syntax_error_in_file(self, temp_dir, refactorer):
        """Test error when file has syntax error."""
        code = """def add(a, b)
    return a + b
"""
        file_path = os.path.join(temp_dir, "test_syntax_error.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.inline_function(file_path, "add")

        assert not result.success
        assert "syntax" in result.error_message.lower()

    def test_fix_history_recorded(self, temp_dir, refactorer):
        """Test that fix is recorded in history."""
        code = """def add(a, b):
    return a + b

result = add(1, 2)
"""
        file_path = os.path.join(temp_dir, "test_history.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.inline_function(file_path, "add")

        assert result.success

        # Check that fix was recorded
        fixes = refactorer.history.get_all_fixes()
        assert len(fixes) > 0
        assert fixes[-1].issue_type == "inline_function"

    def test_function_with_yield(self, temp_dir, refactorer):
        """Test that generator functions cannot be inlined."""
        code = """def gen():
    yield 1
    yield 2

result = list(gen())
"""
        file_path = os.path.join(temp_dir, "test_yield.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.inline_function(file_path, "gen")

        assert not result.success
        assert "generator" in result.error_message

    def test_function_with_nonlocal(self, temp_dir, refactorer):
        """Test that functions with nonlocal cannot be inlined."""
        code = """def outer():
    x = 0
    def inner():
        nonlocal x
        x += 1
        return x
    return inner()

result = outer()
"""
        file_path = os.path.join(temp_dir, "test_nonlocal.py")
        with open(file_path, "w") as f:
            f.write(code)

        # inner has nonlocal, but we try to inline outer which calls inner
        result = refactorer.can_inline(file_path, "inner")
        assert not result[0]

    def test_function_modifies_attribute(self, temp_dir, refactorer):
        """Test that functions modifying attributes cannot be inlined."""
        code = """def set_value(obj):
    obj.value = 10
    return obj

class Obj:
    pass

o = Obj()
result = set_value(o)
"""
        file_path = os.path.join(temp_dir, "test_attr.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.inline_function(file_path, "set_value")

        assert not result.success
        assert "attribute" in result.error_message

    def test_function_modifies_subscript(self, temp_dir, refactorer):
        """Test that functions modifying subscripts cannot be inlined."""
        code = """def set_item(lst):
    lst[0] = 10
    return lst

result = set_item([1, 2, 3])
"""
        file_path = os.path.join(temp_dir, "test_subscript.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.inline_function(file_path, "set_item")

        assert not result.success
        assert "subscript" in result.error_message

    def test_inline_expression_only_function(self, temp_dir, refactorer):
        """Test inlining a function that only has a return expression."""
        code = """def square(x):
    return x * x

result = square(5)
"""
        file_path = os.path.join(temp_dir, "test_expr.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.inline_function(file_path, "square")

        assert result.success

        with open(file_path, "r") as f:
            new_code = f.read()

        assert "5 * 5" in new_code

    def test_inline_function_no_return(self, temp_dir, refactorer):
        """Test inlining a function with no return value."""
        code = """def noop():
    pass

result = noop()
"""
        file_path = os.path.join(temp_dir, "test_noop.py")
        with open(file_path, "w") as f:
            f.write(code)

        result = refactorer.inline_function(file_path, "noop")

        assert result.success

        with open(file_path, "r") as f:
            new_code = f.read()

        assert "None" in new_code
