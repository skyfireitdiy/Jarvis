"""Move Method Refactoring Module

This module provides functionality to move methods from one class to another.
"""

import ast
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from jarvis.jarvis_auto_fix.fix_history import FixHistory, FixRecord, generate_fix_id


@dataclass
class MoveResult:
    """Result of a method move operation.

    Attributes:
        success: Whether the move was successful
        moved_method_code: The code of the moved method in the target class
        error_message: Error message if move failed
    """

    success: bool
    moved_method_code: str = ""
    error_message: str = ""


@dataclass
class MethodInfo:
    """Information about a method for moving.

    Attributes:
        name: Method name
        params: List of parameter names (excluding self)
        start_line: Start line number
        end_line: End line number
        is_abstract: Whether the method is abstract
        is_static: Whether the method is static
        is_classmethod: Whether the method is a classmethod
        self_references: Set of self.xxx references used
        method_calls: Set of self.method() calls
        dependencies: Set of other methods this method depends on
    """

    name: str
    params: List[str]
    start_line: int
    end_line: int
    is_abstract: bool = False
    is_static: bool = False
    is_classmethod: bool = False
    self_references: Set[str] = field(default_factory=set)
    method_calls: Set[str] = field(default_factory=set)
    dependencies: Set[str] = field(default_factory=set)


class MethodAnalyzer(ast.NodeVisitor):
    """AST visitor to analyze method dependencies and self references."""

    def __init__(self) -> None:
        self.methods: Dict[str, MethodInfo] = {}
        self._current_method: Optional[str] = None
        self._self_param: str = "self"

    def analyze_class(self, class_node: ast.ClassDef) -> None:
        """Analyze a class definition to extract method information."""
        for node in class_node.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._analyze_method(node)

    def _analyze_method(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Analyze a method definition."""
        method_name = node.name

        # Get parameters (excluding self/cls)
        params = []
        self_param = "self"
        if node.args.args:
            first_arg = node.args.args[0].arg
            if first_arg in ("self", "cls"):
                self_param = first_arg
                params = [arg.arg for arg in node.args.args[1:]]
            else:
                params = [arg.arg for arg in node.args.args]

        # Check decorators
        is_abstract = False
        is_static = False
        is_classmethod = False
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name):
                if decorator.id == "abstractmethod":
                    is_abstract = True
                elif decorator.id == "staticmethod":
                    is_static = True
                elif decorator.id == "classmethod":
                    is_classmethod = True
            elif isinstance(decorator, ast.Attribute):
                if decorator.attr == "abstractmethod":
                    is_abstract = True

        self.methods[method_name] = MethodInfo(
            name=method_name,
            params=params,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            is_abstract=is_abstract,
            is_static=is_static,
            is_classmethod=is_classmethod,
        )

        # Analyze self references and method calls
        self._current_method = method_name
        self._self_param = self_param
        self.visit(node)
        self._current_method = None

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Track self.xxx attribute access."""
        if self._current_method and isinstance(node.value, ast.Name):
            if node.value.id == self._self_param:
                self.methods[self._current_method].self_references.add(node.attr)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Track self.method() calls."""
        if self._current_method:
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name):
                    if node.func.value.id == self._self_param:
                        method_name = node.func.attr
                        self.methods[self._current_method].method_calls.add(method_name)
                        self.methods[self._current_method].dependencies.add(method_name)
        self.generic_visit(node)


class CallSiteUpdater(ast.NodeTransformer):
    """AST transformer to update call sites after method move."""

    def __init__(
        self,
        source_class: str,
        method_name: str,
        target_instance: str,
    ) -> None:
        self.source_class = source_class
        self.method_name = method_name
        self.target_instance = target_instance
        self.updated_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        """Update method calls to use the new target instance."""
        # Handle self.method() -> self.target_instance.method()
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == self.method_name:
                if isinstance(node.func.value, ast.Name):
                    if node.func.value.id == "self":
                        # Transform self.method() to self.target_instance.method()
                        new_value = ast.Attribute(
                            value=ast.Name(id="self", ctx=ast.Load()),
                            attr=self.target_instance,
                            ctx=ast.Load(),
                        )
                        node.func.value = new_value
                        self.updated_count += 1
        return self.generic_visit(node)


class MoveMethodRefactorer:
    """Refactorer for moving methods between classes.

    This class provides functionality to move a method from one class to another,
    handling self reference transformations and call site updates.

    Attributes:
        history: FixHistory instance for recording changes

    Example:
        >>> refactorer = MoveMethodRefactorer()
        >>> result = refactorer.move_method(
        ...     file_path="example.py",
        ...     source_class="SourceClass",
        ...     method_name="some_method",
        ...     target_class="TargetClass",
        ... )
        >>> if result.success:
        ...     print("Method moved successfully")
    """

    def __init__(self, history: Optional[FixHistory] = None) -> None:
        """Initialize the MoveMethodRefactorer.

        Args:
            history: Optional FixHistory instance. If None, creates a new one.
        """
        self.history = history or FixHistory()

    def move_method(
        self,
        file_path: str,
        source_class: str,
        method_name: str,
        target_class: str,
        target_instance_name: Optional[str] = None,
        update_call_sites: bool = True,
    ) -> MoveResult:
        """Move a method from source class to target class.

        Args:
            file_path: Path to the Python file
            source_class: Name of the class to move the method from
            method_name: Name of the method to move
            target_class: Name of the class to move the method to
            target_instance_name: Name of the instance variable in source class
                                 that references target class (for call site updates)
            update_call_sites: Whether to update call sites in source class

        Returns:
            MoveResult with success status and details
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            lines = content.splitlines(keepends=True)
            tree = ast.parse(content)

            # Find source and target classes
            source_node = self._find_class(tree, source_class)
            target_node = self._find_class(tree, target_class)

            if source_node is None:
                return MoveResult(
                    success=False,
                    error_message=f"Source class '{source_class}' not found",
                )

            if target_node is None:
                return MoveResult(
                    success=False,
                    error_message=f"Target class '{target_class}' not found",
                )

            # Analyze source class
            analyzer = MethodAnalyzer()
            analyzer.analyze_class(source_node)

            if method_name not in analyzer.methods:
                return MoveResult(
                    success=False,
                    error_message=f"Method '{method_name}' not found in '{source_class}'",
                )

            method_info = analyzer.methods[method_name]

            # Safety checks
            safety_result = self._check_safety(method_info, target_node)
            if not safety_result[0]:
                return MoveResult(success=False, error_message=safety_result[1])

            # Extract method code
            method_code = self._extract_method_code(lines, method_info)

            # Transform self references if needed
            transformed_code = self._transform_method_for_target(
                method_code, method_info, source_class
            )

            # Generate modified content
            modified_content = self._generate_modified_content(
                content,
                lines,
                source_node,
                target_node,
                method_info,
                transformed_code,
                target_instance_name,
                update_call_sites,
            )

            # Validate syntax
            try:
                ast.parse(modified_content)
            except SyntaxError as e:
                return MoveResult(
                    success=False,
                    error_message=f"Generated code has syntax error: {e}",
                )

            # Write the modified content
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(modified_content)

            # Record the fix
            record = FixRecord(
                record_id=generate_fix_id(),
                file_path=file_path,
                issue_type="move_method",
                original_content=content,
                fixed_content=modified_content,
                timestamp=datetime.now().isoformat(),
                fix_applied=f"Moved method '{method_name}' from '{source_class}' to '{target_class}'",
                rollback_available=True,
            )
            self.history.record_fix(record)

            return MoveResult(
                success=True,
                moved_method_code=transformed_code,
            )

        except FileNotFoundError:
            return MoveResult(
                success=False,
                error_message=f"File not found: {file_path}",
            )
        except Exception as e:
            return MoveResult(
                success=False,
                error_message=f"Unexpected error: {str(e)}",
            )

    def _find_class(self, tree: ast.Module, class_name: str) -> Optional[ast.ClassDef]:
        """Find a class definition by name in the AST."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return node
        return None

    def _check_safety(
        self, method_info: MethodInfo, target_node: ast.ClassDef
    ) -> Tuple[bool, str]:
        """Check if it's safe to move the method.

        Returns:
            Tuple of (is_safe, error_message)
        """
        # Check for abstract method
        if method_info.is_abstract:
            return False, "Cannot move abstract methods"

        # Check if target class already has a method with the same name
        for node in target_node.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == method_info.name:
                    return (
                        False,
                        f"Target class already has a method named '{method_info.name}'",
                    )

        return True, ""

    def _extract_method_code(self, lines: List[str], method_info: MethodInfo) -> str:
        """Extract the method code from the source file."""
        method_lines = lines[method_info.start_line - 1 : method_info.end_line]
        return "".join(method_lines)

    def _transform_method_for_target(
        self,
        method_code: str,
        method_info: MethodInfo,
        source_class: str,
    ) -> str:
        """Transform the method code for the target class.

        This handles self reference transformations if needed.
        For now, we keep the method as-is since it will use self in the target class.
        """
        # Parse the method code to normalize indentation
        lines = method_code.splitlines(keepends=True)
        if not lines:
            return method_code

        # Detect base indentation
        first_line = lines[0]
        base_indent = len(first_line) - len(first_line.lstrip())

        # Normalize to 4-space indentation for class body
        result_lines = []
        for line in lines:
            if line.strip():  # Non-empty line
                current_indent = len(line) - len(line.lstrip())
                relative_indent = current_indent - base_indent
                new_indent = 4 + relative_indent  # 4 spaces for class body
                result_lines.append(" " * new_indent + line.lstrip())
            else:
                result_lines.append(line)

        return "".join(result_lines)

    def _generate_modified_content(
        self,
        content: str,
        lines: List[str],
        source_node: ast.ClassDef,
        target_node: ast.ClassDef,
        method_info: MethodInfo,
        transformed_code: str,
        target_instance_name: Optional[str],
        update_call_sites: bool,
    ) -> str:
        """Generate the modified file content."""
        # We need to:
        # 1. Remove the method from source class
        # 2. Add the method to target class
        # 3. Optionally update call sites

        # Work with lines for precise editing
        result_lines = list(lines)

        # Check if source class will be empty after removing the method
        source_will_be_empty = self._will_class_be_empty_after_removal(
            source_node, method_info.name
        )

        # Find the end of target class body
        target_end_line = target_node.end_lineno or target_node.lineno

        # Prepare the method code to insert
        # Add a blank line before the method if needed
        insert_code = "\n" + transformed_code
        if not transformed_code.endswith("\n"):
            insert_code += "\n"

        # Split insert_code into lines for proper insertion
        insert_lines = insert_code.splitlines(keepends=True)
        # Ensure last line has newline
        if insert_lines and not insert_lines[-1].endswith("\n"):
            insert_lines[-1] += "\n"

        # Determine the order of operations based on class positions
        # If target is after source, remove from source first, then add to target
        # If target is before source, add to target first, then remove from source

        source_start = method_info.start_line
        source_end = method_info.end_line

        if target_node.lineno >= source_node.lineno:
            # Target is after or same as source
            # Remove from source first
            if source_will_be_empty:
                method_line = result_lines[source_start - 1]
                indent = len(method_line) - len(method_line.lstrip())
                pass_line = " " * indent + "pass\n"
                result_lines[source_start - 1 : source_end] = [pass_line]
                # Adjust target_end_line for removed lines
                lines_removed = source_end - source_start + 1 - 1  # +1 for pass
                target_end_line -= lines_removed
            else:
                del result_lines[source_start - 1 : source_end]
                lines_removed = source_end - source_start + 1
                target_end_line -= lines_removed

            # Now insert at target
            for i, line in enumerate(insert_lines):
                result_lines.insert(target_end_line + i, line)
        else:
            # Target is before source
            # Insert at target first
            for i, line in enumerate(insert_lines):
                result_lines.insert(target_end_line + i, line)

            # Adjust source line numbers for inserted lines
            lines_inserted = len(insert_lines)
            source_start += lines_inserted
            source_end += lines_inserted

            # Now remove from source
            if source_will_be_empty:
                method_line = result_lines[source_start - 1]
                indent = len(method_line) - len(method_line.lstrip())
                pass_line = " " * indent + "pass\n"
                result_lines[source_start - 1 : source_end] = [pass_line]
            else:
                del result_lines[source_start - 1 : source_end]

        return "".join(result_lines)

    def _will_class_be_empty_after_removal(
        self, class_node: ast.ClassDef, method_name: str
    ) -> bool:
        """Check if a class will be empty after removing a method."""
        meaningful_nodes = []
        for node in class_node.body:
            if isinstance(node, ast.Pass):
                continue
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                # Docstring
                continue
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == method_name:
                    continue
            meaningful_nodes.append(node)
        return len(meaningful_nodes) == 0

    def _is_class_body_empty(self, class_node: ast.ClassDef) -> bool:
        """Check if a class body is empty (only has pass or docstring)."""
        meaningful_nodes = []
        for node in class_node.body:
            if isinstance(node, ast.Pass):
                continue
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                # Docstring
                continue
            meaningful_nodes.append(node)
        return len(meaningful_nodes) == 0

    def _add_pass_to_empty_class(self, content: str, class_name: str) -> str:
        """Add pass statement to an empty class."""
        tree = ast.parse(content)
        class_node = self._find_class(tree, class_name)
        if class_node is None:
            return content

        lines = content.splitlines(keepends=True)

        # Find the class definition line and add pass after it
        class_line = class_node.lineno - 1

        # Find the colon at the end of class definition
        # Handle multi-line class definitions
        colon_line = class_line
        while colon_line < len(lines) and ":" not in lines[colon_line]:
            colon_line += 1

        # Insert pass after the class definition
        indent = "    "  # Standard 4-space indent
        pass_line = f"{indent}pass\n"

        # Check if there's already content after the class definition
        if colon_line + 1 < len(lines):
            next_line = lines[colon_line + 1]
            if next_line.strip() and not next_line.strip().startswith("pass"):
                # There's content, don't add pass
                return content

        lines.insert(colon_line + 1, pass_line)
        return "".join(lines)

    def analyze_method_dependencies(
        self, file_path: str, class_name: str, method_name: str
    ) -> Dict[str, Set[str]]:
        """Analyze the dependencies of a method.

        Args:
            file_path: Path to the Python file
            class_name: Name of the class containing the method
            method_name: Name of the method to analyze

        Returns:
            Dictionary with 'self_references', 'method_calls', and 'dependencies'
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)
            class_node = self._find_class(tree, class_name)

            if class_node is None:
                return {
                    "self_references": set(),
                    "method_calls": set(),
                    "dependencies": set(),
                }

            analyzer = MethodAnalyzer()
            analyzer.analyze_class(class_node)

            if method_name not in analyzer.methods:
                return {
                    "self_references": set(),
                    "method_calls": set(),
                    "dependencies": set(),
                }

            method_info = analyzer.methods[method_name]
            return {
                "self_references": method_info.self_references,
                "method_calls": method_info.method_calls,
                "dependencies": method_info.dependencies,
            }
        except Exception:
            return {
                "self_references": set(),
                "method_calls": set(),
                "dependencies": set(),
            }

    def suggest_target_class(
        self, file_path: str, source_class: str, method_name: str
    ) -> List[Tuple[str, float]]:
        """Suggest potential target classes for moving a method.

        This analyzes the method's dependencies and suggests classes that
        might be better homes for the method based on coupling.

        Args:
            file_path: Path to the Python file
            source_class: Name of the source class
            method_name: Name of the method

        Returns:
            List of (class_name, score) tuples, sorted by score descending
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)

            # Find all classes in the file
            classes = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name != source_class:
                    classes.append(node.name)

            # For now, return all classes with equal score
            # A more sophisticated implementation would analyze coupling
            return [(cls, 1.0) for cls in classes]
        except Exception:
            return []
