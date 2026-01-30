"""Extract Class Refactoring Module

This module provides functionality to extract methods and attributes from a class
into a new separate class.
"""

import ast
import builtins
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from jarvis.jarvis_auto_fix.fix_history import FixHistory, FixRecord, generate_fix_id


@dataclass
class ClassMemberInfo:
    """Information about a class member (method or attribute)."""

    name: str
    member_type: str
    start_line: int
    end_line: int
    dependencies: Set[str]
    used_by: Set[str]


@dataclass
class ExtractionPlan:
    """Plan for extracting members into a new class."""

    members_to_extract: List[str]
    new_class_name: str
    reference_name: str
    additional_dependencies: List[str]


@dataclass
class ClassExtractionResult:
    """Result of a class extraction operation."""

    success: bool
    new_class_code: str = ""
    modified_original_class: str = ""
    error_message: str = ""


class ClassMemberAnalyzer(ast.NodeVisitor):
    """AST visitor to analyze class members and their dependencies."""

    def __init__(self) -> None:
        self.methods: Dict[str, ClassMemberInfo] = {}
        self.attributes: Dict[str, ClassMemberInfo] = {}
        self.class_attributes: Dict[str, ClassMemberInfo] = {}
        self._current_method: Optional[str] = None
        self._method_uses: Dict[str, Set[str]] = {}

    def analyze_class(self, class_node: ast.ClassDef) -> None:
        """Analyze a class definition to extract member information."""
        for node in class_node.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._analyze_method(node)
            elif isinstance(node, ast.Assign):
                self._analyze_class_attribute(node)
            elif isinstance(node, ast.AnnAssign):
                self._analyze_annotated_attribute(node)
        self._analyze_dependencies()

    def _analyze_method(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Analyze a method definition."""
        method_name = node.name
        self.methods[method_name] = ClassMemberInfo(
            name=method_name,
            member_type="method",
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            dependencies=set(),
            used_by=set(),
        )
        self._current_method = method_name
        self._method_uses[method_name] = set()
        self.visit(node)
        self._current_method = None

    def _analyze_class_attribute(self, node: ast.Assign) -> None:
        """Analyze a class-level attribute assignment."""
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.class_attributes[target.id] = ClassMemberInfo(
                    name=target.id,
                    member_type="class_attribute",
                    start_line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    dependencies=set(),
                    used_by=set(),
                )

    def _analyze_annotated_attribute(self, node: ast.AnnAssign) -> None:
        """Analyze an annotated class attribute."""
        if isinstance(node.target, ast.Name):
            self.class_attributes[node.target.id] = ClassMemberInfo(
                name=node.target.id,
                member_type="class_attribute",
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                dependencies=set(),
                used_by=set(),
            )

    def _analyze_dependencies(self) -> None:
        """Analyze dependencies between methods."""
        all_members = set(self.methods.keys()) | set(self.class_attributes.keys())
        for method_name, uses in self._method_uses.items():
            if method_name not in self.methods:
                continue
            for used_name in uses:
                if used_name in all_members and used_name != method_name:
                    self.methods[method_name].dependencies.add(used_name)
                    if used_name in self.methods:
                        self.methods[used_name].used_by.add(method_name)
                    elif used_name in self.class_attributes:
                        self.class_attributes[used_name].used_by.add(method_name)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Visit attribute access to track self.xxx usage."""
        if (
            self._current_method
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        ):
            self._method_uses[self._current_method].add(node.attr)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Visit function calls to track self.method() usage."""
        if self._current_method and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
                self._method_uses[self._current_method].add(node.func.attr)
        self.generic_visit(node)


class ExtractClassRefactorer:
    """Refactorer for extracting methods and attributes into a new class."""

    BUILTINS = set(dir(builtins))

    def __init__(self, history: Optional[FixHistory] = None) -> None:
        """Initialize the ExtractClassRefactorer."""
        self.history = history or FixHistory()

    def extract_class(
        self,
        file_path: str,
        source_class: str,
        methods_to_extract: List[str],
        new_class_name: str,
        reference_name: Optional[str] = None,
        include_dependencies: bool = True,
    ) -> ClassExtractionResult:
        """Extract methods and their dependencies into a new class."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")

            try:
                tree = ast.parse(content)
            except SyntaxError as e:
                return ClassExtractionResult(
                    success=False, error_message=f"Syntax error in file: {e}"
                )

            class_node = self._find_class(tree, source_class)
            if class_node is None:
                return ClassExtractionResult(
                    success=False,
                    error_message=f"Class '{source_class}' not found in file",
                )

            if not self._is_valid_identifier(new_class_name):
                return ClassExtractionResult(
                    success=False, error_message=f"Invalid class name: {new_class_name}"
                )

            if reference_name is None:
                reference_name = self._to_snake_case(new_class_name)

            analyzer = ClassMemberAnalyzer()
            analyzer.analyze_class(class_node)

            invalid_methods = set(methods_to_extract) - set(analyzer.methods.keys())
            if invalid_methods:
                return ClassExtractionResult(
                    success=False,
                    error_message=f"Methods not found: {', '.join(invalid_methods)}",
                )

            plan = self._create_extraction_plan(
                analyzer,
                methods_to_extract,
                new_class_name,
                reference_name,
                include_dependencies,
            )

            new_class_code = self._generate_new_class(lines, class_node, analyzer, plan)
            modified_content = self._modify_original_class(
                content, lines, class_node, analyzer, plan
            )

            try:
                ast.parse(modified_content)
            except SyntaxError as e:
                return ClassExtractionResult(
                    success=False, error_message=f"Generated code has syntax error: {e}"
                )

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(modified_content)

            record = FixRecord(
                record_id=generate_fix_id(),
                file_path=file_path,
                issue_type="extract_class",
                original_content=content,
                fixed_content=modified_content,
                timestamp=datetime.now().isoformat(),
                fix_applied=f"Extracted methods {methods_to_extract} from '{source_class}' into '{new_class_name}'",
                rollback_available=True,
            )
            self.history.record_fix(record)

            return ClassExtractionResult(
                success=True,
                new_class_code=new_class_code,
                modified_original_class=modified_content,
            )

        except FileNotFoundError:
            return ClassExtractionResult(
                success=False, error_message=f"File not found: {file_path}"
            )
        except Exception as e:
            return ClassExtractionResult(
                success=False, error_message=f"Unexpected error: {str(e)}"
            )

    def _find_class(self, tree: ast.Module, class_name: str) -> Optional[ast.ClassDef]:
        """Find a class definition by name in the AST."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return node
        return None

    def _is_valid_identifier(self, name: str) -> bool:
        """Check if a name is a valid Python identifier."""
        return bool(name) and name.isidentifier()

    def _to_snake_case(self, name: str) -> str:
        """Convert a CamelCase name to snake_case."""
        result = []
        for i, char in enumerate(name):
            if char.isupper() and i > 0:
                result.append("_")
            result.append(char.lower())
        return "".join(result)

    def _create_extraction_plan(
        self,
        analyzer: ClassMemberAnalyzer,
        methods_to_extract: List[str],
        new_class_name: str,
        reference_name: str,
        include_dependencies: bool,
    ) -> ExtractionPlan:
        """Create a plan for extracting methods."""
        members_to_extract = set(methods_to_extract)
        additional_deps: List[str] = []

        if include_dependencies:
            to_process = list(methods_to_extract)
            processed: Set[str] = set()
            while to_process:
                member = to_process.pop(0)
                if member in processed:
                    continue
                processed.add(member)
                if member in analyzer.methods:
                    deps = analyzer.methods[member].dependencies
                    for dep in deps:
                        if dep not in members_to_extract:
                            members_to_extract.add(dep)
                            additional_deps.append(dep)
                            to_process.append(dep)

        return ExtractionPlan(
            members_to_extract=sorted(members_to_extract),
            new_class_name=new_class_name,
            reference_name=reference_name,
            additional_dependencies=additional_deps,
        )

    def _generate_new_class(
        self,
        lines: List[str],
        class_node: ast.ClassDef,
        analyzer: ClassMemberAnalyzer,
        plan: ExtractionPlan,
    ) -> str:
        """Generate the code for the new extracted class."""
        class_lines = [f"class {plan.new_class_name}:"]

        attrs_to_extract = [
            name
            for name in plan.members_to_extract
            if name in analyzer.class_attributes
        ]

        if attrs_to_extract:
            class_lines.append("    def __init__(self):")
            for attr_name in sorted(attrs_to_extract):
                attr_info = analyzer.class_attributes[attr_name]
                attr_line = lines[attr_info.start_line - 1].strip()
                if "=" in attr_line:
                    _, value = attr_line.split("=", 1)
                    class_lines.append(f"        self.{attr_name} ={value}")
                else:
                    class_lines.append(f"        self.{attr_name} = None")
            class_lines.append("")

        methods_to_extract = [
            name for name in plan.members_to_extract if name in analyzer.methods
        ]

        for method_name in sorted(methods_to_extract):
            method_info = analyzer.methods[method_name]
            method_lines = lines[method_info.start_line - 1 : method_info.end_line]
            if method_lines:
                # Detect the base indentation of the method definition
                first_line = method_lines[0]
                method_indent = len(first_line) - len(first_line.lstrip())
                for line in method_lines:
                    stripped = line.rstrip()
                    if stripped:
                        # Calculate relative indentation from method definition
                        current_indent = len(line) - len(line.lstrip())
                        relative_indent = current_indent - method_indent
                        # Add 4 spaces for class body + relative indentation
                        class_lines.append(" " * (4 + relative_indent) + line.lstrip())
                    else:
                        class_lines.append("")
            class_lines.append("")

        if len(class_lines) == 1:
            class_lines.append("    pass")

        return "\n".join(class_lines)

    def _modify_original_class(
        self,
        content: str,
        lines: List[str],
        class_node: ast.ClassDef,
        analyzer: ClassMemberAnalyzer,
        plan: ExtractionPlan,
    ) -> str:
        """Modify the original class to remove extracted members."""
        lines_to_remove: Set[int] = set()

        for member_name in plan.members_to_extract:
            if member_name in analyzer.methods:
                info = analyzer.methods[member_name]
                for line_num in range(info.start_line, info.end_line + 1):
                    lines_to_remove.add(line_num)
            elif member_name in analyzer.class_attributes:
                info = analyzer.class_attributes[member_name]
                for line_num in range(info.start_line, info.end_line + 1):
                    lines_to_remove.add(line_num)

        result_lines: List[str] = []
        insert_pos = class_node.lineno - 1

        for i in range(insert_pos):
            result_lines.append(lines[i])

        new_class_code = self._generate_new_class(lines, class_node, analyzer, plan)
        result_lines.append("")
        result_lines.append(new_class_code)
        result_lines.append("")

        class_start = class_node.lineno
        class_end = class_node.end_lineno or class_node.lineno

        # Collect remaining lines in the original class
        remaining_class_lines: List[str] = []
        for i in range(class_start - 1, class_end):
            line_num = i + 1
            if line_num not in lines_to_remove:
                remaining_class_lines.append(lines[i])

        # Check if class body is empty (only class definition line remains)
        has_body = False
        for line in remaining_class_lines[1:]:  # Skip class definition line
            if line.strip() and not line.strip().startswith("#"):
                has_body = True
                break

        # Add remaining class lines
        result_lines.extend(remaining_class_lines)

        # If class body is empty, add pass statement
        if not has_body and remaining_class_lines:
            # Detect indentation from class definition
            class_def_line = remaining_class_lines[0]
            base_indent = len(class_def_line) - len(class_def_line.lstrip())
            result_lines.append(" " * (base_indent + 4) + "pass")

        for i in range(class_end, len(lines)):
            result_lines.append(lines[i])

        return "\n".join(result_lines)

    def analyze_class_cohesion(
        self, file_path: str, class_name: str
    ) -> List[Tuple[List[str], str]]:
        """Analyze a class for potential extraction candidates."""
        candidates: List[Tuple[List[str], str]] = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            tree = ast.parse(content)
            class_node = self._find_class(tree, class_name)
            if class_node is None:
                return candidates
            analyzer = ClassMemberAnalyzer()
            analyzer.analyze_class(class_node)
            method_groups = self._find_cohesive_groups(analyzer)
            for group in method_groups:
                if len(group) >= 2:
                    candidates.append(
                        (list(group), f"Methods {group} form a cohesive group")
                    )
        except (FileNotFoundError, SyntaxError):
            pass
        return candidates

    def _find_cohesive_groups(self, analyzer: ClassMemberAnalyzer) -> List[Set[str]]:
        """Find groups of methods that are highly cohesive."""
        groups: List[Set[str]] = []
        processed: Set[str] = set()

        for method_name, method_info in analyzer.methods.items():
            if method_name in processed or method_name == "__init__":
                continue
            group: Set[str] = {method_name}
            processed.add(method_name)
            for dep in method_info.dependencies:
                if dep in analyzer.methods and dep not in processed:
                    group.add(dep)
                    processed.add(dep)
            for user in method_info.used_by:
                if user in analyzer.methods and user not in processed:
                    group.add(user)
                    processed.add(user)
            if len(group) >= 2:
                groups.append(group)
        return groups
