"""Inline Function Refactoring Module

This module provides functionality to inline simple function calls,
replacing them with the function body.
"""

import ast
import builtins
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from jarvis.jarvis_auto_fix.fix_history import FixHistory, FixRecord, generate_fix_id


@dataclass
class InlineResult:
    """Result of a function inline operation.

    Attributes:
        success: Whether the inline was successful
        inlined_count: Number of call sites that were inlined
        error_message: Error message if inline failed
    """

    success: bool
    inlined_count: int = 0
    error_message: str = ""


@dataclass
class FunctionInfo:
    """Information about a function for inlining.

    Attributes:
        name: Function name
        params: List of parameter names
        body_code: The function body code (without def line)
        return_value: The return expression (if single return)
        is_safe: Whether the function is safe to inline
        unsafe_reason: Reason why function is not safe to inline
    """

    name: str
    params: List[str]
    body_code: str
    return_value: Optional[str]
    is_safe: bool
    unsafe_reason: str = ""


class SideEffectChecker(ast.NodeVisitor):
    """AST visitor to check for side effects in a function."""

    def __init__(self) -> None:
        self.has_side_effects = False
        self.side_effect_reason = ""
        self.is_recursive = False
        self.function_name = ""
        self.has_multiple_returns = False
        self.return_count = 0

    def check_function(self, node: ast.FunctionDef, function_name: str) -> None:
        """Check a function for side effects and other issues.

        Args:
            node: The function definition AST node
            function_name: Name of the function being checked
        """
        self.function_name = function_name
        self.visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Check for recursive calls and side-effect functions."""
        # Check for recursive call
        if isinstance(node.func, ast.Name) and node.func.id == self.function_name:
            self.is_recursive = True

        # Check for known side-effect functions
        side_effect_funcs = {"print", "open", "write", "input", "exec", "eval"}
        if isinstance(node.func, ast.Name) and node.func.id in side_effect_funcs:
            self.has_side_effects = True
            self.side_effect_reason = f"calls side-effect function '{node.func.id}'"

        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        """Global statements indicate side effects."""
        self.has_side_effects = True
        self.side_effect_reason = "uses global statement"
        self.generic_visit(node)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        """Nonlocal statements indicate side effects."""
        self.has_side_effects = True
        self.side_effect_reason = "uses nonlocal statement"
        self.generic_visit(node)

    def visit_Yield(self, node: ast.Yield) -> None:
        """Yield indicates a generator, not safe to inline."""
        self.has_side_effects = True
        self.side_effect_reason = "is a generator function"
        self.generic_visit(node)

    def visit_YieldFrom(self, node: ast.YieldFrom) -> None:
        """YieldFrom indicates a generator, not safe to inline."""
        self.has_side_effects = True
        self.side_effect_reason = "is a generator function"
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        """Count return statements."""
        self.return_count += 1
        if self.return_count > 1:
            self.has_multiple_returns = True
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        """Raise statements can have side effects."""
        # We allow raise, but note it
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Check for attribute assignments (side effects)."""
        for target in node.targets:
            if isinstance(target, ast.Attribute):
                self.has_side_effects = True
                self.side_effect_reason = "modifies object attributes"
                break
            if isinstance(target, ast.Subscript):
                self.has_side_effects = True
                self.side_effect_reason = "modifies subscript"
                break
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        """Check for augmented assignments to attributes."""
        if isinstance(node.target, ast.Attribute):
            self.has_side_effects = True
            self.side_effect_reason = "modifies object attributes"
        if isinstance(node.target, ast.Subscript):
            self.has_side_effects = True
            self.side_effect_reason = "modifies subscript"
        self.generic_visit(node)


class CallSiteFinder(ast.NodeVisitor):
    """AST visitor to find all call sites of a function."""

    def __init__(self, function_name: str) -> None:
        self.function_name = function_name
        self.call_sites: List[Tuple[int, int, ast.Call]] = []  # (line, col, node)

    def visit_Call(self, node: ast.Call) -> None:
        """Find calls to the target function."""
        if isinstance(node.func, ast.Name) and node.func.id == self.function_name:
            self.call_sites.append((node.lineno, node.col_offset, node))
        self.generic_visit(node)


class InlineFunctionRefactorer:
    """Refactorer for inlining simple function calls.

    This class provides functionality to inline function calls by replacing
    them with the function body. Only simple functions (no side effects,
    single return, non-recursive) can be safely inlined.

    Attributes:
        history: FixHistory instance for tracking changes

    Example:
        >>> refactorer = InlineFunctionRefactorer()
        >>> result = refactorer.inline_function(
        ...     file_path="example.py",
        ...     function_name="simple_add"
        ... )
        >>> if result.success:
        ...     print(f"Inlined {result.inlined_count} call sites")
    """

    # Built-in names that should not be treated as conflicts
    BUILTINS = set(dir(builtins))

    def __init__(self, history: Optional[FixHistory] = None) -> None:
        """Initialize the InlineFunctionRefactorer.

        Args:
            history: Optional FixHistory instance. If None, creates a new one.
        """
        self.history = history or FixHistory()

    def inline_function(
        self,
        file_path: str,
        function_name: str,
        remove_function: bool = False,
    ) -> InlineResult:
        """Inline all calls to a function.

        Args:
            file_path: Path to the source file.
            function_name: Name of the function to inline.
            remove_function: Whether to remove the function definition after inlining.

        Returns:
            InlineResult containing the result of the operation.
        """
        try:
            # Read the file
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Parse the file
            try:
                tree = ast.parse(content)
            except SyntaxError as e:
                return InlineResult(
                    success=False,
                    error_message=f"Syntax error in file: {e}",
                )

            # Find the function definition
            func_info = self._find_function(tree, function_name, content)
            if func_info is None:
                return InlineResult(
                    success=False,
                    error_message=f"Function '{function_name}' not found",
                )

            # Check if function is safe to inline
            if not func_info.is_safe:
                return InlineResult(
                    success=False,
                    error_message=f"Function cannot be inlined: {func_info.unsafe_reason}",
                )

            # Find all call sites
            finder = CallSiteFinder(function_name)
            finder.visit(tree)

            if not finder.call_sites:
                return InlineResult(
                    success=False,
                    error_message=f"No call sites found for function '{function_name}'",
                )

            # Perform the inlining
            new_content = self._perform_inline(
                content, tree, func_info, finder.call_sites, remove_function
            )

            # Validate the new code
            try:
                ast.parse(new_content)
            except SyntaxError as e:
                return InlineResult(
                    success=False,
                    error_message=f"Generated code has syntax error: {e}",
                )

            # Write the new content
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            # Record the fix
            record = FixRecord(
                record_id=generate_fix_id(),
                file_path=file_path,
                issue_type="inline_function",
                original_content=content,
                fixed_content=new_content,
                timestamp=datetime.now().isoformat(),
                fix_applied=f"Inlined {len(finder.call_sites)} calls to function '{function_name}'",
                rollback_available=True,
            )
            self.history.record_fix(record)

            return InlineResult(
                success=True,
                inlined_count=len(finder.call_sites),
            )

        except FileNotFoundError:
            return InlineResult(
                success=False,
                error_message=f"File not found: {file_path}",
            )
        except Exception as e:
            return InlineResult(
                success=False,
                error_message=f"Unexpected error: {str(e)}",
            )

    def can_inline(self, file_path: str, function_name: str) -> Tuple[bool, str]:
        """Check if a function can be safely inlined.

        Args:
            file_path: Path to the source file.
            function_name: Name of the function to check.

        Returns:
            Tuple of (can_inline, reason).
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)
            func_info = self._find_function(tree, function_name, content)

            if func_info is None:
                return False, f"Function '{function_name}' not found"

            if not func_info.is_safe:
                return False, func_info.unsafe_reason

            return True, "Function can be safely inlined"

        except SyntaxError as e:
            return False, f"Syntax error in file: {e}"
        except FileNotFoundError:
            return False, f"File not found: {file_path}"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def _find_function(
        self, tree: ast.Module, function_name: str, content: str
    ) -> Optional[FunctionInfo]:
        """Find a function definition and extract its information.

        Args:
            tree: The AST of the file.
            function_name: Name of the function to find.
            content: The source code content.

        Returns:
            FunctionInfo if found, None otherwise.
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                return self._analyze_function(node, content)
        return None

    def _analyze_function(self, node: ast.FunctionDef, content: str) -> FunctionInfo:
        """Analyze a function definition for inlining.

        Args:
            node: The function definition AST node.
            content: The source code content.

        Returns:
            FunctionInfo with analysis results.
        """
        # Get parameter names
        params = [arg.arg for arg in node.args.args]

        # Check for default arguments (not supported for simplicity)
        if node.args.defaults or node.args.kw_defaults:
            return FunctionInfo(
                name=node.name,
                params=params,
                body_code="",
                return_value=None,
                is_safe=False,
                unsafe_reason="has default arguments",
            )

        # Check for *args, **kwargs (not supported)
        if node.args.vararg or node.args.kwarg:
            return FunctionInfo(
                name=node.name,
                params=params,
                body_code="",
                return_value=None,
                is_safe=False,
                unsafe_reason="has *args or **kwargs",
            )

        # Check for side effects and recursion
        checker = SideEffectChecker()
        checker.check_function(node, node.name)

        if checker.is_recursive:
            return FunctionInfo(
                name=node.name,
                params=params,
                body_code="",
                return_value=None,
                is_safe=False,
                unsafe_reason="is recursive",
            )

        if checker.has_side_effects:
            return FunctionInfo(
                name=node.name,
                params=params,
                body_code="",
                return_value=None,
                is_safe=False,
                unsafe_reason=checker.side_effect_reason,
            )

        if checker.has_multiple_returns:
            return FunctionInfo(
                name=node.name,
                params=params,
                body_code="",
                return_value=None,
                is_safe=False,
                unsafe_reason="has multiple return statements",
            )

        # Extract the function body and return value
        body_code, return_value = self._extract_body(node, content)

        return FunctionInfo(
            name=node.name,
            params=params,
            body_code=body_code,
            return_value=return_value,
            is_safe=True,
        )

    def _extract_body(
        self, node: ast.FunctionDef, content: str
    ) -> Tuple[str, Optional[str]]:
        """Extract the function body code and return value.

        Args:
            node: The function definition AST node.
            content: The source code content.

        Returns:
            Tuple of (body_code, return_value).
        """
        # Get the body statements
        if not node.body:
            return "", None

        # Find return value
        return_value = None
        body_statements = []

        for stmt in node.body:
            if isinstance(stmt, ast.Return):
                if stmt.value:
                    return_value = ast.unparse(stmt.value)
            elif isinstance(stmt, ast.Pass):
                continue
            else:
                body_statements.append(stmt)

        # Generate body code
        body_code = "\n".join(ast.unparse(stmt) for stmt in body_statements)

        return body_code, return_value

    def _perform_inline(
        self,
        content: str,
        tree: ast.Module,
        func_info: FunctionInfo,
        call_sites: List[Tuple[int, int, ast.Call]],
        remove_function: bool,
    ) -> str:
        """Perform the actual inlining operation.

        Args:
            content: The source code content.
            tree: The AST of the file.
            func_info: Information about the function to inline.
            call_sites: List of call sites to inline.
            remove_function: Whether to remove the function definition.

        Returns:
            The modified source code.
        """
        lines = content.split("\n")

        # Sort call sites by line number in reverse order (to preserve line numbers)
        sorted_sites = sorted(call_sites, key=lambda x: (x[0], x[1]), reverse=True)

        # Process each call site
        for line_no, col_offset, call_node in sorted_sites:
            # Get the arguments
            args = [ast.unparse(arg) for arg in call_node.args]

            # Create parameter to argument mapping
            param_map = dict(zip(func_info.params, args))

            # Generate the inline code
            inline_code = self._generate_inline_code(func_info, param_map)

            # Replace the call in the line
            line_idx = line_no - 1
            line = lines[line_idx]

            # Find the call in the line and replace it
            call_str = ast.unparse(call_node)
            if call_str in line:
                lines[line_idx] = line.replace(call_str, inline_code, 1)

        # Remove the function definition if requested
        if remove_function:
            lines = self._remove_function_def(lines, tree, func_info.name)

        return "\n".join(lines)

    def _generate_inline_code(
        self, func_info: FunctionInfo, param_map: Dict[str, str]
    ) -> str:
        """Generate the inline code for a function call.

        Args:
            func_info: Information about the function.
            param_map: Mapping from parameter names to argument values.

        Returns:
            The inline code string.
        """
        if func_info.return_value:
            # Replace parameters in return value
            result = func_info.return_value
            for param, arg in param_map.items():
                # Use word boundary replacement to avoid partial matches
                result = self._replace_identifier(result, param, arg)
            return result
        else:
            # No return value, just return the body with parameters replaced
            result = func_info.body_code
            for param, arg in param_map.items():
                result = self._replace_identifier(result, param, arg)
            return result if result else "None"

    def _replace_identifier(self, code: str, old_name: str, new_name: str) -> str:
        """Replace an identifier in code, respecting word boundaries.

        Args:
            code: The code to modify.
            old_name: The identifier to replace.
            new_name: The replacement value.

        Returns:
            The modified code.
        """
        # Parse and transform the AST to replace identifiers
        try:
            tree = ast.parse(code, mode="eval")
            transformer = IdentifierReplacer(old_name, new_name)
            new_tree = transformer.visit(tree)
            return ast.unparse(new_tree)
        except SyntaxError:
            # Fallback to simple string replacement for non-expression code
            pattern = r"\b" + re.escape(old_name) + r"\b"
            return re.sub(pattern, new_name, code)

    def _remove_function_def(
        self, lines: List[str], tree: ast.Module, function_name: str
    ) -> List[str]:
        """Remove a function definition from the source.

        Args:
            lines: The source lines.
            tree: The AST of the file.
            function_name: Name of the function to remove.

        Returns:
            The modified source lines.
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                start_line = node.lineno - 1
                end_line = node.end_lineno if node.end_lineno else start_line + 1

                # Remove the function lines
                del lines[start_line:end_line]

                # Remove any trailing blank lines
                while start_line < len(lines) and not lines[start_line].strip():
                    del lines[start_line]

                break

        return lines


class IdentifierReplacer(ast.NodeTransformer):
    """AST transformer to replace identifiers."""

    def __init__(self, old_name: str, new_name: str) -> None:
        self.old_name = old_name
        self.new_name = new_name

    def visit_Name(self, node: ast.Name) -> ast.AST:
        """Replace Name nodes with matching identifier."""
        if node.id == self.old_name:
            # Parse the new name as an expression
            try:
                new_node = ast.parse(self.new_name, mode="eval").body
                return ast.copy_location(new_node, node)
            except SyntaxError:
                node.id = self.new_name
                return node
        return node
