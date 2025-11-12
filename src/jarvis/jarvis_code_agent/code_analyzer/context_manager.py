import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

from .dependency_analyzer import DependencyGraph
from .file_ignore import filter_walk_dirs
from .symbol_extractor import Symbol, SymbolTable
from .language_support import detect_language, get_symbol_extractor, get_dependency_analyzer


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
    context_summary: str = ""


@dataclass
class Reference:
    """Represents a reference to a symbol."""
    symbol: Symbol
    file_path: str
    line: int
    column: Optional[int] = None


class ContextManager:
    """Manages the symbol table and dependency graph to provide code context."""

    def __init__(self, project_root: str):
        self.project_root = project_root
        # Create cache directory path relative to project root
        cache_dir = os.path.join(project_root, ".jarvis", "symbol_cache")
        self.symbol_table = SymbolTable(cache_dir)
        self.dependency_graph = DependencyGraph()
        self._file_cache: dict[str, str] = {}  # Cache file contents

    def get_edit_context(self, file_path: str, line_start: int, line_end: int) -> EditContext:
        """
        Gets contextual information for a given edit location.
        
        Returns:
            EditContext with information about the current scope, used symbols,
            imported symbols, and relevant files.
        """
        # Get file content
        content = self._get_file_content(file_path)
        if not content:
            return EditContext(file_path=file_path, line_start=line_start, line_end=line_end)
        
        # Find current scope (function or class)
        current_scope = self._find_current_scope(file_path, line_start)
        
        # Find symbols used in the edit region
        used_symbols = self._find_used_symbols(file_path, content, line_start, line_end)
        
        # Find imported symbols
        imported_symbols = self._find_imported_symbols(file_path)
        
        # Find relevant files (dependencies and dependents)
        relevant_files = self._find_relevant_files(file_path)
        
        # Build context summary
        context_summary = self._build_context_summary(
            current_scope, used_symbols, imported_symbols, relevant_files
        )
        
        return EditContext(
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            current_scope=current_scope,
            used_symbols=used_symbols,
            imported_symbols=imported_symbols,
            relevant_files=relevant_files,
            context_summary=context_summary,
        )

    def find_references(self, symbol_name: str, file_path: Optional[str] = None) -> List[Reference]:
        """
        Finds all references to a symbol.
        
        Args:
            symbol_name: Name of the symbol to find references for
            file_path: Optional file path to limit search scope
            
        Returns:
            List of Reference objects pointing to where the symbol is used
        """
        references: List[Reference] = []
        
        # Find symbol definitions
        symbols = self.symbol_table.find_symbol(symbol_name, file_path)
        if not symbols:
            return references
        
        # Search in files that might reference this symbol
        search_files: Set[str] = set()
        
        # Add files that depend on the symbol's file
        for symbol in symbols:
            search_files.add(symbol.file_path)
            dependents = self.dependency_graph.get_dependents(symbol.file_path)
            search_files.update(dependents)
        
        # If file_path is specified, limit search to that file
        if file_path:
            search_files = {f for f in search_files if f == file_path}
        
        # Search for references in each file
        for file_path_to_search in search_files:
            content = self._get_file_content(file_path_to_search)
            if not content:
                continue
            
            # Simple pattern matching for symbol references
            # This is a basic implementation; could be enhanced with AST analysis
            pattern = r'\b' + re.escape(symbol_name) + r'\b'
            for match in re.finditer(pattern, content):
                line_num = content[:match.start()].count('\n') + 1
                col_num = match.start() - content.rfind('\n', 0, match.start()) - 1
                
                # Check if this is not a definition (basic check)
                line_start = content.rfind('\n', 0, match.start()) + 1
                line_end = content.find('\n', match.end())
                if line_end == -1:
                    line_end = len(content)
                line_content = content[line_start:line_end]
                
                # Skip if it's a definition (contains 'def', 'class', etc.)
                if any(keyword in line_content for keyword in ['def ', 'class ', 'import ', 'from ']):
                    continue
                
                # Use the first matching symbol definition
                if symbols:
                    references.append(Reference(
                        symbol=symbols[0],
                        file_path=file_path_to_search,
                        line=line_num,
                        column=col_num,
                    ))
        
        return references

    def find_definition(self, symbol_name: str, file_path: Optional[str] = None) -> Optional[Symbol]:
        """
        Finds the definition of a symbol.
        
        Args:
            symbol_name: Name of the symbol to find
            file_path: Optional file path to limit search scope
            
        Returns:
            Symbol object if found, None otherwise
        """
        symbols = self.symbol_table.find_symbol(symbol_name, file_path)
        if symbols:
            # Return the first definition (could be enhanced to find the most relevant one)
            return symbols[0]
        return None

    def update_context_for_file(self, file_path: str, content: str):
        """
        Updates the symbol table and dependency graph for a single file.
        """
        # 1. Clear old data for the file
        self.symbol_table.clear_file_symbols(file_path)
        self.dependency_graph.clear_file_dependencies(file_path)

        # 2. Update file cache
        self._file_cache[file_path] = content

        # 3. Detect language and get the appropriate extractor
        language = detect_language(file_path)
        if not language:
            return

        # 4. Extract symbols
        extractor = get_symbol_extractor(language)
        if extractor:
            symbols = extractor.extract_symbols(file_path, content)
            for symbol in symbols:
                self.symbol_table.add_symbol(symbol)

        # 5. Analyze dependencies
        analyzer = get_dependency_analyzer(language)
        if analyzer:
            dependencies = analyzer.analyze_imports(file_path, content)
            for dep in dependencies:
                # Resolve dependency path
                dep_path = self._resolve_dependency_path(file_path, dep.from_module)
                if dep_path:
                    self.dependency_graph.add_dependency(file_path, dep_path)
        
        # 6. Save updated symbols to cache
        self.symbol_table.save_cache()

    def _get_file_content(self, file_path: str) -> Optional[str]:
        """Get file content, using cache if available."""
        if file_path in self._file_cache:
            return self._file_cache[file_path]
        
        if not os.path.exists(file_path):
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            self._file_cache[file_path] = content
            return content
        except Exception:
            return None

    def _find_current_scope(self, file_path: str, line_num: int) -> Optional[Symbol]:
        """Find the function or class that contains the given line."""
        symbols = self.symbol_table.get_file_symbols(file_path)
        
        # Find the innermost scope containing the line
        current_scope = None
        for symbol in symbols:
            if symbol.kind in ('function', 'class', 'method'):
                if symbol.line_start <= line_num <= symbol.line_end:
                    # Choose the most nested scope
                    if current_scope is None or (
                        symbol.line_start >= current_scope.line_start and
                        symbol.line_end <= current_scope.line_end
                    ):
                        current_scope = symbol
        
        return current_scope

    def _find_used_symbols(self, file_path: str, content: str, line_start: int, line_end: int) -> List[Symbol]:
        """Find symbols used in the specified line range."""
        # Extract the code in the range
        lines = content.split('\n')
        region_content = '\n'.join(lines[line_start-1:line_end])
        
        used_symbols: List[Symbol] = []
        all_symbols = self.symbol_table.get_file_symbols(file_path)
        
        # Simple pattern matching to find symbol usage
        for symbol in all_symbols:
            if symbol.kind == 'import':
                continue
            
            pattern = r'\b' + re.escape(symbol.name) + r'\b'
            if re.search(pattern, region_content):
                used_symbols.append(symbol)
        
        return used_symbols

    def _find_imported_symbols(self, file_path: str) -> List[Symbol]:
        """Find all imported symbols in a file."""
        symbols = self.symbol_table.get_file_symbols(file_path)
        return [s for s in symbols if s.kind == 'import']

    def _find_relevant_files(self, file_path: str) -> List[str]:
        """Find relevant files (dependencies and dependents)."""
        relevant = set()
        
        # Add dependencies
        deps = self.dependency_graph.get_dependencies(file_path)
        relevant.update(deps)
        
        # Add dependents
        dependents = self.dependency_graph.get_dependents(file_path)
        relevant.update(dependents)
        
        return list(relevant)

    def _resolve_dependency_path(self, file_path: str, module_name: str) -> Optional[str]:
        """Resolve a module name to a file path."""
        # Handle relative imports
        if module_name.startswith('.'):
            # Relative import
            base_dir = os.path.dirname(file_path)
            parts = module_name.split('.')
            depth = len([p for p in parts if p == ''])
            module_parts = [p for p in parts if p]
            
            # Navigate up directories
            current_dir = base_dir
            for _ in range(depth - 1):
                current_dir = os.path.dirname(current_dir)
            
            # Try to find the module file
            if module_parts:
                module_path = os.path.join(current_dir, *module_parts)
            else:
                module_path = current_dir
            
            # Try common extensions
            for ext in ['.py', '.rs', '.go', '.js', '.ts']:
                full_path = module_path + ext
                if os.path.exists(full_path):
                    return full_path
                
                # Try __init__.py for Python packages
                if ext == '.py':
                    init_path = os.path.join(module_path, '__init__.py')
                    if os.path.exists(init_path):
                        return init_path
        else:
            # Absolute import - search in project
            parts = module_name.split('.')
            for root, dirs, files in os.walk(self.project_root):
                # Skip hidden directories and common ignore patterns
                dirs[:] = filter_walk_dirs(dirs)
                
                if parts[0] in dirs or f"{parts[0]}.py" in files:
                    module_path = os.path.join(root, *parts)
                    
                    # Try common extensions
                    for ext in ['.py', '.rs', '.go', '.js', '.ts']:
                        full_path = module_path + ext
                        if os.path.exists(full_path):
                            return full_path
                        
                        # Try __init__.py for Python packages
                        if ext == '.py':
                            init_path = os.path.join(module_path, '__init__.py')
                            if os.path.exists(init_path):
                                return init_path
        
        return None

    def _build_context_summary(
        self,
        current_scope: Optional[Symbol],
        used_symbols: List[Symbol],
        imported_symbols: List[Symbol],
        relevant_files: List[str],
    ) -> str:
        """Build a human-readable context summary."""
        parts = []
        
        if current_scope:
            parts.append(f"Current scope: {current_scope.kind} {current_scope.name}")
            if current_scope.signature:
                parts.append(f"  Signature: {current_scope.signature}")
        
        if used_symbols:
            symbol_names = [s.name for s in used_symbols[:5]]
            parts.append(f"Used symbols: {', '.join(symbol_names)}")
            if len(used_symbols) > 5:
                parts.append(f"  ... and {len(used_symbols) - 5} more")
        
        if imported_symbols:
            import_names = [s.name for s in imported_symbols[:5]]
            parts.append(f"Imported symbols: {', '.join(import_names)}")
            if len(imported_symbols) > 5:
                parts.append(f"  ... and {len(imported_symbols) - 5} more")
        
        if relevant_files:
            parts.append(f"Relevant files: {len(relevant_files)} files")
            for f in relevant_files[:3]:
                parts.append(f"  - {os.path.relpath(f, self.project_root)}")
            if len(relevant_files) > 3:
                parts.append(f"  ... and {len(relevant_files) - 3} more")
        
        return '\n'.join(parts) if parts else "No context available"