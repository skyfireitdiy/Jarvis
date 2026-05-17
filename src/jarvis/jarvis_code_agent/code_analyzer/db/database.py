"""Database connection management for symbol dependency analysis."""

import sqlite3
from pathlib import Path
from typing import Optional

from .query_builder import QueryBuilder
from .graph_traverser import GraphTraverser


class DatabaseConnection:
    """Manages SQLite database connections with performance optimizations."""

    def __init__(self, db_path: str, conn: sqlite3.Connection) -> None:
        self._db_path = db_path
        self._conn = conn
        self._queries: Optional[QueryBuilder] = None
        self._traverser: Optional[GraphTraverser] = None

    @staticmethod
    def initialize(db_path: str) -> "DatabaseConnection":
        """Initialize a new database with schema.

        Args:
            db_path: Path to the database file.

        Returns:
            DatabaseConnection instance.
        """
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row

        # Apply performance optimizations
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 120000")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA cache_size = -64000")  # 64 MB
        conn.execute("PRAGMA temp_store = MEMORY")

        # Load and execute schema
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            schema_sql = schema_path.read_text(encoding="utf-8")
            conn.executescript(schema_sql)

        conn.commit()
        return DatabaseConnection(db_path, conn)

    @staticmethod
    def open(db_path: str) -> "DatabaseConnection":
        """Open an existing database.

        Args:
            db_path: Path to the database file.

        Returns:
            DatabaseConnection instance.

        Raises:
            FileNotFoundError: If database file does not exist.
        """
        path = Path(db_path)
        if not path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row

        # Apply performance optimizations
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 120000")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA cache_size = -64000")
        conn.execute("PRAGMA temp_store = MEMORY")

        return DatabaseConnection(db_path, conn)

    def get_queries(self) -> QueryBuilder:
        """Get the query builder instance.

        Returns:
            QueryBuilder instance.
        """
        if self._queries is None:
            self._queries = QueryBuilder(self._conn)
        return self._queries

    def get_traverser(self) -> GraphTraverser:
        """Get the graph traverser instance.

        Returns:
            GraphTraverser instance.
        """
        if self._traverser is None:
            self._traverser = GraphTraverser(self.get_queries())
        return self._traverser

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]

    def __enter__(self) -> "DatabaseConnection":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        self.close()

    @property
    def connection(self) -> sqlite3.Connection:
        """Get the underlying SQLite connection."""
        return self._conn

    @property
    def db_path(self) -> str:
        """Get the database file path."""
        return self._db_path
