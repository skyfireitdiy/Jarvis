"""Dependency Injection Refactoring Module

This module provides functionality to refactor hardcoded dependencies into
dependency injection patterns, improving code testability and maintainability.
"""

import ast
import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Union

from jarvis.jarvis_auto_fix.fix_history import FixHistory, FixRecord, generate_fix_id


@dataclass
@dataclass
class DependencyInfo:
    """Information about a detected dependency.

    Attributes:
        class_name: The name of the class that has the dependency
        dependency_type: The type/class name of the dependency
        attribute_name: The attribute name where dependency is stored
        instantiation_line: Line number where dependency is instantiated
        instantiation_code: The code that instantiates the dependency
        has_parameters: Whether the instantiation has parameters
        parameters: List of parameter names if present
        is_optional: Whether the dependency can be optional (has default)
    """

    class_name: str
    dependency_type: str
    attribute_name: str
    instantiation_line: int
    instantiation_code: str
    parameters: List[str] = field(default_factory=list)
    has_parameters: bool = False
    is_optional: bool = False


@dataclass
class InjectionResult:
    """Result of a dependency injection refactoring operation.

    Attributes:
        success: Whether the injection was successful
        modified_code: The modified class code
        container_code: The generated dependency container code
        error_message: Error message if injection failed
        dependencies_injected: List of dependencies that were injected
    """

    success: bool
    modified_code: Optional[str] = None
    container_code: Optional[str] = None
    error_message: Optional[str] = None
    dependencies_injected: List[DependencyInfo] = field(default_factory=list)


class DependencyInjectionAnalyzer(ast.NodeVisitor):
    """AST visitor to analyze hardcoded dependencies in classes."""

    def __init__(self) -> None:
        """Initialize the analyzer."""
        self.dependencies: Dict[str, List[DependencyInfo]] = {}
        self._current_class: Optional[str] = None
        self._current_method: Optional[str] = None
        self._current_line: int = 0

    def analyze_file(self, source_code: str) -> Dict[str, List[DependencyInfo]]:
        """Analyze a file for hardcoded dependencies.

        Args:
            source_code: The source code to analyze.

        Returns:
            Dictionary mapping class names to their dependencies.
        """
        self.dependencies = {}
        try:
            tree = ast.parse(source_code)
            self.visit(tree)
        except SyntaxError:
            pass
        return self.dependencies

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition."""
        self._current_class = node.name
        self.generic_visit(node)
        self._current_class = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definition."""
        if node.name == "__init__":
            self._current_method = node.name
            self._current_line = node.lineno
            self._analyze_init_method(node)
        self.generic_visit(node)
        self._current_method = None

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definition."""
        if node.name == "__init__":
            self._current_method = node.name
            self._current_line = node.lineno
            self._analyze_init_method(node)
        self.generic_visit(node)
        self._current_method = None

    def _analyze_init_method(
        self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]
    ) -> None:
        """Analyze __init__ method for hardcoded dependencies.

        Args:
            node: The __init__ method node.
        """
        if not self._current_class:
            return

        dependencies = []

        # Walk through the body of __init__
        for child in ast.walk(node):
            # Look for assignments in self.attr = Class() pattern
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Attribute) and isinstance(
                        target.value, ast.Name
                    ):
                        if target.value.id == "self":
                            dep_info = self._analyze_assignment(child, target.attr)
                            if dep_info:
                                dependencies.append(dep_info)

        if dependencies:
            self.dependencies[self._current_class] = dependencies

    def _analyze_assignment(
        self, node: ast.Assign, attr_name: str
    ) -> Optional[DependencyInfo]:
        """Analyze an assignment to detect dependency instantiation.

        Args:
            node: The assignment node.
            attr_name: The attribute name being assigned.

        Returns:
            DependencyInfo if a hardcoded dependency is detected, None otherwise.
        """
        value = node.value

        # Check for direct instantiation: self.db = Database()
        if isinstance(value, ast.Call):
            if isinstance(value.func, ast.Name):
                dep_type = value.func.id
                has_params = len(value.args) > 0 or len(value.keywords) > 0
                params = self._extract_parameters(value) if has_params else []

                return DependencyInfo(
                    class_name=self._current_class or "",
                    dependency_type=dep_type,
                    attribute_name=attr_name,
                    instantiation_line=node.lineno,
                    instantiation_code=ast.unparse(value),
                    has_parameters=has_params,
                    parameters=params,
                    is_optional=False,
                )

        return None

    def _extract_parameters(self, call_node: ast.Call) -> List[str]:
        """Extract parameter names from a function call.

        Args:
            call_node: The Call node to analyze.

        Returns:
            List of parameter strings.
        """
        params = []

        # Positional arguments (as names if they are simple names)
        for arg in call_node.args:
            if isinstance(arg, ast.Name):
                params.append(arg.id)
            elif isinstance(arg, ast.Constant):
                # For string constants, use the value directly without extra quotes
                if isinstance(arg.value, str):
                    params.append(f'"{arg.value}"')
                else:
                    params.append(repr(arg.value))
            else:
                params.append(ast.unparse(arg))

        # Keyword arguments
        for keyword in call_node.keywords:
            if keyword.arg:
                params.append(f"{keyword.arg}={ast.unparse(keyword.value)}")

        return params


class DependencyInjectionRefactorer:
    """Refactorer for converting hardcoded dependencies to dependency injection."""

    def __init__(self, history: Optional[FixHistory] = None) -> None:
        """Initialize the refactorer.

        Args:
            history: Optional FixHistory for recording changes.
        """
        self.history = history
        self.analyzer = DependencyInjectionAnalyzer()

    def analyze_dependencies(self, source_code: str) -> Dict[str, List[DependencyInfo]]:
        """Analyze source code for hardcoded dependencies.

        Args:
            source_code: The source code to analyze.

        Returns:
            Dictionary mapping class names to their dependencies.
        """
        return self.analyzer.analyze_file(source_code)

    def refactor_to_constructor_injection(
        self,
        file_path: str,
        class_name: str,
        dependency_names: Optional[List[str]] = None,
        keep_defaults: bool = True,
    ) -> InjectionResult:
        """Refactor a class to use constructor dependency injection.

        Args:
            file_path: Path to the file to refactor.
            class_name: Name of the class to refactor.
            dependency_names: Optional list of specific dependencies to inject.
                           If None, inject all detected dependencies.
            keep_defaults: If True, keep default instantiation for backward compatibility.

        Returns:
            InjectionResult with the refactoring outcome.
        """
        try:
            # Read the file
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Parse the file first to check for syntax errors and class existence
            try:
                tree = ast.parse(content)
            except SyntaxError as e:
                return InjectionResult(
                    success=False,
                    error_message=f"File has syntax error: {e}",
                )

            # Find the target class
            target_class = None
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    target_class = node
                    break

            if not target_class:
                return InjectionResult(
                    success=False,
                    error_message=f"Class '{class_name}' not found in file",
                )

            # Find __init__ method
            init_method = None
            for item in target_class.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name == "__init__":
                        init_method = item
                        break

            if not init_method:
                return InjectionResult(
                    success=False,
                    error_message=f"Class '{class_name}' has no __init__ method",
                )

            # Analyze dependencies
            dependencies = self.analyze_dependencies(content)
            if class_name not in dependencies:
                return InjectionResult(
                    success=False,
                    error_message=f"No dependencies found for class '{class_name}'",
                )

            class_deps = dependencies[class_name]
            if dependency_names:
                class_deps = [
                    d for d in class_deps if d.attribute_name in dependency_names
                ]

            if not class_deps:
                return InjectionResult(
                    success=False,
                    error_message=f"No dependencies to inject in class '{class_name}'",
                )

            # Modify the constructor
            modified_init = self._modify_constructor(
                init_method, class_deps, keep_defaults
            )

            # Replace the init method
            for i, item in enumerate(target_class.body):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name == "__init__":
                        if modified_init is not None:
                            target_class.body[i] = modified_init
                        break

            # Generate modified code
            modified_code = ast.unparse(tree)

            # Validate the new code
            try:
                ast.parse(modified_code)
            except SyntaxError as e:
                return InjectionResult(
                    success=False,
                    error_message=f"Generated code has syntax error: {e}",
                )

            # Generate dependency container
            container_code = self._generate_dependency_container(
                class_name, class_deps, file_path
            )

            # Write the modified content
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(modified_code)

            # Record the fix
            if self.history:
                record = FixRecord(
                    record_id=generate_fix_id(),
                    file_path=file_path,
                    issue_type="dependency_injection",
                    original_content=content,
                    fixed_content=modified_code,
                    timestamp=datetime.now().isoformat(),
                    fix_applied=f"Injected {len(class_deps)} dependencies into '{class_name}' constructor",
                    rollback_available=True,
                )
                self.history.record_fix(record)

            return InjectionResult(
                success=True,
                modified_code=modified_code,
                container_code=container_code,
                dependencies_injected=class_deps,
            )

        except FileNotFoundError:
            return InjectionResult(
                success=False,
                error_message=f"File not found: {file_path}",
            )
        except Exception as e:
            return InjectionResult(
                success=False,
                error_message=f"Unexpected error: {str(e)}",
            )

    def _modify_constructor(
        self,
        init_method: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        dependencies: List[DependencyInfo],
        keep_defaults: bool,
    ) -> Union[ast.FunctionDef, ast.AsyncFunctionDef, None]:
        """Modify the constructor to inject dependencies.

        Args:
            init_method: The original __init__ method.
            dependencies: List of dependencies to inject.
            keep_defaults: Whether to keep default instantiation.

        Returns:
            Modified constructor node.
        """
        # Create a copy of the init method
        new_init = copy.deepcopy(init_method)

        # Add parameters to the signature
        for dep in dependencies:
            # Create parameter name (e.g., db for self.db)
            param_name = dep.attribute_name

            # Check if parameter already exists
            param_exists = any(arg.arg == param_name for arg in new_init.args.args)

            if not param_exists:
                # Add the parameter with optional type hint
                if keep_defaults:
                    # Add as optional parameter with None default
                    # Generate type annotation: Database | None (Python 3.10+ syntax)
                    union_annotation = ast.BinOp(
                        left=ast.Name(id=dep.dependency_type, ctx=ast.Load()),
                        op=ast.BitOr(),
                        right=ast.Constant(value=None),
                    )
                    new_init.args.args.append(
                        ast.arg(
                            arg=param_name,
                            annotation=union_annotation,
                        )
                    )
                    new_init.args.defaults.append(ast.Constant(value=None))
                else:
                    # Add as required parameter
                    new_init.args.args.append(
                        ast.arg(
                            arg=param_name,
                            annotation=ast.Name(id=dep.dependency_type, ctx=ast.Load()),
                        )
                    )

        # Modify the body to use injected dependencies
        class DependencyModifier(ast.NodeTransformer):
            def __init__(self, deps: List[DependencyInfo], keep: bool) -> None:
                self.dependencies = deps
                self.keep_defaults = keep

            def visit_Assign(self, node: ast.Assign) -> ast.AST | None:
                # Check if this is a dependency assignment we should modify
                for target in node.targets:
                    if isinstance(target, ast.Attribute) and isinstance(
                        target.value, ast.Name
                    ):
                        if target.value.id == "self":
                            for dep in self.dependencies:
                                if dep.attribute_name == target.attr:
                                    if self.keep_defaults:
                                        # Replace with: self.attr = attr or Dep()
                                        return self._generate_default_assignment(
                                            dep, node
                                        )
                                    else:
                                        # Replace with: self.attr = attr
                                        new_assign = ast.Assign(
                                            targets=[
                                                ast.Attribute(
                                                    value=ast.Name(
                                                        id="self", ctx=ast.Load()
                                                    ),
                                                    attr=dep.attribute_name,
                                                    ctx=ast.Store(),
                                                )
                                            ],
                                            value=ast.Name(
                                                id=dep.attribute_name, ctx=ast.Load()
                                            ),
                                        )
                                        new_assign.lineno = node.lineno
                                        return new_assign
                return node

            def _generate_default_assignment(
                self, dep: DependencyInfo, original: ast.Assign
            ) -> ast.Assign:
                """Generate assignment with default fallback."""
                # Generate: self.attr = attr or Dep(params)
                or_test = ast.BoolOp(
                    op=ast.Or(),
                    values=[
                        ast.Name(id=dep.attribute_name, ctx=ast.Load()),
                        original.value,
                    ],
                )
                new_node = ast.Assign(
                    targets=[
                        ast.Attribute(
                            value=ast.Name(id="self", ctx=ast.Load()),
                            attr=dep.attribute_name,
                            ctx=ast.Store(),
                        )
                    ],
                    value=or_test,
                )
                # Set lineno to match original
                new_node.lineno = original.lineno
                return new_node

        modifier = DependencyModifier(dependencies, keep_defaults)
        new_init = modifier.visit(new_init)

        # Type narrowing for mypy
        result: Union[ast.FunctionDef, ast.AsyncFunctionDef, None] = new_init
        return result

    def _generate_dependency_container(
        self, class_name: str, dependencies: List[DependencyInfo], file_path: str
    ) -> str:
        """Generate a dependency injection container class.

        Args:
            class_name: Name of the class that was refactored.
            dependencies: List of injected dependencies.
            file_path: Path to the file (for module context).

        Returns:
            Generated container code.
        """
        lines = []
        container_name = f"{class_name}DIContainer"

        lines.append('"""Dependency Injection Container."""')
        lines.append("")
        lines.append(f"class {container_name}:")
        lines.append(f'    """Dependency container for {class_name}."""')
        lines.append("")
        lines.append("    def __init__(self) -> None:")
        lines.append('        """Initialize the container."""')

        # Initialize private attributes for dependencies
        for dep in dependencies:
            lines.append(
                f"        self._{dep.attribute_name}: {dep.dependency_type} | None = None"
            )
        lines.append("")

        # Generate properties for each dependency
        for dep in dependencies:
            lines.append("    @property")
            lines.append(
                f"    def {dep.attribute_name}(self) -> {dep.dependency_type}:"
            )
            lines.append(
                f'        """Get or create the {dep.dependency_type} dependency."""'
            )
            lines.append(f"        if self._{dep.attribute_name} is None:")

            # Generate instantiation code
            if dep.has_parameters and dep.parameters:
                params_str = ", ".join(dep.parameters)
                lines.append(
                    f"            self._{dep.attribute_name} = {dep.dependency_type}({params_str})"
                )
            else:
                lines.append(
                    f"            self._{dep.attribute_name} = {dep.dependency_type}()"
                )

            lines.append(f"        return self._{dep.attribute_name}")
            lines.append("")

        # Generate factory method for the target class
        lines.append(f"    def create_{class_name.lower()}(self) -> {class_name}:")
        lines.append(
            f'        """Create an instance of {class_name} with injected dependencies."""'
        )
        lines.append(f"        return {class_name}(")

        for i, dep in enumerate(dependencies):
            comma = "," if i < len(dependencies) - 1 else ""
            lines.append(
                f"            {dep.attribute_name}=self.{dep.attribute_name}{comma}"
            )

        lines.append("        )")

        return "\n".join(lines)
