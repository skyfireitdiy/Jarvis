"""Rust语言支持实现。"""

from typing import Optional, Set

from tree_sitter import Language, Node

from ..base_language import BaseLanguageSupport
from ..dependency_analyzer import DependencyAnalyzer
from ..symbol_extractor import Symbol, SymbolExtractor
from ..tree_sitter_extractor import TreeSitterExtractor


# --- Rust Symbol Query ---

RUST_SYMBOL_QUERY = """
(function_item
  name: (identifier) @function.name)

(struct_item
  name: (type_identifier) @struct.name)
  
(trait_item
  name: (type_identifier) @trait.name)

(impl_item
  type: (type_identifier) @impl.name)

(mod_item
  name: (identifier) @module.name)
"""

# --- Rust Language Setup ---

try:
    # TODO: This requires a mechanism to locate the compiled grammar file.
    # For now, we'll assume it's discoverable in the environment.
    RUST_LANGUAGE: Optional[Language] = Language('build/my-languages.so', 'rust')
except Exception:
    RUST_LANGUAGE = None


# --- Rust Symbol Extractor ---

class RustSymbolExtractor(TreeSitterExtractor):
    """Extracts symbols from Rust code using tree-sitter."""

    def __init__(self):
        if not RUST_LANGUAGE:
            raise RuntimeError("Rust tree-sitter grammar not available.")
        super().__init__(RUST_LANGUAGE, RUST_SYMBOL_QUERY)

    def _create_symbol_from_capture(self, node: Node, name: str, file_path: str) -> Optional[Symbol]:
        """Maps a tree-sitter capture to a Symbol object."""
        kind_map = {
            "function.name": "function",
            "struct.name": "struct",
            "trait.name": "trait",
            "impl.name": "impl",
            "module.name": "module",
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


class RustLanguageSupport(BaseLanguageSupport):
    """Rust语言支持类。"""

    @property
    def language_name(self) -> str:
        return 'rust'

    @property
    def file_extensions(self) -> Set[str]:
        return {'.rs'}

    def create_symbol_extractor(self) -> Optional[SymbolExtractor]:
        try:
            return RustSymbolExtractor()
        except RuntimeError:
            return None

    def create_dependency_analyzer(self) -> Optional[DependencyAnalyzer]:
        # Rust依赖分析暂未实现
        return None

