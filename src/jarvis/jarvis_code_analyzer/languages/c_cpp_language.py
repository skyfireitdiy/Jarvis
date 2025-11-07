"""C/C++语言支持实现。"""

import os
import re
from typing import List, Optional, Set

from tree_sitter import Language, Node

from ..base_language import BaseLanguageSupport
from ..dependency_analyzer import Dependency, DependencyAnalyzer, DependencyGraph
from ..symbol_extractor import Symbol, SymbolExtractor
from ..tree_sitter_extractor import TreeSitterExtractor


# --- C/C++ Symbol Query ---

C_CPP_SYMBOL_QUERY = """
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
"""

# --- C/C++ Language Setup ---

try:
    C_LANGUAGE: Optional[Language] = Language('build/my-languages.so', 'c')
except Exception:
    C_LANGUAGE = None

try:
    CPP_LANGUAGE: Optional[Language] = Language('build/my-languages.so', 'cpp')
except Exception:
    CPP_LANGUAGE = None


# --- C/C++ Symbol Extractors ---

class CSymbolExtractor(TreeSitterExtractor):
    """Extracts symbols from C code using tree-sitter."""

    def __init__(self):
        if not C_LANGUAGE:
            raise RuntimeError("C tree-sitter grammar not available.")
        super().__init__(C_LANGUAGE, C_CPP_SYMBOL_QUERY)

    def _create_symbol_from_capture(self, node: Node, name: str, file_path: str) -> Optional[Symbol]:
        kind_map = {
            "function.name": "function",
            "struct.name": "struct",
            "union.name": "union",
            "enum.name": "enum",
        }
        symbol_kind = kind_map.get(name)
        if not symbol_kind:
            return None

        return Symbol(
            name=node.text.decode('utf8'),
            kind=symbol_kind,
            file_path=file_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
        )


class CppSymbolExtractor(TreeSitterExtractor):
    """Extracts symbols from C++ code using tree-sitter."""

    def __init__(self):
        if not CPP_LANGUAGE:
            raise RuntimeError("C++ tree-sitter grammar not available.")
        super().__init__(CPP_LANGUAGE, C_CPP_SYMBOL_QUERY)

    def _create_symbol_from_capture(self, node: Node, name: str, file_path: str) -> Optional[Symbol]:
        kind_map = {
            "function.name": "function",
            "struct.name": "struct",
            "class.name": "class",
            "union.name": "union",
            "enum.name": "enum",
        }
        symbol_kind = kind_map.get(name)
        if not symbol_kind:
            return None

        return Symbol(
            name=node.text.decode('utf8'),
            kind=symbol_kind,
            file_path=file_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
        )


# --- C/C++ Dependency Analyzers ---

class CDependencyAnalyzer(DependencyAnalyzer):
    """Analyzes C include dependencies."""

    def analyze_imports(self, file_path: str, content: str) -> List[Dependency]:
        """Analyzes C #include statements."""
        dependencies: List[Dependency] = []
        
        # Match #include directives
        # Format: #include <header.h> or #include "header.h"
        include_pattern = re.compile(r'#include\s+[<"]([^>"]+)[>"]')
        
        for line_num, line in enumerate(content.split('\n'), start=1):
            match = include_pattern.search(line)
            if match:
                header = match.group(1)
                dependencies.append(Dependency(
                    from_module=header,
                    imported_symbol=None,
                    file_path=file_path,
                    line=line_num,
                ))
        
        return dependencies

    def build_dependency_graph(self, project_root: str) -> DependencyGraph:
        """Builds a dependency graph for a C project."""
        graph = DependencyGraph()
        extensions = {'.c', '.h'}
        
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for file in files:
                if not any(file.endswith(ext) for ext in extensions):
                    continue
                
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                    
                    dependencies = self.analyze_imports(file_path, content)
                    for dep in dependencies:
                        dep_path = self._resolve_header_path(project_root, dep.from_module, file_path)
                        if dep_path and dep_path != file_path:
                            graph.add_dependency(file_path, dep_path)
                except Exception:
                    continue
        
        return graph

    def _resolve_header_path(self, project_root: str, header_name: str, from_file: str) -> Optional[str]:
        """Resolve a header name to a file path."""
        # Try relative to current file
        base_dir = os.path.dirname(from_file)
        relative_path = os.path.join(base_dir, header_name)
        if os.path.exists(relative_path):
            return relative_path
        
        # Try in project root
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            if header_name in files:
                return os.path.join(root, header_name)
        
        return None

    def _is_source_file(self, file_path: str) -> bool:
        """Check if a file is a C source file."""
        return file_path.endswith(('.c', '.h'))


class CppDependencyAnalyzer(CDependencyAnalyzer):
    """Analyzes C++ include dependencies (same as C)."""

    def _is_source_file(self, file_path: str) -> bool:
        """Check if a file is a C++ source file."""
        return file_path.endswith(('.cpp', '.hpp', '.cc', '.cxx', '.hxx', '.h'))


class CLanguageSupport(BaseLanguageSupport):
    """C语言支持类。"""

    @property
    def language_name(self) -> str:
        return 'c'

    @property
    def file_extensions(self) -> Set[str]:
        return {'.c', '.h'}

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
        return 'cpp'

    @property
    def file_extensions(self) -> Set[str]:
        return {'.cpp', '.hpp', '.cc', '.cxx', '.hxx'}

    def create_symbol_extractor(self) -> Optional[SymbolExtractor]:
        try:
            return CppSymbolExtractor()
        except RuntimeError:
            return None

    def create_dependency_analyzer(self) -> Optional[DependencyAnalyzer]:
        return CppDependencyAnalyzer()

