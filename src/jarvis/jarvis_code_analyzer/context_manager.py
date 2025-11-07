from dataclasses import dataclass, field
from typing import List, Optional

from .dependency_analyzer import DependencyGraph
from .symbol_extractor import Symbol, SymbolTable
from .language_support import detect_language, get_symbol_extractor


@dataclass
class EditContext:
    """Provides contextual information for a specific code location."""
    file_path: str
    line_start: int
    line_end: int
    current_scope: Optional[Symbol] = None
    used_symbols: List[Symbol] = field(default_factory=list)
    imported_symbols: List[Symbol] = field(default_factory=list)
    relevant_files: List[str] = field(default_factory=list)


@dataclass
class Reference:
    """Represents a reference to a symbol."""
    symbol: Symbol
    file_path: str
    line: int


class ContextManager:
    """Manages the symbol table and dependency graph to provide code context."""

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.symbol_table = SymbolTable()
        self.dependency_graph = DependencyGraph()

    def get_edit_context(self, file_path: str, line_start: int, line_end: int) -> EditContext:
        """
        Gets contextual information for a given edit location.
        """
        raise NotImplementedError("This method needs to be implemented.")

    def find_references(self, symbol_name: str, file_path: str) -> List[Reference]:
        """
        Finds all references to a symbol.
        """
        raise NotImplementedError("This method needs to be implemented.")

    def find_definition(self, symbol_name: str, file_path: str) -> Optional[Symbol]:
        """
        Finds the definition of a symbol.
        """
        raise NotImplementedError("This method needs to be implemented.")

    def update_context_for_file(self, file_path: str, content: str):
        """
        Updates the symbol table and dependency graph for a single file.
        """
        # 1. Clear old data for the file
        self.symbol_table.clear_file_symbols(file_path)
        self.dependency_graph.clear_file_dependencies(file_path)

        # 2. Detect language and get the appropriate extractor
        language = detect_language(file_path)
        if not language:
            print(f"Language not supported for file: {file_path}")
            return

        extractor = get_symbol_extractor(language)
        if not extractor:
            print(f"No symbol extractor available for {language}")
            return

        # 3. Extract new symbols and update the symbol table
        symbols = extractor.extract_symbols(file_path, content)
        for symbol in symbols:
            self.symbol_table.add_symbol(symbol)

        # 4. Analyze dependencies (to be implemented)
        # analyzer = get_dependency_analyzer(language)
        # if analyzer:
        #     dependencies = analyzer.analyze_imports(file_path, content)
        #     for dep in dependencies:
        #         # Logic to resolve dependency path and add to graph
        #         pass
        
        print(f"Context updated for {file_path} ({len(symbols)} symbols found).")