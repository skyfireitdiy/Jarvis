"""C/C++语言支持实现。"""

import os
import re
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Set
from typing import cast

from tree_sitter import Language
from tree_sitter import Node

from jarvis.jarvis_utils.config import read_text_file

from ..base_language import BaseLanguageSupport
from ..dependency_analyzer import Dependency
from ..dependency_analyzer import DependencyAnalyzer
from ..dependency_analyzer import DependencyGraph
from ..file_ignore import filter_walk_dirs
from ..symbol_extractor import Symbol
from ..symbol_extractor import SymbolExtractor
from ..tree_sitter_extractor import TreeSitterExtractor

# --- C/C++ Symbol Query ---

# C语言查询（不包含class_specifier，因为C不支持class）
C_SYMBOL_QUERY = """
(function_declarator
  declarator: (identifier) @function.name)

(struct_specifier
  name: (type_identifier) @struct.name)
  
(union_specifier
  name: (type_identifier) @union.name)
  
(enum_specifier
  name: (type_identifier) @enum.name)

(preproc_def
  name: (identifier) @macro.name)

(type_definition
  declarator: (type_identifier) @typedef.name)
"""

# C++语言查询（包含class_specifier）
CPP_SYMBOL_QUERY = """
(function_declarator
  declarator: (identifier) @function.name)

(struct_specifier
  name: (type_identifier) @struct.name)

(class_specifier
  name: (type_identifier) @class.name)
  
(union_specifier
  name: (type_identifier) @union.name)
  
(enum_specifier
  name: (type_identifier) @enum.name)

(namespace_definition
  name: (identifier)? @namespace.name)

(preproc_def
  name: (identifier) @macro.name)

(type_definition
  declarator: (type_identifier) @typedef.name)

(template_declaration) @template
"""

# --- C/C++ Language Setup ---

try:
    import tree_sitter_c

    C_LANGUAGE: Optional[Language] = cast(Optional[Language], tree_sitter_c.language())
except (ImportError, Exception):
    C_LANGUAGE = None

try:
    import tree_sitter_cpp

    CPP_LANGUAGE: Optional[Language] = cast(
        Optional[Language], tree_sitter_cpp.language()
    )
except (ImportError, Exception):
    CPP_LANGUAGE = None


# --- C/C++ Symbol Extractors ---


class CSymbolExtractor(TreeSitterExtractor):
    """Extracts symbols from C code using tree-sitter."""

    def __init__(self) -> None:
        if not C_LANGUAGE:
            raise RuntimeError("C tree-sitter grammar not available.")
        super().__init__(C_LANGUAGE, C_SYMBOL_QUERY)

    def _create_symbol_from_capture(
        self, node: Node, name: str, file_path: str
    ) -> Optional[Symbol]:
        kind_map = {
            "function.name": "function",
            "struct.name": "struct",
            "union.name": "union",
            "enum.name": "enum",
            "macro.name": "macro",
            "typedef.name": "typedef",
        }
        symbol_kind = kind_map.get(name)
        if not symbol_kind:
            return None

        if node.text is None:
            return None

        return Symbol(
            name=node.text.decode("utf8"),
            kind=symbol_kind,
            file_path=file_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
        )


class CppSymbolExtractor(TreeSitterExtractor):
    """Extracts symbols from C++ code using tree-sitter."""

    def __init__(self) -> None:
        if not CPP_LANGUAGE:
            raise RuntimeError("C++ tree-sitter grammar not available.")
        super().__init__(CPP_LANGUAGE, CPP_SYMBOL_QUERY)

    def _create_symbol_from_capture(
        self, node: Node, name: str, file_path: str
    ) -> Optional[Symbol]:
        kind_map = {
            "function.name": "function",
            "struct.name": "struct",
            "class.name": "class",
            "union.name": "union",
            "enum.name": "enum",
            "namespace.name": "namespace",
            "macro.name": "macro",
            "typedef.name": "typedef",
            "template": "template",
        }
        symbol_kind = kind_map.get(name)
        if not symbol_kind:
            return None

        # For anonymous namespaces, use a generated name
        if name == "namespace.name":
            symbol_name = (
                node.text.decode("utf8") if node.text else "<anonymous_namespace>"
            )
        elif name == "template":
            # For template declarations, extract the template name or use a generic name
            # Try to find the function/class name after template
            if node.text is None:
                return None
            template_text = node.text.decode("utf8").strip()
            # Extract template parameters and the following declaration
            # This is a simplified extraction - in practice, you might want more sophisticated parsing
            if "template" in template_text:
                # Try to extract the name after template<...>
                parts = template_text.split(">", 1)
                if len(parts) > 1:
                    # Look for function/class name in the second part
                    match = re.search(r"\b(function|class|struct)\s+(\w+)", parts[1])
                    if match:
                        symbol_name = f"template_{match.group(2)}"
                    else:
                        symbol_name = "template"
                else:
                    symbol_name = "template"
            else:
                symbol_name = "template"
        else:
            if node.text is None:
                return None
            symbol_name = node.text.decode("utf8")

        if not symbol_name:
            return None

        return Symbol(
            name=symbol_name,
            kind=symbol_kind,
            file_path=file_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
        )


# --- C/C++ Dependency Analyzers ---


class CDependencyAnalyzer(DependencyAnalyzer):
    """Analyzes C include dependencies and macro calls."""

    def analyze_imports(self, file_path: str, content: str) -> List[Dependency]:
        """Analyzes C #include statements."""
        dependencies: List[Dependency] = []

        # Match #include directives
        # Format: #include <header.h> or #include "header.h"
        include_pattern = re.compile(r'#include\s+[<"]([^>"]+)[>"]')

        for line_num, line in enumerate(content.split("\n"), start=1):
            match = include_pattern.search(line)
            if match:
                header = match.group(1)
                dependencies.append(
                    Dependency(
                        from_module=header,
                        imported_symbol=None,
                        file_path=file_path,
                        line=line_num,
                    )
                )

        return dependencies

    def build_dependency_graph(self, project_root: str) -> DependencyGraph:
        """Builds a dependency graph for a C project."""
        graph = DependencyGraph()

        # First pass: Collect all macro definitions
        macro_definitions: Dict[str, str] = {}  # macro_name -> file_path

        for root, dirs, files in os.walk(project_root):
            dirs[:] = filter_walk_dirs(dirs)
            for file in files:
                file_path = os.path.join(root, file)
                if not self._is_source_file(file_path):
                    continue
                try:
                    # Extract macro definitions using tree-sitter
                    self._extract_macro_definitions(file_path, macro_definitions)
                except Exception:
                    continue

        # Second pass: Analyze dependencies
        for root, dirs, files in os.walk(project_root):
            dirs[:] = filter_walk_dirs(dirs)

            for file in files:
                file_path = os.path.join(root, file)
                if not self._is_source_file(file_path):
                    continue

                try:
                    content = read_text_file(file_path, errors="replace")
                    dependencies = self.analyze_imports(file_path, content)
                    for dep in dependencies:
                        dep_path = self._resolve_header_path(
                            project_root, dep.from_module, file_path
                        )
                        if dep_path and dep_path != file_path:
                            graph.add_dependency(file_path, dep_path)

                    # Analyze macro calls
                    func_to_macros = self._extract_macro_calls(file_path)
                    for func, macros in func_to_macros.items():
                        for macro in macros:
                            if macro in macro_definitions:
                                dep_path = macro_definitions[macro]
                                if dep_path != file_path:
                                    graph.add_dependency(file_path, dep_path)
                except Exception:
                    continue

        return graph

    def _extract_macro_definitions(
        self, file_path: str, macro_definitions: Dict[str, str]
    ) -> None:
        """Extract macro definitions from a file using tree-sitter."""
        try:
            import tree_sitter
            import tree_sitter_c as tsc
            import tree_sitter_cpp as tscpp
        except ImportError:
            return

        ext = Path(file_path).suffix.lower()
        if ext in (".c", ".h"):
            language = tree_sitter.Language(tsc.language())
        elif ext in (".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".hh"):
            language = tree_sitter.Language(tscpp.language())
        else:
            return

        parser = tree_sitter.Parser(language)
        try:
            with open(file_path, "rb") as f:
                source_code = f.read()
        except Exception:
            return

        tree = parser.parse(source_code)

        def get_text(node: Any) -> str:
            return source_code[node.start_byte : node.end_byte].decode(
                "utf-8", errors="ignore"
            )

        def walk_tree(node: Any) -> None:
            if node.type in ("preproc_def", "preproc_function_def"):
                for child in node.children:
                    if child.type == "identifier":
                        macro_name = get_text(child)
                        if macro_name:
                            macro_definitions[macro_name] = file_path
                        break

            for child in node.children:
                walk_tree(child)

        walk_tree(tree.root_node)

    def _extract_macro_calls(self, file_path: str) -> Dict[str, List[str]]:
        """Extract macro calls from a file using tree-sitter."""
        try:
            import tree_sitter
            import tree_sitter_c as tsc
            import tree_sitter_cpp as tscpp
        except ImportError:
            return {}

        ext = Path(file_path).suffix.lower()
        if ext in (".c", ".h"):
            language = tree_sitter.Language(tsc.language())
        elif ext in (".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".hh"):
            language = tree_sitter.Language(tscpp.language())
        else:
            return {}

        parser = tree_sitter.Parser(language)
        try:
            with open(file_path, "rb") as f:
                source_code = f.read()
        except Exception:
            return {}

        tree = parser.parse(source_code)
        func_to_macros: Dict[str, List[str]] = {}

        def get_text(node: Any) -> str:
            return source_code[node.start_byte : node.end_byte].decode(
                "utf-8", errors="ignore"
            )

        def walk_tree(node: Any, current_func: Optional[str] = None) -> None:
            # Check for function definition
            if node.type == "function_definition":
                declarator = node.child_by_field_name("declarator")
                if declarator and declarator.type == "function_declarator":
                    name_node = declarator.child_by_field_name("declarator")
                    if name_node:
                        current_func = get_text(name_node)

            # Check for macro invocation
            if node.type == "call_expression" and current_func:
                func_node = node.child_by_field_name("function")
                if func_node:
                    func_name = get_text(func_node)
                    # Heuristic: Macros are usually uppercase
                    if func_name.isupper():
                        if current_func not in func_to_macros:
                            func_to_macros[current_func] = []
                        if func_name not in func_to_macros[current_func]:
                            func_to_macros[current_func].append(func_name)

            for child in node.children:
                walk_tree(child, current_func)

        walk_tree(tree.root_node)
        return func_to_macros

    def _resolve_header_path(
        self, project_root: str, header_name: str, from_file: str
    ) -> Optional[str]:
        """Resolve a header name to a file path."""
        # Try relative to current file
        base_dir = os.path.dirname(from_file)
        relative_path = os.path.join(base_dir, header_name)
        if os.path.exists(relative_path):
            return relative_path

        # Try in project root
        for root, dirs, files in os.walk(project_root):
            dirs[:] = filter_walk_dirs(dirs)
            if header_name in files:
                return os.path.join(root, header_name)

        return None

    def _is_source_file(self, file_path: str) -> bool:
        """Check if a file is a C source file."""
        return file_path.endswith((".c", ".h"))


class CppDependencyAnalyzer(CDependencyAnalyzer):
    """Analyzes C++ include dependencies (same as C)."""

    def _is_source_file(self, file_path: str) -> bool:
        """Check if a file is a C++ source file."""
        return file_path.endswith((".cpp", ".hpp", ".cc", ".cxx", ".hxx", ".h"))


class CLanguageSupport(BaseLanguageSupport):
    """C语言支持类。"""

    @property
    def language_name(self) -> str:
        return "c"

    @property
    def file_extensions(self) -> Set[str]:
        return {".c", ".h"}

    def create_symbol_extractor(self) -> Optional[SymbolExtractor]:
        try:
            return CSymbolExtractor()
        except RuntimeError:
            return None

    def create_dependency_analyzer(self) -> Optional[DependencyAnalyzer]:
        return CDependencyAnalyzer()


class CppLanguageSupport(BaseLanguageSupport):
    """C++语言支持类。"""

    @property
    def language_name(self) -> str:
        return "cpp"

    @property
    def file_extensions(self) -> Set[str]:
        return {".cpp", ".hpp", ".cc", ".cxx", ".hxx"}

    def create_symbol_extractor(self) -> Optional[SymbolExtractor]:
        try:
            return CppSymbolExtractor()
        except RuntimeError:
            return None

    def create_dependency_analyzer(self) -> Optional[DependencyAnalyzer]:
        return CppDependencyAnalyzer()
