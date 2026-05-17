"""Graph traversal algorithms for symbol dependency analysis."""

from collections import deque
from typing import Dict, List, Optional, Set

from .data_types import Edge, EdgeKind, Node, Subgraph
from .query_builder import QueryBuilder


class GraphTraverser:
    """Provides graph traversal operations for symbol dependencies."""

    def __init__(self, queries: QueryBuilder) -> None:
        self.queries = queries

    def traverse_bfs(
        self,
        start_id: str,
        max_depth: int = 3,
        edge_kinds: Optional[List[EdgeKind]] = None,
        direction: str = "outgoing",
        limit: int = 1000,
    ) -> Subgraph:
        """Breadth-first traversal of the graph.

        Args:
            start_id: Starting node ID.
            max_depth: Maximum traversal depth.
            edge_kinds: Optional filter for edge types.
            direction: 'outgoing', 'incoming', or 'both'.
            limit: Maximum number of nodes to visit.

        Returns:
            Subgraph containing visited nodes and edges.
        """
        visited: Set[str] = set()
        nodes: Dict[str, Node] = {}
        edges: List[Edge] = []
        queue: deque[tuple[str, int]] = deque()

        # Get start node
        start_node = self.queries.get_node_by_id(start_id)
        if not start_node:
            return Subgraph(root_id=start_id, depth=0)

        queue.append((start_id, 0))
        visited.add(start_id)
        nodes[start_id] = start_node

        while queue and len(nodes) < limit:
            current_id, depth = queue.popleft()

            if depth >= max_depth:
                continue

            # Get edges based on direction
            current_edges: List[Edge] = []
            if direction in ("outgoing", "both"):
                current_edges.extend(
                    self.queries.get_outgoing_edges(current_id, edge_kinds)
                )
            if direction in ("incoming", "both"):
                current_edges.extend(
                    self.queries.get_incoming_edges(current_id, edge_kinds)
                )

            for edge in current_edges:
                edges.append(edge)

                # Determine neighbor based on direction
                if edge.source == current_id:
                    neighbor_id = edge.target
                else:
                    neighbor_id = edge.source

                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    neighbor = self.queries.get_node_by_id(neighbor_id)
                    if neighbor:
                        nodes[neighbor_id] = neighbor
                        queue.append((neighbor_id, depth + 1))

        return Subgraph(
            nodes=list(nodes.values()),
            edges=edges,
            root_id=start_id,
            depth=max_depth,
        )

    def traverse_dfs(
        self,
        start_id: str,
        max_depth: int = 3,
        edge_kinds: Optional[List[EdgeKind]] = None,
        direction: str = "outgoing",
    ) -> Subgraph:
        """Depth-first traversal of the graph.

        Args:
            start_id: Starting node ID.
            max_depth: Maximum traversal depth.
            edge_kinds: Optional filter for edge types.
            direction: 'outgoing', 'incoming', or 'both'.

        Returns:
            Subgraph containing visited nodes and edges.
        """
        visited: Set[str] = set()
        nodes: Dict[str, Node] = {}
        edges: List[Edge] = []

        def dfs(node_id: str, depth: int) -> None:
            if node_id in visited or depth > max_depth:
                return

            visited.add(node_id)
            node = self.queries.get_node_by_id(node_id)
            if not node:
                return

            nodes[node_id] = node

            # Get edges based on direction
            current_edges: List[Edge] = []
            if direction in ("outgoing", "both"):
                current_edges.extend(
                    self.queries.get_outgoing_edges(node_id, edge_kinds)
                )
            if direction in ("incoming", "both"):
                current_edges.extend(
                    self.queries.get_incoming_edges(node_id, edge_kinds)
                )

            for edge in current_edges:
                edges.append(edge)

                # Determine neighbor based on direction
                if edge.source == node_id:
                    neighbor_id = edge.target
                else:
                    neighbor_id = edge.source

                dfs(neighbor_id, depth + 1)

        dfs(start_id, 0)

        return Subgraph(
            nodes=list(nodes.values()),
            edges=edges,
            root_id=start_id,
            depth=max_depth,
        )

    def get_type_hierarchy(self, node_id: str) -> Subgraph:
        """Get the type hierarchy (inheritance chain) for a class.

        Args:
            node_id: The class node ID.

        Returns:
            Subgraph containing the inheritance hierarchy.
        """
        return self.traverse_bfs(
            node_id,
            max_depth=10,
            edge_kinds=[EdgeKind.EXTENDS, EdgeKind.IMPLEMENTS],
            direction="both",
        )

    def get_call_graph(self, node_id: str, depth: int = 2) -> Subgraph:
        """Get the call graph for a function/method.

        Args:
            node_id: The function/method node ID.
            depth: Maximum call depth.

        Returns:
            Subgraph containing the call graph.
        """
        return self.traverse_bfs(
            node_id,
            max_depth=depth,
            edge_kinds=[EdgeKind.CALLS],
            direction="outgoing",
        )

    def get_callers(self, node_id: str, max_depth: int = 1) -> List[Node]:
        """Get all callers of a function/method.

        Args:
            node_id: The function/method node ID.
            max_depth: Maximum depth to search.

        Returns:
            List of nodes that call the specified node.
        """
        subgraph = self.traverse_bfs(
            node_id,
            max_depth=max_depth,
            edge_kinds=[EdgeKind.CALLS],
            direction="incoming",
        )
        return [n for n in subgraph.nodes if n.id != node_id]

    def get_callees(self, node_id: str, max_depth: int = 1) -> List[Node]:
        """Get all callees of a function/method.

        Args:
            node_id: The function/method node ID.
            max_depth: Maximum depth to search.

        Returns:
            List of nodes called by the specified node.
        """
        subgraph = self.traverse_bfs(
            node_id,
            max_depth=max_depth,
            edge_kinds=[EdgeKind.CALLS],
            direction="outgoing",
        )
        return [n for n in subgraph.nodes if n.id != node_id]

    def get_dependencies(self, node_id: str, max_depth: int = 1) -> List[Node]:
        """Get all dependencies of a node.

        Args:
            node_id: The node ID.
            max_depth: Maximum depth to search.

        Returns:
            List of nodes that the specified node depends on.
        """
        subgraph = self.traverse_bfs(
            node_id,
            max_depth=max_depth,
            edge_kinds=[EdgeKind.USES, EdgeKind.REFERENCES, EdgeKind.IMPORTS],
            direction="outgoing",
        )
        return [n for n in subgraph.nodes if n.id != node_id]

    def get_dependents(self, node_id: str, max_depth: int = 1) -> List[Node]:
        """Get all nodes that depend on the specified node.

        Args:
            node_id: The node ID.
            max_depth: Maximum depth to search.

        Returns:
            List of nodes that depend on the specified node.
        """
        subgraph = self.traverse_bfs(
            node_id,
            max_depth=max_depth,
            edge_kinds=[EdgeKind.USES, EdgeKind.REFERENCES, EdgeKind.IMPORTS],
            direction="incoming",
        )
        return [n for n in subgraph.nodes if n.id != node_id]
