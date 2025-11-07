"""C/C++语言支持实现。"""

from typing import Optional, Set

from tree_sitter import Language, Node

from ..base_language import BaseLanguageSupport
from ..dependency_analyzer import DependencyAnalyzer
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
        # C依赖分析暂未实现
        return None


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
        # C++依赖分析暂未实现
        return None

