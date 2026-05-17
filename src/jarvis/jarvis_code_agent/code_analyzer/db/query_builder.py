"""Query builder for symbol dependency database operations."""

import sqlite3
from typing import List, Optional

from .data_types import Edge, EdgeKind, FileRecord, Node, SymbolKind


class QueryBuilder:
    """Provides CRUD operations for nodes, edges, and files."""

    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db
        self._prepare_statements()

    def _prepare_statements(self) -> None:
        """Prepare commonly used SQL statements."""
        # Node statements
        self._insert_node_sql = """
            INSERT OR REPLACE INTO nodes (
                id, kind, name, qualified_name, file_path, language,
                start_line, end_line, start_column, end_column,
                docstring, signature, visibility,
                is_exported, is_async, is_static, parent_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        self._get_node_sql = "SELECT * FROM nodes WHERE id = ?"
        self._get_nodes_by_file_sql = (
            "SELECT * FROM nodes WHERE file_path = ? ORDER BY start_line"
        )
        self._get_nodes_by_kind_sql = "SELECT * FROM nodes WHERE kind = ?"
        self._get_nodes_by_name_sql = (
            "SELECT * FROM nodes WHERE name = ? OR qualified_name = ?"
        )
        self._delete_node_sql = "DELETE FROM nodes WHERE id = ?"
        self._delete_nodes_by_file_sql = "DELETE FROM nodes WHERE file_path = ?"

        # Edge statements
        self._insert_edge_sql = """
            INSERT INTO edges (source, target, kind, metadata, line, col)
            VALUES (?, ?, ?, ?, ?, ?)
        """

        self._get_outgoing_sql = "SELECT * FROM edges WHERE source = ?"
        self._get_outgoing_kinds_sql = (
            "SELECT * FROM edges WHERE source = ? AND kind IN ({})"
        )
        self._get_incoming_sql = "SELECT * FROM edges WHERE target = ?"
        self._get_incoming_kinds_sql = (
            "SELECT * FROM edges WHERE target = ? AND kind IN ({})"
        )
        self._delete_edges_by_source_sql = "DELETE FROM edges WHERE source = ?"
        self._delete_edges_by_target_sql = "DELETE FROM edges WHERE target = ?"

        # File statements
        self._upsert_file_sql = """
            INSERT OR REPLACE INTO files (
                path, content_hash, language, size, modified_at, indexed_at, node_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        self._get_file_sql = "SELECT * FROM files WHERE path = ?"
        self._delete_file_sql = "DELETE FROM files WHERE path = ?"
        self._get_all_files_sql = "SELECT * FROM files ORDER BY path"

    # =========================================================================
    # Node Operations
    # =========================================================================

    def insert_node(self, node: Node) -> None:
        """Insert or update a node.

        Args:
            node: The node to insert.
        """
        data = node.to_dict()
        self.db.execute(
            self._insert_node_sql,
            (
                data["id"],
                data["kind"],
                data["name"],
                data["qualified_name"],
                data["file_path"],
                data["language"],
                data["start_line"],
                data["end_line"],
                data["start_column"],
                data["end_column"],
                data["docstring"],
                data["signature"],
                data["visibility"],
                data["is_exported"],
                data["is_async"],
                data["is_static"],
                data["parent_id"],
                data["updated_at"],
            ),
        )

    def insert_nodes(self, nodes: List[Node]) -> None:
        """Insert multiple nodes in a transaction.

        Args:
            nodes: List of nodes to insert.
        """
        for node in nodes:
            self.insert_node(node)

    def get_node_by_id(self, node_id: str) -> Optional[Node]:
        """Get a node by its ID.

        Args:
            node_id: The node ID.

        Returns:
            The node if found, None otherwise.
        """
        cursor = self.db.execute(self._get_node_sql, (node_id,))
        row = cursor.fetchone()
        if row:
            return Node.from_row(row)
        return None

    def get_nodes_by_file(self, file_path: str) -> List[Node]:
        """Get all nodes in a file.

        Args:
            file_path: The file path.

        Returns:
            List of nodes in the file.
        """
        cursor = self.db.execute(self._get_nodes_by_file_sql, (file_path,))
        return [Node.from_row(row) for row in cursor.fetchall()]

    def get_nodes_by_kind(self, kind: SymbolKind) -> List[Node]:
        """Get all nodes of a specific kind.

        Args:
            kind: The symbol kind.

        Returns:
            List of nodes of the specified kind.
        """
        cursor = self.db.execute(self._get_nodes_by_kind_sql, (kind.value,))
        return [Node.from_row(row) for row in cursor.fetchall()]

    def get_nodes_by_name(self, name: str) -> List[Node]:
        """Get nodes by name or qualified name.

        Args:
            name: The name to search for.

        Returns:
            List of matching nodes.
        """
        cursor = self.db.execute(self._get_nodes_by_name_sql, (name, name))
        return [Node.from_row(row) for row in cursor.fetchall()]

    def delete_node(self, node_id: str) -> None:
        """Delete a node and its edges.

        Args:
            node_id: The node ID to delete.
        """
        self.db.execute(self._delete_edges_by_source_sql, (node_id,))
        self.db.execute(self._delete_edges_by_target_sql, (node_id,))
        self.db.execute(self._delete_node_sql, (node_id,))

    def delete_nodes_by_file(self, file_path: str) -> None:
        """Delete all nodes in a file.

        Args:
            file_path: The file path.
        """
        # Get node IDs first to delete their edges
        cursor = self.db.execute(
            "SELECT id FROM nodes WHERE file_path = ?", (file_path,)
        )
        node_ids = [row[0] for row in cursor.fetchall()]

        for node_id in node_ids:
            self.db.execute(self._delete_edges_by_source_sql, (node_id,))
            self.db.execute(self._delete_edges_by_target_sql, (node_id,))

        self.db.execute(self._delete_nodes_by_file_sql, (file_path,))

    # =========================================================================
    # Edge Operations
    # =========================================================================

    def insert_edge(self, edge: Edge) -> None:
        """Insert an edge.

        Args:
            edge: The edge to insert.
        """
        import json

        metadata = json.dumps(edge.metadata) if edge.metadata else None
        self.db.execute(
            self._insert_edge_sql,
            (edge.source, edge.target, edge.kind.value, metadata, edge.line, edge.col),
        )

    def insert_edges(self, edges: List[Edge]) -> None:
        """Insert multiple edges.

        Args:
            edges: List of edges to insert.
        """
        for edge in edges:
            self.insert_edge(edge)

    def get_outgoing_edges(
        self, source_id: str, kinds: Optional[List[EdgeKind]] = None
    ) -> List[Edge]:
        """Get outgoing edges from a node.

        Args:
            source_id: The source node ID.
            kinds: Optional list of edge kinds to filter.

        Returns:
            List of outgoing edges.
        """
        if kinds:
            placeholders = ",".join("?" for _ in kinds)
            sql = self._get_outgoing_kinds_sql.format(placeholders)
            params = (source_id,) + tuple(k.value for k in kinds)
        else:
            sql = self._get_outgoing_sql
            params = (source_id,)

        cursor = self.db.execute(sql, params)
        return [Edge.from_row(row) for row in cursor.fetchall()]

    def get_incoming_edges(
        self, target_id: str, kinds: Optional[List[EdgeKind]] = None
    ) -> List[Edge]:
        """Get incoming edges to a node.

        Args:
            target_id: The target node ID.
            kinds: Optional list of edge kinds to filter.

        Returns:
            List of incoming edges.
        """
        if kinds:
            placeholders = ",".join("?" for _ in kinds)
            sql = self._get_incoming_kinds_sql.format(placeholders)
            params = (target_id,) + tuple(k.value for k in kinds)
        else:
            sql = self._get_incoming_sql
            params = (target_id,)

        cursor = self.db.execute(sql, params)
        return [Edge.from_row(row) for row in cursor.fetchall()]

    def delete_edges_by_source(self, source_id: str) -> None:
        """Delete all edges from a source node.

        Args:
            source_id: The source node ID.
        """
        self.db.execute(self._delete_edges_by_source_sql, (source_id,))

    # =========================================================================
    # File Operations
    # =========================================================================

    def upsert_file(self, file_record: FileRecord) -> None:
        """Insert or update a file record.

        Args:
            file_record: The file record to upsert.
        """
        data = file_record.to_dict()
        self.db.execute(
            self._upsert_file_sql,
            (
                data["path"],
                data["content_hash"],
                data["language"],
                data["size"],
                data["modified_at"],
                data["indexed_at"],
                data["node_count"],
            ),
        )

    def get_file_by_path(self, path: str) -> Optional[FileRecord]:
        """Get a file record by path.

        Args:
            path: The file path.

        Returns:
            The file record if found, None otherwise.
        """
        cursor = self.db.execute(self._get_file_sql, (path,))
        row = cursor.fetchone()
        if row:
            return FileRecord.from_row(row)
        return None

    def get_all_files(self) -> List[FileRecord]:
        """Get all tracked files.

        Returns:
            List of all file records.
        """
        cursor = self.db.execute(self._get_all_files_sql)
        return [FileRecord.from_row(row) for row in cursor.fetchall()]

    def delete_file(self, path: str) -> None:
        """Delete a file and its nodes/edges.

        Args:
            path: The file path.
        """
        self.delete_nodes_by_file(path)
        self.db.execute(self._delete_file_sql, (path,))
