"""Data types for symbol dependency analysis."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SymbolKind(Enum):
    """Types of code symbols."""

    FILE = "file"
    MODULE = "module"
    CLASS = "class"
    INTERFACE = "interface"
    STRUCT = "struct"
    ENUM = "enum"
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"
    VARIABLE = "variable"
    CONSTANT = "constant"
    IMPORT = "import"
    EXPORT = "export"
    DECORATOR = "decorator"


class EdgeKind(Enum):
    """Types of relationships between symbols."""

    CALLS = "calls"  # Function/method call
    IMPORTS = "imports"  # Import relationship
    EXTENDS = "extends"  # Inheritance
    IMPLEMENTS = "implements"  # Interface implementation
    CONTAINS = "contains"  # Containment
    REFERENCES = "references"  # Reference
    OVERRIDES = "overrides"  # Method override
    USES = "uses"  # Usage
    DEFINES = "defines"  # Definition
    RETURNS = "returns"  # Return type
    PARAMETER = "parameter"  # Parameter type
    DECORATES = "decorates"  # Decorator


@dataclass
class Node:
    """Represents a code symbol node."""

    id: str
    kind: SymbolKind
    name: str
    qualified_name: str
    file_path: str
    language: str
    start_line: int
    end_line: int
    start_column: int
    end_column: int
    docstring: Optional[str] = None
    signature: Optional[str] = None
    visibility: Optional[str] = None
    is_exported: bool = False
    is_async: bool = False
    is_static: bool = False
    parent_id: Optional[str] = None
    updated_at: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "id": self.id,
            "kind": self.kind.value,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "file_path": self.file_path,
            "language": self.language,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "start_column": self.start_column,
            "end_column": self.end_column,
            "docstring": self.docstring,
            "signature": self.signature,
            "visibility": self.visibility,
            "is_exported": int(self.is_exported),
            "is_async": int(self.is_async),
            "is_static": int(self.is_static),
            "parent_id": self.parent_id,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: Any) -> "Node":
        """Create from database row."""
        return cls(
            id=row["id"],
            kind=SymbolKind(row["kind"]),
            name=row["name"],
            qualified_name=row["qualified_name"],
            file_path=row["file_path"],
            language=row["language"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            start_column=row["start_column"],
            end_column=row["end_column"],
            docstring=row["docstring"],
            signature=row["signature"],
            visibility=row["visibility"],
            is_exported=bool(row["is_exported"]),
            is_async=bool(row["is_async"]),
            is_static=bool(row["is_static"]),
            parent_id=row["parent_id"],
            updated_at=row["updated_at"],
        )


@dataclass
class Edge:
    """Represents a relationship between two symbols."""

    source: str
    target: str
    kind: EdgeKind
    metadata: Optional[Dict[str, Any]] = None
    line: Optional[int] = None
    col: Optional[int] = None
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        import json

        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind.value,
            "metadata": json.dumps(self.metadata) if self.metadata else None,
            "line": self.line,
            "col": self.col,
        }

    @classmethod
    def from_row(cls, row: Any) -> "Edge":
        """Create from database row."""
        import json

        metadata = None
        if row["metadata"]:
            metadata = json.loads(row["metadata"])
        return cls(
            id=row["id"],
            source=row["source"],
            target=row["target"],
            kind=EdgeKind(row["kind"]),
            metadata=metadata,
            line=row["line"],
            col=row["col"],
        )


@dataclass
class FileRecord:
    """Represents a tracked source file."""

    path: str
    content_hash: str
    language: str
    size: int
    modified_at: int
    indexed_at: int
    node_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "path": self.path,
            "content_hash": self.content_hash,
            "language": self.language,
            "size": self.size,
            "modified_at": self.modified_at,
            "indexed_at": self.indexed_at,
            "node_count": self.node_count,
        }

    @classmethod
    def from_row(cls, row: Any) -> "FileRecord":
        """Create from database row."""
        return cls(
            path=row["path"],
            content_hash=row["content_hash"],
            language=row["language"],
            size=row["size"],
            modified_at=row["modified_at"],
            indexed_at=row["indexed_at"],
            node_count=row["node_count"],
        )


@dataclass
class Subgraph:
    """Represents a subgraph result from traversal."""

    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    root_id: str = ""
    depth: int = 0

    def get_node_by_id(self, node_id: str) -> Optional[Node]:
        """Get a node by its ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_edges_from(self, source_id: str) -> List[Edge]:
        """Get all edges from a source node."""
        return [e for e in self.edges if e.source == source_id]

    def get_edges_to(self, target_id: str) -> List[Edge]:
        """Get all edges to a target node."""
        return [e for e in self.edges if e.target == target_id]
