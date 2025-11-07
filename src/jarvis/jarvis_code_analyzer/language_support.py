import os
import ast
from typing import Dict, List, Optional, Type, Union

from .symbol_extractor import Symbol, SymbolExtractor


# --- Language Detection ---

def detect_language(file_path: str) -> Optional[str]:
    """Detects the programming language based on the file extension."""
    ext_map = {
        '.py': 'python',
        '.rs': 'rust',
        '.go': 'go',
        '.c': 'c',
        '.h': 'c',
        '.cpp': 'cpp',
        '.hpp': 'cpp',
    }
    _, ext = os.path.splitext(file_path)
    return ext_map.get(ext)


# --- Python Symbol Extraction ---

class PythonSymbolExtractor(SymbolExtractor):
    """Extracts symbols from Python code using the AST module."""

    def extract_symbols(self, file_path: str, content: str) -> List[Symbol]:
        symbols: List[Symbol] = []
        try:
            tree = ast.parse(content, filename=file_path)
            self._traverse_node(tree, file_path, symbols, parent_name=None)
        except SyntaxError as e:
            print(f"Error parsing Python file {file_path}: {e}")
        return symbols

    def _traverse_node(self, node: ast.AST, file_path: str, symbols: List[Symbol], parent_name: Optional[str]):
        if isinstance(node, ast.FunctionDef):
            symbol = self._create_symbol_from_func(node, file_path, parent_name)
            symbols.append(symbol)
            parent_name = node.name
        elif isinstance(node, ast.AsyncFunctionDef):
            symbol = self._create_symbol_from_func(node, file_path, parent_name, is_async=True)
            symbols.append(symbol)
            parent_name = node.name
        elif isinstance(node, ast.ClassDef):
            symbol = self._create_symbol_from_class(node, file_path, parent_name)
            symbols.append(symbol)
            parent_name = node.name
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
             symbols.extend(self._create_symbols_from_import(node, file_path, parent_name))


        for child in ast.iter_child_nodes(node):
            self._traverse_node(child, file_path, symbols, parent_name=parent_name)

    def _create_symbol_from_func(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef], file_path: str, parent: Optional[str], is_async: bool = False) -> Symbol:
        signature = f"{'async ' if is_async else ''}def {node.name}(...)"
        return Symbol(
            name=node.name,
            kind='function',
            file_path=file_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            signature=signature,
            docstring=ast.get_docstring(node),
            parent=parent,
        )

    def _create_symbol_from_class(self, node: ast.ClassDef, file_path: str, parent: Optional[str]) -> Symbol:
        return Symbol(
            name=node.name,
            kind='class',
            file_path=file_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            docstring=ast.get_docstring(node),
            parent=parent,
        )
    
    def _create_symbols_from_import(self, node: Union[ast.Import, ast.ImportFrom], file_path: str, parent: Optional[str]) -> List[Symbol]:
        symbols = []
        for alias in node.names:
            symbols.append(Symbol(
                name=alias.asname or alias.name,
                kind='import',
                file_path=file_path,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                parent=parent,
            ))
        return symbols


# --- Extensibility and Factory ---

# A registry to hold language-specific extractor classes
# --- Extensibility and Factory ---

# A registry to hold language-specific extractor classes
EXTRACTOR_REGISTRY: Dict[str, Type[SymbolExtractor]] = {
    'python': PythonSymbolExtractor,
}

# Attempt to register tree-sitter based extractors
try:
    from .rust_extractor import RustSymbolExtractor
    EXTRACTOR_REGISTRY['rust'] = RustSymbolExtractor
except (ImportError, RuntimeError) as e:
    print(f"Could not register RustSymbolExtractor: {e}")

try:
    from .go_extractor import GoSymbolExtractor
    EXTRACTOR_REGISTRY['go'] = GoSymbolExtractor
except (ImportError, RuntimeError) as e:
    print(f"Could not register GoSymbolExtractor: {e}")

try:
    from .c_cpp_extractor import CppSymbolExtractor, CSymbolExtractor
    EXTRACTOR_REGISTRY['c'] = CSymbolExtractor
    EXTRACTOR_REGISTRY['cpp'] = CppSymbolExtractor
except (ImportError, RuntimeError) as e:
    print(f"Could not register CSymbolExtractor or CppSymbolExtractor: {e}")


def get_symbol_extractor(language: str) -> Optional[SymbolExtractor]:
    """
    Factory function to get a symbol extractor for a given language.
    Returns an instance of the appropriate extractor class, or None if not supported.
    """
    extractor_class = EXTRACTOR_REGISTRY.get(language)
    if extractor_class:
        return extractor_class()
    return None