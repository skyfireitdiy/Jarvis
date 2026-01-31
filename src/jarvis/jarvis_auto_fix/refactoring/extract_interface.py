"""Extract Interface Refactoring Module

This module provides functionality to extract an interface (ABC or Protocol)
from a concrete class, identifying public methods and generating
an abstract base class definition.
"""

import ast
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Set

from jarvis.jarvis_auto_fix.fix_history import FixHistory, FixRecord, generate_fix_id


@dataclass
class InterfaceInfo:
    """Information about an extracted interface."""

    interface_name: str
    methods: List[str]
    original_class: str
    file_path: str
    start_line: int
    base_type: str  # 'ABC' or 'Protocol'


@dataclass
class InterfaceExtractionResult:
    """Result of an interface extraction operation."""

    success: bool
    interface_code: str = ""
    modified_class_code: str = ""
    error_message: str = ""
    interface_info: Optional[InterfaceInfo] = None


class InterfaceMethodAnalyzer(ast.NodeVisitor):
    """AST visitor to analyze methods that can be extracted to an interface."""

    def __init__(self) -> None:
        self.public_methods: Dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        self.private_methods: Set[str] = set()
        self.special_methods: Set[str] = set()
        self._current_class: Optional[str] = None

    def analyze_class(self, class_node: ast.ClassDef) -> None:
        """Analyze a class to identify methods suitable for interface extraction.

        Args:
            class_node: The AST ClassDef node to analyze.
        """
        self._current_class = class_node.name

        for node in class_node.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_name = node.name

                # Skip private methods (name mangling)
                if method_name.startswith("__") and not method_name.endswith("__"):
                    self.private_methods.add(method_name)
                    continue

                # Skip "private" methods (single underscore)
                if method_name.startswith("_") and method_name != "__init__":
                    self.private_methods.add(method_name)
                    continue

                # Skip special methods except __init__
                if method_name.startswith("__") and method_name.endswith("__"):
                    if method_name == "__init__":
                        # Include __init__ but convert to abstractmethod
                        self.public_methods[method_name] = node
                    else:
                        self.special_methods.add(method_name)
                    continue

                # Include public methods
                self.public_methods[method_name] = node

    def get_method_signature(self, method_name: str) -> Optional[str]:
        """Get the signature of a method as a string (without method name).

        Args:
            method_name: Name of the method.

        Returns:
            Method signature string (parameters only), or None if method not found.
        """
        method = self.public_methods.get(method_name)
        if method is None:
            return None

        # Build signature (parameters only, no method name)
        args = []

        # Add 'self' parameter
        args.append("self")

        # Add other parameters
        for arg in method.args.args[1:]:  # Skip 'self'
            arg_str = arg.arg
            if arg.annotation:
                arg_str += ": " + ast.unparse(arg.annotation)
            args.append(arg_str)

        # Handle *args
        if method.args.vararg:
            vararg_str = "*" + method.args.vararg.arg
            if method.args.vararg.annotation:
                vararg_str += ": " + ast.unparse(method.args.vararg.annotation)
            args.append(vararg_str)

        # Handle **kwargs
        if method.args.kwarg:
            kwarg_str = "**" + method.args.kwarg.arg
            if method.args.kwarg.annotation:
                kwarg_str += ": " + ast.unparse(method.args.kwarg.annotation)
            args.append(kwarg_str)

        # Add return type annotation
        signature = ", ".join(args)
        if method.returns:
            signature += " -> " + ast.unparse(method.returns)

        return signature

    def get_method_docstring(self, method_name: str) -> Optional[str]:
        """Get the docstring of a method.

        Args:
            method_name: Name of the method.

        Returns:
            Docstring content, or None if no docstring.
        """
        method = self.public_methods.get(method_name)
        if method is None:
            return None

        docstring = ast.get_docstring(method)
        return docstring


class ExtractInterfaceRefactorer:
    """Refactorer to extract an interface from a concrete class.

    This refactorer identifies public methods in a class and generates
    an abstract base class (ABC) or Protocol interface definition.
    """

    def __init__(self, history: Optional[FixHistory] = None) -> None:
        """Initialize the ExtractInterfaceRefactorer.

        Args:
            history: Optional FixHistory instance for tracking changes.
        """
        self.history = history or FixHistory()
        self.analyzer = InterfaceMethodAnalyzer()

    def extract_interface(
        self,
        file_path: str,
        class_name: str,
        interface_name: Optional[str] = None,
        base_type: str = "ABC",
        methods: Optional[List[str]] = None,
    ) -> InterfaceExtractionResult:
        """Extract an interface from a concrete class.

        Args:
            file_path: Path to the file containing the class.
            class_name: Name of the class to extract interface from.
            interface_name: Name for the interface (auto-generated if None).
            base_type: Type of interface ('ABC' or 'Protocol').
            methods: List of methods to include (None means all public methods).

        Returns:
            InterfaceExtractionResult containing the interface code and modified class.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)

            # Find the target class
            target_class = None
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    target_class = node
                    break

            if target_class is None:
                return InterfaceExtractionResult(
                    success=False,
                    error_message=f"Class '{class_name}' not found in file",
                )

            # Analyze class methods
            self.analyzer.analyze_class(target_class)

            # Determine which methods to include
            if methods is None:
                methods = list(self.analyzer.public_methods.keys())

            # Generate interface name if not provided
            if interface_name is None:
                interface_name = self._suggest_interface_name(class_name, base_type)

            # Generate interface code
            interface_code = self._generate_interface_code(
                interface_name, methods, base_type
            )

            # Modify original class to inherit from interface
            modified_code = self._modify_original_class(
                content, class_name, interface_name, target_class.lineno
            )

            # Record fix if successful
            if interface_code and modified_code:
                record_id = generate_fix_id()
                record = FixRecord(
                    record_id=record_id,
                    file_path=file_path,
                    issue_type="extract_interface",
                    original_content=content,
                    fixed_content=modified_code,
                    timestamp=datetime.now().isoformat(),
                    fix_applied=f"Extracted interface {interface_name} from {class_name}",
                    rollback_available=True,
                )
                self.history.record_fix(record)

            interface_info = InterfaceInfo(
                interface_name=interface_name,
                methods=methods,
                original_class=class_name,
                file_path=file_path,
                start_line=target_class.lineno,
                base_type=base_type,
            )

            return InterfaceExtractionResult(
                success=True,
                interface_code=interface_code,
                modified_class_code=modified_code,
                interface_info=interface_info,
            )

        except Exception as e:
            return InterfaceExtractionResult(
                success=False, error_message=f"Error extracting interface: {str(e)}"
            )

    def _suggest_interface_name(self, class_name: str, base_type: str) -> str:
        """Suggest a name for the interface.

        Args:
            class_name: Name of the original class.
            base_type: Type of interface ('ABC' or 'Protocol').

        Returns:
            Suggested interface name.
        """
        if base_type == "Protocol":
            # Protocol naming: remove 'Impl' suffix or add 'Protocol' suffix
            if class_name.endswith("Impl"):
                return class_name[:-4]  # Remove 'Impl'
            else:
                return class_name + "Protocol"
        else:
            # ABC naming: add 'I' prefix or 'able'/'Abstract' suffix
            if class_name.startswith("I") and len(class_name) > 2:
                return class_name  # Already has I prefix
            elif class_name.endswith("Impl"):
                return "I" + class_name[:-4]  # Remove Impl and add I
            else:
                return "I" + class_name  # Add I prefix

    def _generate_interface_code(
        self, interface_name: str, methods: List[str], base_type: str
    ) -> str:
        """Generate the interface (ABC or Protocol) code.

        Args:
            interface_name: Name for the interface.
            methods: List of method names to include.
            base_type: Type of interface ('ABC' or 'Protocol').

        Returns:
            Generated interface code as a string.
        """
        lines = []

        # Import statement
        if base_type == "ABC":
            lines.append("from abc import ABC, abstractmethod\n")
        else:
            lines.append("from typing import Protocol\n")

        # Interface class definition
        if base_type == "ABC":
            lines.append(f"class {interface_name}(ABC):")
        else:
            lines.append(f"class {interface_name}(Protocol):")

        # Add docstring
        lines.append(f'    """Interface for {interface_name}."""\n')

        # Add methods
        for method_name in methods:
            signature = self.analyzer.get_method_signature(method_name)
            docstring = self.analyzer.get_method_docstring(method_name)

            if signature is None:
                continue

            # Add abstractmethod decorator for ABC
            if base_type == "ABC":
                if method_name == "__init__":
                    # __init__ should be abstract but not use abstractmethod decorator
                    lines.append(f"    def {method_name}({signature}):")
                else:
                    lines.append("    @abstractmethod")
                    lines.append(f"    def {method_name}({signature}):")
            else:
                # Protocol methods don't need decorators
                lines.append(f"    def {method_name}({signature}):")

            # Add docstring
            if docstring:
                lines.append(f'        """{docstring}"""')
            else:
                # Add ... for method body
                lines.append("        ...")

            lines.append("")  # Empty line between methods

        return "\n".join(lines)

    def _modify_original_class(
        self, content: str, class_name: str, interface_name: str, class_lineno: int
    ) -> str:
        """Modify the original class to inherit from the interface.

        Args:
            content: Original file content.
            class_name: Name of the class to modify.
            interface_name: Name of the interface to inherit from.
            class_lineno: Line number where the class is defined.

        Returns:
            Modified file content.
        """
        lines = content.split("\n")

        # Find the class definition line
        for i, line in enumerate(lines):
            if i == class_lineno - 1:  # Line numbers are 1-indexed
                # Check if class already has bases
                if ":" in line:
                    # Add interface to existing bases
                    if "(" in line:
                        # Class already has bases
                        closing_paren = line.rfind(")")
                        if closing_paren > 0:
                            # Insert interface before closing paren
                            lines[i] = (
                                line[:closing_paren]
                                + f", {interface_name}"
                                + line[closing_paren:]
                            )
                    else:
                        # No bases, add them
                        lines[i] = line.replace(":", f"({interface_name}):")
                break

        return "\n".join(lines)

    def analyze_interface_candidates(self, file_path: str) -> List[InterfaceInfo]:
        """Analyze a file to find classes suitable for interface extraction.

        Args:
            file_path: Path to the file to analyze.

        Returns:
            List of InterfaceInfo for classes with extractable interfaces.
        """
        candidates = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Analyze each class
                    self.analyzer.analyze_class(node)

                    # Check if class has enough public methods
                    if len(self.analyzer.public_methods) >= 2:
                        # Create interface info
                        interface_info = InterfaceInfo(
                            interface_name=self._suggest_interface_name(
                                node.name, "ABC"
                            ),
                            methods=list(self.analyzer.public_methods.keys()),
                            original_class=node.name,
                            file_path=file_path,
                            start_line=node.lineno,
                            base_type="ABC",
                        )
                        candidates.append(interface_info)
        except Exception:
            # Skip files that can't be parsed
            pass

        return candidates
