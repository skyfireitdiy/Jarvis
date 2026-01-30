"""Extract Function Refactoring Module

This module provides functionality to extract code blocks into separate functions.
"""

import ast
import builtins
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Set, Tuple

from jarvis.jarvis_auto_fix.fix_history import FixHistory, FixRecord, generate_fix_id


@dataclass
class VariableInfo:
    """Information about variables in a code block.

    Attributes:
        inputs: Variables that are read but not defined in the block
        outputs: Variables that are defined and used after the block
        locals: Variables that are defined and only used within the block
    """

    inputs: Set[str]
    outputs: Set[str]
    locals: Set[str]


@dataclass
class ExtractionResult:
    """Result of a function extraction operation.

    Attributes:
        success: Whether the extraction was successful
        new_function: The generated function code
        call_statement: The function call to replace the original code
        error_message: Error message if extraction failed
    """

    success: bool
    new_function: str = ""
    call_statement: str = ""
    error_message: str = ""


class VariableAnalyzer(ast.NodeVisitor):
    """AST visitor to analyze variable usage in a code block."""

    def __init__(self) -> None:
        self.defined: Set[str] = set()
        self.used: Set[str] = set()
        self.assigned: Set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        """Visit a Name node to track variable usage."""
        if isinstance(node.ctx, ast.Store):
            self.defined.add(node.id)
            self.assigned.add(node.id)
        elif isinstance(node.ctx, ast.Load):
            self.used.add(node.id)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definition - don't recurse into nested functions."""
        self.defined.add(node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definition - don't recurse into nested functions."""
        self.defined.add(node.name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition - don't recurse into nested classes."""
        self.defined.add(node.name)

    def visit_For(self, node: ast.For) -> None:
        """Visit for loop to track loop variable."""
        if isinstance(node.target, ast.Name):
            self.defined.add(node.target.id)
        elif isinstance(node.target, ast.Tuple):
            for elt in node.target.elts:
                if isinstance(elt, ast.Name):
                    self.defined.add(elt.id)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        """Visit comprehension to track iteration variable."""
        if isinstance(node.target, ast.Name):
            self.defined.add(node.target.id)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """Visit except handler to track exception variable."""
        if node.name:
            self.defined.add(node.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """Visit import statement."""
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name.split(".")[0]
            self.defined.add(name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Visit from import statement."""
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.defined.add(name)


class ExtractFunctionRefactorer:
    """Refactorer for extracting code blocks into separate functions.

    This class provides functionality to extract a range of lines from a file
    into a new function, automatically detecting variable dependencies and
    generating appropriate function signatures.

    Attributes:
        history: FixHistory instance for tracking changes

    Example:
        >>> refactorer = ExtractFunctionRefactorer()
        >>> result = refactorer.extract_function(
        ...     file_path="example.py",
        ...     start_line=10,
        ...     end_line=20,
        ...     function_name="extracted_function"
        ... )
        >>> if result.success:
        ...     print(result.new_function)
    """

    # Built-in names that should not be treated as external variables
    BUILTINS = set(dir(builtins))

    def __init__(self, history: Optional[FixHistory] = None) -> None:
        """Initialize the ExtractFunctionRefactorer.

        Args:
            history: Optional FixHistory instance. If None, creates a new one.
        """
        self.history = history or FixHistory()

    def extract_function(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
        function_name: str,
        add_return: bool = True,
    ) -> ExtractionResult:
        """Extract a code block into a new function.

        Args:
            file_path: Path to the source file.
            start_line: Starting line number (1-indexed, inclusive).
            end_line: Ending line number (1-indexed, inclusive).
            function_name: Name for the new function.
            add_return: Whether to add return statement for output variables.

        Returns:
            ExtractionResult containing the new function and call statement.
        """
        try:
            # Read the file
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                content = "".join(lines)

            # Validate line numbers
            if start_line < 1 or end_line > len(lines) or start_line > end_line:
                return ExtractionResult(
                    success=False,
                    error_message=f"Invalid line range: {start_line}-{end_line} (file has {len(lines)} lines)",
                )

            # Validate function name
            if not self._is_valid_identifier(function_name):
                return ExtractionResult(
                    success=False,
                    error_message=f"Invalid function name: {function_name}",
                )

            # Parse the entire file to validate syntax
            try:
                ast.parse(content)
            except SyntaxError as e:
                return ExtractionResult(
                    success=False,
                    error_message=f"Syntax error in file: {e}",
                )

            # Extract the code block
            block_lines = lines[start_line - 1 : end_line]
            block_code = "".join(block_lines)

            # Analyze variables
            var_info = self._analyze_variables(
                block_code, content, start_line, end_line
            )

            # Detect indentation
            base_indent = self._detect_indentation(block_lines)

            # Generate the new function
            new_function = self._generate_function(
                function_name, block_code, var_info, base_indent, add_return
            )

            # Generate the call statement
            call_statement = self._generate_call(
                function_name, var_info, base_indent, add_return
            )

            # Apply the refactoring
            new_content = self._apply_refactoring(
                lines, start_line, end_line, new_function, call_statement
            )

            # Validate the new code
            try:
                ast.parse(new_content)
            except SyntaxError as e:
                return ExtractionResult(
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
                issue_type="extract_function",
                original_content=content,
                fixed_content=new_content,
                timestamp=datetime.now().isoformat(),
                fix_applied=f"Extracted lines {start_line}-{end_line} into function '{function_name}'",
                rollback_available=True,
            )
            self.history.record_fix(record)

            return ExtractionResult(
                success=True,
                new_function=new_function,
                call_statement=call_statement,
            )

        except FileNotFoundError:
            return ExtractionResult(
                success=False,
                error_message=f"File not found: {file_path}",
            )
        except Exception as e:
            return ExtractionResult(
                success=False,
                error_message=f"Unexpected error: {str(e)}",
            )

    def _is_valid_identifier(self, name: str) -> bool:
        """Check if a name is a valid Python identifier.

        Args:
            name: The name to check.

        Returns:
            True if valid, False otherwise.
        """
        if not name:
            return False
        return name.isidentifier() and not name.startswith("_")

    def _analyze_variables(
        self, block_code: str, full_code: str, start_line: int, end_line: int
    ) -> VariableInfo:
        """Analyze variable usage in a code block.

        Args:
            block_code: The code block to analyze.
            full_code: The full file content for context.
            start_line: Starting line number.
            end_line: Ending line number.

        Returns:
            VariableInfo with input, output, and local variables.
        """
        # Dedent the block code for parsing
        dedented_code = self._dedent_code(block_code)

        # Analyze the block
        block_analyzer = VariableAnalyzer()
        try:
            block_tree = ast.parse(dedented_code)
            block_analyzer.visit(block_tree)
        except SyntaxError:
            # If block can't be parsed alone, return empty sets
            return VariableInfo(inputs=set(), outputs=set(), locals=set())

        # Variables used but not defined in block are inputs
        inputs = block_analyzer.used - block_analyzer.defined - self.BUILTINS

        # Analyze the code after the block to find outputs
        lines = full_code.split("\n")
        after_code = "\n".join(lines[end_line:])
        # Dedent after_code for parsing
        after_code_dedented = self._dedent_code(after_code)

        after_analyzer = VariableAnalyzer()
        try:
            after_tree = ast.parse(after_code_dedented)
            after_analyzer.visit(after_tree)
        except SyntaxError:
            after_analyzer.used = set()

        # Variables defined in block and used after are outputs
        outputs = block_analyzer.assigned & after_analyzer.used

        # Variables defined and only used within block are locals
        locals_vars = block_analyzer.defined - outputs

        return VariableInfo(inputs=inputs, outputs=outputs, locals=locals_vars)

    def _dedent_code(self, code: str) -> str:
        """Remove common leading whitespace from code.

        Args:
            code: The code to dedent.

        Returns:
            Dedented code.
        """
        lines = code.split("\n")
        if not lines:
            return code

        # Find minimum indentation (ignoring empty lines)
        min_indent = float("inf")
        for line in lines:
            if line.strip():
                indent = len(line) - len(line.lstrip())
                min_indent = min(min_indent, indent)

        if min_indent == float("inf"):
            return code

        # Remove the common indentation
        dedented_lines = []
        for line in lines:
            if line.strip():
                dedented_lines.append(line[int(min_indent) :])
            else:
                dedented_lines.append(line)

        return "\n".join(dedented_lines)

    def _detect_indentation(self, lines: List[str]) -> str:
        """Detect the base indentation of code lines.

        Args:
            lines: List of code lines.

        Returns:
            The base indentation string.
        """
        for line in lines:
            if line.strip():
                return line[: len(line) - len(line.lstrip())]
        return ""

    def _generate_function(
        self,
        name: str,
        block_code: str,
        var_info: VariableInfo,
        base_indent: str,
        add_return: bool,
    ) -> str:
        """Generate the new function code.

        Args:
            name: Function name.
            block_code: The code block to extract.
            var_info: Variable information.
            base_indent: Base indentation.
            add_return: Whether to add return statement.

        Returns:
            The generated function code.
        """
        # Sort parameters for consistent output
        params = sorted(var_info.inputs)
        param_str = ", ".join(params)

        # Dedent the block code
        dedented = self._dedent_code(block_code)

        # Add function indentation
        body_lines = []
        for line in dedented.split("\n"):
            if line.strip():
                body_lines.append("    " + line)
            else:
                body_lines.append(line)

        body = "\n".join(body_lines)

        # Add return statement if needed
        if add_return and var_info.outputs:
            outputs = sorted(var_info.outputs)
            if len(outputs) == 1:
                return_stmt = f"    return {outputs[0]}"
            else:
                return_stmt = f"    return {', '.join(outputs)}"
            body = body.rstrip() + "\n" + return_stmt

        # Generate function definition
        func_def = f"def {name}({param_str}):\n{body}\n"

        return func_def

    def _generate_call(
        self,
        name: str,
        var_info: VariableInfo,
        base_indent: str,
        add_return: bool,
    ) -> str:
        """Generate the function call statement.

        Args:
            name: Function name.
            var_info: Variable information.
            base_indent: Base indentation.
            add_return: Whether to capture return value.

        Returns:
            The function call statement.
        """
        params = sorted(var_info.inputs)
        param_str = ", ".join(params)

        call = f"{name}({param_str})"

        if add_return and var_info.outputs:
            outputs = sorted(var_info.outputs)
            if len(outputs) == 1:
                call = f"{outputs[0]} = {call}"
            else:
                call = f"{', '.join(outputs)} = {call}"

        return base_indent + call + "\n"

    def _apply_refactoring(
        self,
        lines: List[str],
        start_line: int,
        end_line: int,
        new_function: str,
        call_statement: str,
    ) -> str:
        """Apply the refactoring to the file content.

        Args:
            lines: Original file lines.
            start_line: Starting line number.
            end_line: Ending line number.
            new_function: The new function code.
            call_statement: The function call statement.

        Returns:
            The refactored file content.
        """
        # Find the best place to insert the function
        insert_pos = self._find_insertion_point(lines, start_line)

        # Build the new content
        result_lines = []

        # Add lines before insertion point
        result_lines.extend(lines[:insert_pos])

        # Add the new function with a blank line before and after
        if insert_pos > 0 and result_lines and result_lines[-1].strip():
            result_lines.append("\n")
        result_lines.append(new_function)
        result_lines.append("\n")

        # Add lines between insertion point and the extracted block
        if insert_pos < start_line - 1:
            result_lines.extend(lines[insert_pos : start_line - 1])

        # Add the call statement instead of the original block
        result_lines.append(call_statement)

        # Add remaining lines after the extracted block
        result_lines.extend(lines[end_line:])

        return "".join(result_lines)

    def _find_insertion_point(self, lines: List[str], before_line: int) -> int:
        """Find the best line to insert the new function.

        Args:
            lines: File lines.
            before_line: The line before which the function should be accessible.

        Returns:
            Line index for insertion (0-indexed).
        """
        content = "".join(lines)
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return 0

        # Find the enclosing function or class that contains the target line
        enclosing_node = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if hasattr(node, "lineno") and node.lineno < before_line:
                    if (
                        hasattr(node, "end_lineno")
                        and node.end_lineno is not None
                        and node.end_lineno >= before_line
                    ):
                        # The block is inside this function/class
                        # We want to insert BEFORE this function/class
                        if (
                            enclosing_node is None
                            or node.lineno > enclosing_node.lineno
                        ):
                            enclosing_node = node

        if enclosing_node is not None:
            # Insert before the enclosing function/class (0-indexed)
            return enclosing_node.lineno - 1

        # If not inside any function/class, find the first function/class
        # and insert before it
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                return node.lineno - 1

        # Default: insert at the beginning (after imports)
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith(
                ("import ", "from ", "#", '"""', "'''")
            ):
                return i

        return 0

    def analyze_extraction_candidates(
        self, file_path: str, min_lines: int = 5
    ) -> List[Tuple[int, int, str]]:
        """Analyze a file for potential extraction candidates.

        Args:
            file_path: Path to the file to analyze.
            min_lines: Minimum number of lines for a candidate.

        Returns:
            List of (start_line, end_line, reason) tuples.
        """
        candidates: List[Tuple[int, int, str]] = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Check for long functions
                    if (
                        hasattr(node, "end_lineno")
                        and hasattr(node, "lineno")
                        and node.end_lineno is not None
                    ):
                        func_length = node.end_lineno - node.lineno
                        if func_length > 50:
                            candidates.append(
                                (
                                    node.lineno,
                                    node.end_lineno,
                                    f"Long function '{node.name}' ({func_length} lines)",
                                )
                            )

        except (FileNotFoundError, SyntaxError):
            pass

        return candidates
