from dataclasses import dataclass

from typing import Dict, List, Optional


@dataclass
class Symbol:
    """Represents a single symbol in the code."""
    name: str
    kind: str  # e.g., 'function', 'class', 'variable', 'import'
    file_path: str
    line_start: int
    line_end: int
    signature: Optional[str] = None
    docstring: Optional[str] = None
    # Add more fields as needed, e.g., parent scope
    parent: Optional[str] = None


class SymbolTable:
    """Stores and provides access to symbols across a project."""

    def __init__(self):
        # A dictionary to store symbols by their name for quick lookups.
        # A symbol name can appear in multiple files, so it's a list.
        self.symbols_by_name: Dict[str, List[Symbol]] = {}
        # A dictionary to store symbols on a per-file basis.
        self.symbols_by_file: Dict[str, List[Symbol]] = {}

    def add_symbol(self, symbol: Symbol):
        """Adds a symbol to the table."""
        if symbol.name not in self.symbols_by_name:
            self.symbols_by_name[symbol.name] = []
        self.symbols_by_name[symbol.name].append(symbol)

        if symbol.file_path not in self.symbols_by_file:
            self.symbols_by_file[symbol.file_path] = []
        self.symbols_by_file[symbol.file_path].append(symbol)

    def find_symbol(self, name: str, file_path: Optional[str] = None) -> List[Symbol]:
        """
        Finds a symbol by name.
        If file_path is provided, the search is limited to that file.
        """
        if file_path:
            return [
                s for s in self.get_file_symbols(file_path) if s.name == name
            ]
        return self.symbols_by_name.get(name, [])

    def get_file_symbols(self, file_path: str) -> List[Symbol]:
        """Gets all symbols within a specific file."""
        return self.symbols_by_file.get(file_path, [])

    def clear_file_symbols(self, file_path: str):
        """Removes all symbols associated with a specific file."""
        if file_path in self.symbols_by_file:
            symbols_to_remove = self.symbols_by_file.pop(file_path)
            for symbol in symbols_to_remove:
                if symbol.name in self.symbols_by_name:
                    self.symbols_by_name[symbol.name] = [
                        s for s in self.symbols_by_name[symbol.name]
                        if s.file_path != file_path
                    ]
                    if not self.symbols_by_name[symbol.name]:
                        del self.symbols_by_name[symbol.name]


class SymbolExtractor:
    """Extracts symbols from a source code file."""

    def extract_symbols(self, file_path: str, content: str) -> List[Symbol]:
        """
        Extracts symbols (functions, classes, variables, etc.) from the code.
        This method should be implemented by language-specific subclasses.
        """
        raise NotImplementedError("Subclasses must implement this method.")