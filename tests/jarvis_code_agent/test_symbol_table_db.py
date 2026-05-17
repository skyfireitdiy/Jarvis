"""Tests for database-backed symbol table."""

import tempfile

import pytest

from jarvis.jarvis_code_agent.code_analyzer.db import EdgeKind, SymbolKind
from jarvis.jarvis_code_agent.code_analyzer.symbol_table_db import SymbolTableDB


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = SymbolTableDB(cache_dir=tmpdir)
        yield db
        db.close()


class TestSymbolTableDB:
    """Test cases for SymbolTableDB."""

    def test_add_symbol(self, temp_db):
        """Test adding a symbol."""
        node = temp_db.add_symbol(
            name="test_function",
            kind="function",
            file_path="/test/file.py",
            line_start=10,
            line_end=20,
            language="python",
            signature="def test_function():",
            docstring="Test function docstring",
        )

        assert node.name == "test_function"
        assert node.kind == SymbolKind.FUNCTION
        assert node.file_path == "/test/file.py"
        assert node.start_line == 10
        assert node.end_line == 20

    def test_find_symbol(self, temp_db):
        """Test finding symbols by name."""
        temp_db.add_symbol(
            name="my_class",
            kind="class",
            file_path="/test/file.py",
            line_start=1,
            line_end=50,
            language="python",
        )

        results = temp_db.find_symbol("my_class")
        assert len(results) == 1
        assert results[0].name == "my_class"
        assert results[0].kind == SymbolKind.CLASS

    def test_get_file_symbols(self, temp_db):
        """Test getting all symbols in a file."""
        temp_db.add_symbol(
            name="func1",
            kind="function",
            file_path="/test/file.py",
            line_start=1,
            line_end=10,
        )
        temp_db.add_symbol(
            name="func2",
            kind="function",
            file_path="/test/file.py",
            line_start=15,
            line_end=25,
        )
        temp_db.add_symbol(
            name="func3",
            kind="function",
            file_path="/other/file.py",
            line_start=1,
            line_end=10,
        )

        symbols = temp_db.get_file_symbols("/test/file.py")
        assert len(symbols) == 2
        names = {s.name for s in symbols}
        assert names == {"func1", "func2"}

    def test_clear_file_symbols(self, temp_db):
        """Test clearing symbols for a file."""
        temp_db.add_symbol(
            name="func1",
            kind="function",
            file_path="/test/file.py",
            line_start=1,
            line_end=10,
        )
        temp_db.add_symbol(
            name="func2",
            kind="function",
            file_path="/test/file.py",
            line_start=15,
            line_end=25,
        )

        temp_db.clear_file_symbols("/test/file.py")
        symbols = temp_db.get_file_symbols("/test/file.py")
        assert len(symbols) == 0

    def test_add_edge(self, temp_db):
        """Test adding an edge between symbols."""
        # Add two symbols
        temp_db.add_symbol(
            name="caller",
            kind="function",
            file_path="/test/file.py",
            line_start=1,
            line_end=10,
        )
        temp_db.add_symbol(
            name="callee",
            kind="function",
            file_path="/test/file.py",
            line_start=20,
            line_end=30,
        )

        # Add edge
        temp_db.add_edge(
            source_id="/test/file.py:caller:1",
            target_id="/test/file.py:callee:20",
            kind="calls",
            line=5,
        )

        # Verify edge
        edges = temp_db.get_symbol_edges("/test/file.py:caller:1", direction="outgoing")
        assert len(edges) == 1
        assert edges[0].kind == EdgeKind.CALLS
        assert edges[0].target == "/test/file.py:callee:20"

    def test_get_symbol_edges_both_directions(self, temp_db):
        """Test getting edges in both directions."""
        temp_db.add_symbol(
            name="a",
            kind="function",
            file_path="/test/file.py",
            line_start=1,
            line_end=10,
        )
        temp_db.add_symbol(
            name="b",
            kind="function",
            file_path="/test/file.py",
            line_start=20,
            line_end=30,
        )

        temp_db.add_edge(
            source_id="/test/file.py:a:1", target_id="/test/file.py:b:20", kind="calls"
        )

        # Outgoing from a
        edges = temp_db.get_symbol_edges("/test/file.py:a:1", direction="outgoing")
        assert len(edges) == 1

        # Incoming to b
        edges = temp_db.get_symbol_edges("/test/file.py:b:20", direction="incoming")
        assert len(edges) == 1

        # Both directions from a
        edges = temp_db.get_symbol_edges("/test/file.py:a:1", direction="both")
        assert len(edges) == 1

    def test_update_file_record(self, temp_db):
        """Test updating file record."""
        temp_db.update_file_record(
            file_path="/test/file.py",
            content_hash="abc123",
            language="python",
            node_count=5,
        )

        # Verify file is not stale
        assert not temp_db.is_file_stale("/test/file.py")

    def test_is_file_stale_new_file(self, temp_db):
        """Test that new files are considered stale."""
        assert temp_db.is_file_stale("/nonexistent/file.py")
