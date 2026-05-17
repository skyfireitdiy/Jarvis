"""Database-backed symbol table for efficient symbol storage and retrieval."""

import os
import time
from typing import Dict, List, Optional

from .db import (
    DatabaseConnection,
    Edge,
    EdgeKind,
    GraphTraverser,
    Node,
    QueryBuilder,
    SymbolKind,
)


class SymbolTableDB:
    """Database-backed symbol table using SQLite3."""

    def __init__(self, cache_dir: Optional[str] = None) -> None:
        self.cache_dir = cache_dir or ".jarvis/symbol_cache"
        self._db: Optional[DatabaseConnection] = None
        self._queries: Optional[QueryBuilder] = None

    def _get_db_path(self) -> str:
        """Get the database file path."""
        return os.path.join(self.cache_dir, "codegraph.db")

    def _ensure_db(self) -> QueryBuilder:
        """Ensure database connection is established."""
        if self._db is None:
            db_path = self._get_db_path()
            if os.path.exists(db_path):
                self._db = DatabaseConnection.open(db_path)
            else:
                self._db = DatabaseConnection.initialize(db_path)
            self._queries = self._db.get_queries()
        assert self._queries is not None
        return self._queries

    @property
    def queries(self) -> QueryBuilder:
        """Get the query builder."""
        return self._ensure_db()

    def get_traverser(self) -> GraphTraverser:
        """Get the graph traverser."""
        queries = self._ensure_db()
        return GraphTraverser(queries)

    def close(self) -> None:
        """Close the database connection."""
        if self._db:
            self._db.close()
            self._db = None
            self._queries = None

    def __enter__(self) -> "SymbolTableDB":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        self.close()

    # =========================================================================
    # Symbol Operations
    # =========================================================================

    def add_symbol(
        self,
        name: str,
        kind: str,
        file_path: str,
        line_start: int,
        line_end: int,
        qualified_name: Optional[str] = None,
        language: str = "unknown",
        signature: Optional[str] = None,
        docstring: Optional[str] = None,
        parent: Optional[str] = None,
        is_exported: bool = False,
        is_async: bool = False,
        is_static: bool = False,
        visibility: Optional[str] = None,
    ) -> Node:
        """Add a symbol to the database.

        Args:
            name: Symbol name.
            kind: Symbol kind (function, class, variable, etc.).
            file_path: File path where symbol is defined.
            line_start: Start line number.
            line_end: End line number.
            qualified_name: Fully qualified name.
            language: Programming language.
            signature: Function/method signature.
            docstring: Documentation string.
            parent: Parent symbol ID.
            is_exported: Whether symbol is exported.
            is_async: Whether symbol is async.
            is_static: Whether symbol is static.
            visibility: Visibility level (public, private, protected).

        Returns:
            The created Node.
        """
        # Generate unique ID
        node_id = f"{file_path}:{name}:{line_start}"
        if qualified_name:
            node_id = f"{file_path}:{qualified_name}:{line_start}"

        # Map kind string to SymbolKind enum
        symbol_kind = self._map_kind(kind)

        node = Node(
            id=node_id,
            kind=symbol_kind,
            name=name,
            qualified_name=qualified_name or name,
            file_path=file_path,
            language=language,
            start_line=line_start,
            end_line=line_end,
            start_column=0,
            end_column=0,
            docstring=docstring,
            signature=signature,
            visibility=visibility,
            is_exported=is_exported,
            is_async=is_async,
            is_static=is_static,
            parent_id=parent,
            updated_at=int(time.time() * 1000),
        )

        self.queries.insert_node(node)
        return node

    def _map_kind(self, kind: str) -> SymbolKind:
        """Map string kind to SymbolKind enum."""
        kind_map = {
            "function": SymbolKind.FUNCTION,
            "method": SymbolKind.METHOD,
            "class": SymbolKind.CLASS,
            "interface": SymbolKind.INTERFACE,
            "struct": SymbolKind.STRUCT,
            "enum": SymbolKind.ENUM,
            "variable": SymbolKind.VARIABLE,
            "constant": SymbolKind.CONSTANT,
            "import": SymbolKind.IMPORT,
            "export": SymbolKind.EXPORT,
            "module": SymbolKind.MODULE,
            "file": SymbolKind.FILE,
            "property": SymbolKind.PROPERTY,
            "decorator": SymbolKind.DECORATOR,
        }
        return kind_map.get(kind.lower(), SymbolKind.VARIABLE)

    def find_symbol(self, name: str, file_path: Optional[str] = None) -> List[Node]:
        """Find symbols by name.

        Args:
            name: Symbol name to search for.
            file_path: Optional file path to limit search.

        Returns:
            List of matching nodes.
        """
        if file_path:
            nodes = self.queries.get_nodes_by_file(file_path)
            return [n for n in nodes if n.name == name or n.qualified_name == name]
        return self.queries.get_nodes_by_name(name)

    def get_file_symbols(self, file_path: str) -> List[Node]:
        """Get all symbols in a file.

        Args:
            file_path: The file path.

        Returns:
            List of nodes in the file.
        """
        return self.queries.get_nodes_by_file(file_path)

    def clear_file_symbols(self, file_path: str) -> None:
        """Remove all symbols for a file.

        Args:
            file_path: The file path.
        """
        self.queries.delete_file(file_path)

    def is_file_stale(self, file_path: str) -> bool:
        """Check if file has been modified since last indexing.

        Args:
            file_path: The file path.

        Returns:
            True if file needs re-indexing.
        """
        file_record = self.queries.get_file_by_path(file_path)
        if not file_record:
            return True

        if not os.path.exists(file_path):
            return False

        try:
            current_mtime = int(os.path.getmtime(file_path) * 1000)
            return current_mtime > file_record.modified_at
        except OSError:
            return True

    def update_file_record(
        self,
        file_path: str,
        content_hash: str,
        language: str,
        node_count: int,
    ) -> None:
        """Update or create file record.

        Args:
            file_path: The file path.
            content_hash: Hash of file content.
            language: Programming language.
            node_count: Number of nodes in file.
        """
        from .db import FileRecord

        try:
            size = os.path.getsize(file_path)
            mtime = int(os.path.getmtime(file_path) * 1000)
        except OSError:
            size = 0
            mtime = 0

        record = FileRecord(
            path=file_path,
            content_hash=content_hash,
            language=language,
            size=size,
            modified_at=mtime,
            indexed_at=int(time.time() * 1000),
            node_count=node_count,
        )
        self.queries.upsert_file(record)

    # =========================================================================
    # Edge Operations
    # =========================================================================

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        kind: str,
        line: Optional[int] = None,
        col: Optional[int] = None,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Add an edge between two symbols.

        Args:
            source_id: Source node ID.
            target_id: Target node ID.
            kind: Edge kind (calls, imports, extends, etc.).
            line: Line number where relationship occurs.
            col: Column number where relationship occurs.
            metadata: Additional metadata.
        """
        edge_kind = self._map_edge_kind(kind)
        edge = Edge(
            source=source_id,
            target=target_id,
            kind=edge_kind,
            line=line,
            col=col,
            metadata=metadata,
        )
        self.queries.insert_edge(edge)

    def _map_edge_kind(self, kind: str) -> EdgeKind:
        """Map string kind to EdgeKind enum."""
        kind_map = {
            "calls": EdgeKind.CALLS,
            "imports": EdgeKind.IMPORTS,
            "extends": EdgeKind.EXTENDS,
            "implements": EdgeKind.IMPLEMENTS,
            "contains": EdgeKind.CONTAINS,
            "references": EdgeKind.REFERENCES,
            "overrides": EdgeKind.OVERRIDES,
            "uses": EdgeKind.USES,
            "defines": EdgeKind.DEFINES,
            "returns": EdgeKind.RETURNS,
            "parameter": EdgeKind.PARAMETER,
            "decorates": EdgeKind.DECORATES,
        }
        return kind_map.get(kind.lower(), EdgeKind.REFERENCES)

    def get_symbol_edges(
        self,
        node_id: str,
        direction: str = "outgoing",
        edge_kinds: Optional[List[str]] = None,
    ) -> List[Edge]:
        """Get edges for a symbol.

        Args:
            node_id: The node ID.
            direction: 'outgoing', 'incoming', or 'both'.
            edge_kinds: Optional filter for edge types.

        Returns:
            List of edges.
        """
        kinds = None
        if edge_kinds:
            kinds = [self._map_edge_kind(k) for k in edge_kinds]

        edges: List[Edge] = []
        if direction in ("outgoing", "both"):
            edges.extend(self.queries.get_outgoing_edges(node_id, kinds))
        if direction in ("incoming", "both"):
            edges.extend(self.queries.get_incoming_edges(node_id, kinds))
        return edges
