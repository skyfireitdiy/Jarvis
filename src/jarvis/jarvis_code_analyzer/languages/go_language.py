"""Go语言支持实现。"""

from typing import Optional, Set

from tree_sitter import Language, Node

from ..base_language import BaseLanguageSupport
from ..dependency_analyzer import DependencyAnalyzer
from ..symbol_extractor import Symbol, SymbolExtractor
from ..tree_sitter_extractor import TreeSitterExtractor


# --- Go Symbol Query ---

GO_SYMBOL_QUERY = """
(function_declaration
  name: (identifier) @function.name)

(method_declaration
  name: (field_identifier) @method.name)

(type_declaration
  (type_spec
    name: (type_identifier) @type.name))

(interface_declaration
  name: (type_identifier) @interface.name)
"""

# --- Go Language Setup ---

try:
    # Assumes the compiled grammar is located at 'build/my-languages.so'
    GO_LANGUAGE: Optional[Language] = Language('build/my-languages.so', 'go')
except Exception:
    GO_LANGUAGE = None


# --- Go Symbol Extractor ---

class GoSymbolExtractor(TreeSitterExtractor):
    """Extracts symbols from Go code using tree-sitter."""

    def __init__(self):
        if not GO_LANGUAGE:
            raise RuntimeError("Go tree-sitter grammar not available.")
        super().__init__(GO_LANGUAGE, GO_SYMBOL_QUERY)

    def _create_symbol_from_capture(self, node: Node, name: str, file_path: str) -> Optional[Symbol]:
        """Maps a tree-sitter capture to a Symbol object."""
        kind_map = {
            "function.name": "function",
            "method.name": "method",
            "type.name": "type",
            "interface.name": "interface",
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


class GoLanguageSupport(BaseLanguageSupport):
    """Go语言支持类。"""

    @property
    def language_name(self) -> str:
        return 'go'

    @property
    def file_extensions(self) -> Set[str]:
        return {'.go'}

    def create_symbol_extractor(self) -> Optional[SymbolExtractor]:
        try:
            return GoSymbolExtractor()
        except RuntimeError:
            return None

    def create_dependency_analyzer(self) -> Optional[DependencyAnalyzer]:
        # Go依赖分析暂未实现
        return None

