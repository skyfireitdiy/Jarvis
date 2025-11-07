"""Python语言支持实现。"""

import ast
from typing import List, Optional, Set, Union

from ..base_language import BaseLanguageSupport
from ..dependency_analyzer import DependencyAnalyzer, PythonDependencyAnalyzer
from ..symbol_extractor import Symbol, SymbolExtractor


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


class PythonLanguageSupport(BaseLanguageSupport):
    """Python语言支持类。"""

    @property
    def language_name(self) -> str:
        return 'python'

    @property
    def file_extensions(self) -> Set[str]:
        return {'.py', '.pyw', '.pyi'}

    def create_symbol_extractor(self) -> Optional[SymbolExtractor]:
        return PythonSymbolExtractor()

    def create_dependency_analyzer(self) -> Optional[DependencyAnalyzer]:
        return PythonDependencyAnalyzer()

