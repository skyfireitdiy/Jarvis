import json
import os
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

    def __init__(self, cache_dir: Optional[str] = None):
        # A dictionary to store symbols by their name for quick lookups.
        # A symbol name can appear in multiple files, so it's a list.
        self.symbols_by_name: Dict[str, List[Symbol]] = {}
        # A dictionary to store symbols on a per-file basis.
        self.symbols_by_file: Dict[str, List[Symbol]] = {}
        # Track file modification times for cache invalidation
        self._file_mtimes: Dict[str, float] = {}
        # Cache directory for persistent storage
        self.cache_dir = cache_dir or ".jarvis/symbol_cache"
        # Load cached data if available
        self._load_from_cache()

    def _get_cache_file(self) -> str:
        """Get the cache file path."""
        return os.path.join(self.cache_dir, "symbol_table.json")

    def _load_from_cache(self):
        """Load symbol table data from cache file."""
        cache_file = self._get_cache_file()
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Convert JSON data back to Symbol objects
                self.symbols_by_name = self._deserialize_symbols(data.get('symbols_by_name', {}))
                self.symbols_by_file = self._deserialize_symbols(data.get('symbols_by_file', {}))
                # Load file modification times
                self._file_mtimes = data.get('file_mtimes', {})
            except Exception:
                # If cache loading fails, start with empty tables
                pass

    def _save_to_cache(self):
        """Save symbol table data to cache file."""
        try:
            # Ensure cache directory exists
            os.makedirs(self.cache_dir, exist_ok=True)
            cache_file = self._get_cache_file()
            
            # Update file modification times before saving
            self._update_file_mtimes()
            
            # Serialize symbols for JSON storage
            data = {
                'symbols_by_name': self._serialize_symbols(self.symbols_by_name),
                'symbols_by_file': self._serialize_symbols(self.symbols_by_file),
                'file_mtimes': self._file_mtimes
            }
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            # If cache saving fails, continue without caching
            pass

    def _serialize_symbols(self, symbol_dict: Dict[str, List[Symbol]]) -> Dict[str, List[dict]]:
        """Convert Symbol objects to serializable dictionaries."""
        serialized = {}
        for key, symbols in symbol_dict.items():
            serialized[key] = [self._symbol_to_dict(symbol) for symbol in symbols]
        return serialized

    def _deserialize_symbols(self, symbol_dict: Dict[str, List[dict]]) -> Dict[str, List[Symbol]]:
        """Convert serialized dictionaries back to Symbol objects."""
        deserialized = {}
        for key, symbol_data_list in symbol_dict.items():
            deserialized[key] = [self._dict_to_symbol(data) for data in symbol_data_list]
        return deserialized

    def _symbol_to_dict(self, symbol: Symbol) -> dict:
        """Convert a Symbol object to a dictionary."""
        return {
            'name': symbol.name,
            'kind': symbol.kind,
            'file_path': symbol.file_path,
            'line_start': symbol.line_start,
            'line_end': symbol.line_end,
            'signature': symbol.signature,
            'docstring': symbol.docstring,
            'parent': symbol.parent
        }

    def _dict_to_symbol(self, data: dict) -> Symbol:
        """Convert a dictionary back to a Symbol object."""
        return Symbol(
            name=data['name'],
            kind=data['kind'],
            file_path=data['file_path'],
            line_start=data['line_start'],
            line_end=data['line_end'],
            signature=data.get('signature'),
            docstring=data.get('docstring'),
            parent=data.get('parent')
        )

    def add_symbol(self, symbol: Symbol, save_to_cache: bool = False):
        """Adds a symbol to the table.
        
        Args:
            symbol: The symbol to add
            save_to_cache: If True, save to cache immediately. Default False for performance.
                          Use save_cache() to save all symbols at once after batch operations.
        """
        if symbol.name not in self.symbols_by_name:
            self.symbols_by_name[symbol.name] = []
        self.symbols_by_name[symbol.name].append(symbol)

        if symbol.file_path not in self.symbols_by_file:
            self.symbols_by_file[symbol.file_path] = []
        self.symbols_by_file[symbol.file_path].append(symbol)
        
        # Only save to cache if explicitly requested (for performance)
        if save_to_cache:
            self._save_to_cache()
    
    def save_cache(self):
        """Save the entire symbol table to cache. Call this after batch operations."""
        self._save_to_cache()

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
            
            # Remove file mtime tracking
            if file_path in self._file_mtimes:
                del self._file_mtimes[file_path]
            
            # Save to cache after clearing
            self._save_to_cache()
    
    def _update_file_mtimes(self):
        """Update modification times for all tracked files."""
        for file_path in list(self.symbols_by_file.keys()):
            if os.path.exists(file_path):
                try:
                    self._file_mtimes[file_path] = os.path.getmtime(file_path)
                except Exception:
                    # If we can't get mtime, remove from tracking
                    self._file_mtimes.pop(file_path, None)
    
    def is_file_stale(self, file_path: str) -> bool:
        """Check if a file has been modified since it was cached.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            True if file is newer than cache, False otherwise
        """
        if file_path not in self.symbols_by_file:
            # File not in cache, consider it stale (needs to be loaded)
            return True
        
        if file_path not in self._file_mtimes:
            # No mtime recorded, consider it stale
            return True
        
        if not os.path.exists(file_path):
            # File doesn't exist, not stale (will be handled by clear_file_symbols)
            return False
        
        try:
            current_mtime = os.path.getmtime(file_path)
            cached_mtime = self._file_mtimes.get(file_path, 0)
            return current_mtime > cached_mtime
        except Exception:
            # If we can't get mtime, assume not stale
            return False


class SymbolExtractor:
    """Extracts symbols from a source code file."""

    def extract_symbols(self, file_path: str, content: str) -> List[Symbol]:
        """
        Extracts symbols (functions, classes, variables, etc.) from the code.
        This method should be implemented by language-specific subclasses.
        """
        raise NotImplementedError("Subclasses must implement this method.")