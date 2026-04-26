import os
import re
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Set
from typing import Tuple

from .dependency_analyzer import DependencyGraph
from .file_ignore import filter_walk_dirs
from .language_support import detect_language
from .language_support import get_dependency_analyzer
from .language_support import get_symbol_extractor
from .symbol_extractor import Symbol
from .symbol_extractor import SymbolTable


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

    def get_edit_context(
        self, file_path: str, line_start: int, line_end: int
    ) -> EditContext:
        """
        Gets contextual information for a given edit location.

        Returns:
            EditContext with information about the current scope, used symbols,
            imported symbols, and relevant files.
        """
        # Get file content
        content = self._get_file_content(file_path)
        if not content:
            return EditContext(
                file_path=file_path, line_start=line_start, line_end=line_end
            )

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

    def find_references(
        self, symbol_name: str, file_path: Optional[str] = None
    ) -> List[Reference]:
        """
        Finds all references to a symbol.

        Args:
            symbol_name: Name of the symbol to find references for
            file_path: Optional file path to limit search scope

        Returns:
            List of Reference objects pointing to where the symbol is used
        """
        references: List[Reference] = []

        # Check if file is stale and update if needed
        if file_path and self.symbol_table.is_file_stale(file_path):
            self._refresh_file_symbols(file_path)

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
            # Check if file is stale and update if needed
            if self.symbol_table.is_file_stale(file_path_to_search):
                self._refresh_file_symbols(file_path_to_search)

            content = self._get_file_content(file_path_to_search)
            if not content:
                continue

            # Simple pattern matching for symbol references
            # This is a basic implementation; could be enhanced with AST analysis
            pattern = r"\b" + re.escape(symbol_name) + r"\b"
            for match in re.finditer(pattern, content):
                line_num = content[: match.start()].count("\n") + 1
                col_num = match.start() - content.rfind("\n", 0, match.start()) - 1

                # Check if this is not a definition (basic check)
                line_start = content.rfind("\n", 0, match.start()) + 1
                line_end = content.find("\n", match.end())
                if line_end == -1:
                    line_end = len(content)
                line_content = content[line_start:line_end]

                # Skip if it's a definition (contains 'def', 'class', etc.)
                if any(
                    keyword in line_content
                    for keyword in ["def ", "class ", "import ", "from "]
                ):
                    continue

                # Use the first matching symbol definition
                if symbols:
                    references.append(
                        Reference(
                            symbol=symbols[0],
                            file_path=file_path_to_search,
                            line=line_num,
                            column=col_num,
                        )
                    )

        return references

    def find_definition(
        self, symbol_name: str, file_path: Optional[str] = None
    ) -> Optional[Symbol]:
        """
        Finds the definition of a symbol.

        Args:
            symbol_name: Name of the symbol to find
            file_path: Optional file path to limit search scope

        Returns:
            Symbol object if found, None otherwise
        """
        # Check if file is stale and update if needed
        if file_path and self.symbol_table.is_file_stale(file_path):
            self._refresh_file_symbols(file_path)

        symbols = self.symbol_table.find_symbol(symbol_name, file_path)
        if symbols:
            # Return the first definition (could be enhanced to find the most relevant one)
            return symbols[0]
        return None

    def update_context_for_file(self, file_path: str, content: str) -> None:
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

            # Update file modification time after extracting symbols
            if os.path.exists(file_path):
                try:
                    self.symbol_table._file_mtimes[file_path] = os.path.getmtime(
                        file_path
                    )
                except Exception:
                    pass

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

    def _refresh_file_symbols(self, file_path: str) -> None:
        """Refresh symbols for a file that has been modified externally.

        This method is called when a file is detected to be stale (modified
        outside of Jarvis's control).
        """
        if not os.path.exists(file_path):
            return

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            self.update_context_for_file(file_path, content)
        except Exception:
            # If we can't read the file, skip refresh
            pass

    def _get_file_content(self, file_path: str) -> Optional[str]:
        """Get file content, using cache if available."""
        if file_path in self._file_cache:
            return self._file_cache[file_path]

        if not os.path.exists(file_path):
            return None

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            self._file_cache[file_path] = content
            return content
        except Exception:
            return None

    def _find_current_scope(self, file_path: str, line_num: int) -> Optional[Symbol]:
        """Find the function or class that contains the given line."""
        # Check if file is stale and update if needed
        if self.symbol_table.is_file_stale(file_path):
            self._refresh_file_symbols(file_path)
        symbols = self.symbol_table.get_file_symbols(file_path)

        # Find the innermost scope containing the line
        current_scope = None
        for symbol in symbols:
            if symbol.kind in ("function", "class", "method"):
                if symbol.line_start <= line_num <= symbol.line_end:
                    # Choose the most nested scope
                    if current_scope is None or (
                        symbol.line_start >= current_scope.line_start
                        and symbol.line_end <= current_scope.line_end
                    ):
                        current_scope = symbol

        return current_scope

    def _find_used_symbols(
        self, file_path: str, content: str, line_start: int, line_end: int
    ) -> List[Symbol]:
        """Find symbols used in the specified line range.

        改进版本：
        1. 区分定义和调用：检查符号是否在当前行范围内定义
        2. 获取定义位置：使用 tree-sitter 符号提取器
        3. 为每个使用的符号添加定义位置信息
        """
        # Check if file is stale and update if needed
        if self.symbol_table.is_file_stale(file_path):
            self._refresh_file_symbols(file_path)

        # Extract the code in the range
        lines = content.split("\n")
        region_content = "\n".join(lines[line_start - 1 : line_end])

        used_symbols: List[Symbol] = []
        all_symbols = self.symbol_table.get_file_symbols(file_path)

        # 尝试获取 tree-sitter 提取器
        treesitter_extractor = None
        try:
            from jarvis.jarvis_code_agent.code_analyzer.language_support import (
                detect_language,
            )
            from jarvis.jarvis_code_agent.code_analyzer.language_support import (
                get_symbol_extractor,
            )

            language = detect_language(file_path)
            if language:
                treesitter_extractor = get_symbol_extractor(language)
        except Exception:
            pass

        # 用于跟踪已处理的符号，避免重复
        processed_symbols: Dict[
            str, Tuple[Symbol, bool, Optional[Symbol]]
        ] = {}  # {symbol_name: (symbol, is_definition, definition_location)}

        # Simple pattern matching to find symbol usage
        for symbol in all_symbols:
            if symbol.kind == "import":
                continue

            pattern = r"\b" + re.escape(symbol.name) + r"\b"
            matches = list(re.finditer(pattern, region_content))
            if not matches:
                continue

            # 检查符号是否在当前行范围内定义
            is_definition_in_range = (
                symbol.file_path == file_path
                and symbol.line_start >= line_start
                and symbol.line_start <= line_end
            )

            # 检查是否有调用（不在定义行的使用）
            has_calls = False
            call_line = None
            call_column = None
            for match in matches:
                match_start = match.start()
                match_line_in_region = region_content[:match_start].count("\n") + 1
                match_line = line_start + match_line_in_region - 1

                # 如果使用位置不在定义行，则认为是调用
                if not is_definition_in_range or match_line != symbol.line_start:
                    has_calls = True
                    call_line = match_line
                    # 计算列号
                    line_start_pos = region_content[:match_start].rfind("\n") + 1
                    call_column = match_start - line_start_pos
                    break

            # 处理定义
            if is_definition_in_range:
                symbol.is_definition = True
                if symbol.name not in processed_symbols:
                    processed_symbols[symbol.name] = (symbol, True, None)

            # 处理调用
            if has_calls or not is_definition_in_range:
                # 创建或更新引用符号
                if symbol.name in processed_symbols:
                    (
                        existing_symbol,
                        existing_is_def,
                        existing_def_loc,
                    ) = processed_symbols[symbol.name]
                    # 如果已有定义，跳过；否则更新定义位置
                    if not existing_is_def and not existing_def_loc:
                        # 尝试获取定义位置
                        definition_location = self._find_definition_location(
                            symbol.name,
                            file_path,
                            call_line or line_start,
                            call_column or 0,
                            treesitter_extractor,
                            content,
                        )

                        if definition_location:
                            processed_symbols[symbol.name] = (
                                existing_symbol,
                                False,
                                definition_location,
                            )
                        else:
                            # 从符号表中查找
                            definition_symbols = self.symbol_table.find_symbol(
                                symbol.name
                            )
                            if definition_symbols:
                                def_symbol = definition_symbols[0]
                                definition_location = Symbol(
                                    name=def_symbol.name,
                                    kind=def_symbol.kind,
                                    file_path=def_symbol.file_path,
                                    line_start=def_symbol.line_start,
                                    line_end=def_symbol.line_end,
                                    signature=def_symbol.signature,
                                )
                                processed_symbols[symbol.name] = (
                                    existing_symbol,
                                    False,
                                    definition_location,
                                )
                else:
                    # 创建新的引用符号
                    reference_symbol = Symbol(
                        name=symbol.name,
                        kind=symbol.kind,
                        file_path=file_path,
                        line_start=call_line or line_start,
                        line_end=call_line or line_start,
                        signature=symbol.signature,
                        docstring=symbol.docstring,
                        parent=symbol.parent,
                        is_definition=False,
                    )

                    # 尝试获取定义位置
                    definition_location = self._find_definition_location(
                        symbol.name,
                        file_path,
                        call_line or line_start,
                        call_column or 0,
                        treesitter_extractor,
                        content,
                    )

                    if definition_location:
                        reference_symbol.definition_location = definition_location
                    else:
                        # 从符号表中查找
                        definition_symbols = self.symbol_table.find_symbol(symbol.name)
                        if definition_symbols:
                            def_symbol = definition_symbols[0]
                            reference_symbol.definition_location = Symbol(
                                name=def_symbol.name,
                                kind=def_symbol.kind,
                                file_path=def_symbol.file_path,
                                line_start=def_symbol.line_start,
                                line_end=def_symbol.line_end,
                                signature=def_symbol.signature,
                            )

                    processed_symbols[symbol.name] = (
                        reference_symbol,
                        False,
                        reference_symbol.definition_location,
                    )

        # 将处理后的符号添加到结果列表
        for symbol, is_def, def_loc in processed_symbols.values():
            if is_def:
                symbol.is_definition = True
            if def_loc:
                symbol.definition_location = def_loc
            used_symbols.append(symbol)

        return used_symbols

    def _find_definition_location(
        self,
        symbol_name: str,
        file_path: str,
        line: int,
        column: int,
        treesitter_extractor: Optional[Any],
        content: str,
    ) -> Optional[Symbol]:
        """查找符号的定义位置。

        使用 tree-sitter 符号提取器。

        Args:
            symbol_name: 符号名称
            file_path: 文件路径
            line: 行号（1-based）
            column: 列号（0-based）
            treesitter_extractor: tree-sitter 提取器（可选）
            content: 文件内容

        Returns:
            定义位置的 Symbol 对象，如果找不到则返回 None
        """
        # 使用 tree-sitter
        if treesitter_extractor:
            try:
                # 从符号表中查找定义（tree-sitter 已经提取了符号）
                definition_symbols = self.symbol_table.find_symbol(symbol_name)
                if definition_symbols:
                    # 选择第一个定义（可以改进为选择最相关的）
                    def_symbol = definition_symbols[0]
                    return Symbol(
                        name=def_symbol.name,
                        kind=def_symbol.kind,
                        file_path=def_symbol.file_path,
                        line_start=def_symbol.line_start,
                        line_end=def_symbol.line_end,
                        signature=def_symbol.signature,
                    )
            except Exception:
                pass

        return None

    def _find_imported_symbols(self, file_path: str) -> List[Symbol]:
        """Find all imported symbols in a file."""
        # Check if file is stale and update if needed
        if self.symbol_table.is_file_stale(file_path):
            self._refresh_file_symbols(file_path)

        symbols = self.symbol_table.get_file_symbols(file_path)
        return [s for s in symbols if s.kind == "import"]

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

    def _resolve_dependency_path(
        self, file_path: str, module_name: str
    ) -> Optional[str]:
        """Resolve a module name to a file path."""
        # Handle relative imports
        if module_name.startswith("."):
            # Relative import
            base_dir = os.path.dirname(file_path)
            parts = module_name.split(".")
            depth = len([p for p in parts if p == ""])
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
            for ext in [".py", ".rs", ".go", ".js", ".ts"]:
                full_path = module_path + ext
                if os.path.exists(full_path):
                    return full_path

                # Try __init__.py for Python packages
                if ext == ".py":
                    init_path = os.path.join(module_path, "__init__.py")
                    if os.path.exists(init_path):
                        return init_path
        else:
            # Absolute import - search in project
            parts = module_name.split(".")
            for root, dirs, files in os.walk(self.project_root):
                # Skip hidden directories and common ignore patterns
                dirs[:] = filter_walk_dirs(dirs)

                if parts[0] in dirs or f"{parts[0]}.py" in files:
                    module_path = os.path.join(root, *parts)

                    # Try common extensions
                    for ext in [".py", ".rs", ".go", ".js", ".ts"]:
                        full_path = module_path + ext
                        if os.path.exists(full_path):
                            return full_path

                        # Try __init__.py for Python packages
                        if ext == ".py":
                            init_path = os.path.join(module_path, "__init__.py")
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

        return "\n".join(parts) if parts else "No context available"
