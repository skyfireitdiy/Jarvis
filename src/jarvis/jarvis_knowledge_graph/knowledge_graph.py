"""知识图谱核心模块

该模块提供轻量级知识图谱功能，包括：
- 知识节点和关系的数据结构定义
- 节点和边的CRUD操作
- 图查询操作（邻居查询、路径查找、相关知识检索）
- JSON文件持久化存储
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class NodeType(Enum):
    """知识节点类型"""

    METHODOLOGY = "methodology"  # 方法论
    RULE = "rule"  # 规则
    MEMORY = "memory"  # 记忆
    CODE = "code"  # 代码
    FILE = "file"  # 文件
    CONCEPT = "concept"  # 概念


class RelationType(Enum):
    """知识关系类型"""

    REFERENCES = "references"  # 引用
    DEPENDS_ON = "depends_on"  # 依赖
    SIMILAR_TO = "similar_to"  # 相似
    DERIVED_FROM = "derived_from"  # 派生自
    IMPLEMENTS = "implements"  # 实现
    RELATED_TO = "related_to"  # 相关
    PART_OF = "part_of"  # 属于
    SUPERSEDES = "supersedes"  # 取代


@dataclass
class KnowledgeNode:
    """知识节点数据类

    表示知识图谱中的一个节点，可以是方法论、规则、记忆、代码等。
    """

    node_id: str  # 节点唯一标识
    node_type: NodeType  # 节点类型
    name: str  # 节点名称
    description: str  # 节点描述
    source_path: Optional[str] = None  # 来源路径
    tags: List[str] = field(default_factory=list)  # 标签列表
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    created_at: datetime = field(default_factory=datetime.now)  # 创建时间
    updated_at: datetime = field(default_factory=datetime.now)  # 更新时间

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于JSON序列化"""
        data = asdict(self)
        data["node_type"] = self.node_type.value
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeNode":
        """从字典创建节点"""
        data = data.copy()
        data["node_type"] = NodeType(data["node_type"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**data)


@dataclass
class KnowledgeEdge:
    """知识关系数据类

    表示知识图谱中两个节点之间的关系。
    """

    edge_id: str  # 边唯一标识
    source_id: str  # 源节点ID
    target_id: str  # 目标节点ID
    relation_type: RelationType  # 关系类型
    strength: float = 1.0  # 关系强度 (0-1)
    description: Optional[str] = None  # 关系描述
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    created_at: datetime = field(default_factory=datetime.now)  # 创建时间

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于JSON序列化"""
        data = asdict(self)
        data["relation_type"] = self.relation_type.value
        data["created_at"] = self.created_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeEdge":
        """从字典创建边"""
        data = data.copy()
        data["relation_type"] = RelationType(data["relation_type"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)


class KnowledgeGraph:
    """知识图谱管理类

    提供知识节点和关系的管理功能，包括：
    - 节点的增删改查
    - 边的增删查
    - 图查询（邻居、路径、相关知识）
    - 持久化存储
    """

    def __init__(self, storage_dir: Optional[str] = None):
        """初始化知识图谱

        Args:
            storage_dir: 存储目录路径，默认为 .jarvis/knowledge_graph
        """
        self.storage_dir = Path(storage_dir or ".jarvis/knowledge_graph")
        self._nodes: Dict[str, KnowledgeNode] = {}  # 节点缓存
        self._edges: Dict[str, KnowledgeEdge] = {}  # 边缓存
        self._adjacency: Dict[str, Set[str]] = {}  # 邻接表（出边）
        self._reverse_adjacency: Dict[str, Set[str]] = {}  # 反向邻接表（入边）
        self._tag_index: Dict[str, Set[str]] = {}  # 标签索引
        self._type_index: Dict[NodeType, Set[str]] = {}  # 类型索引

        # 初始化存储目录
        self._init_storage()
        # 加载已有数据
        self._load_all()

    def _init_storage(self) -> None:
        """初始化存储目录结构"""
        # 创建目录结构
        (self.storage_dir / "nodes").mkdir(parents=True, exist_ok=True)
        (self.storage_dir / "edges").mkdir(parents=True, exist_ok=True)

        # 为每种节点类型创建子目录
        for node_type in NodeType:
            (self.storage_dir / "nodes" / node_type.value).mkdir(exist_ok=True)

    def _load_all(self) -> None:
        """加载所有节点和边"""
        # 加载节点
        nodes_dir = self.storage_dir / "nodes"
        for type_dir in nodes_dir.iterdir():
            if type_dir.is_dir():
                for node_file in type_dir.glob("*.json"):
                    try:
                        with open(node_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            node = KnowledgeNode.from_dict(data)
                            self._nodes[node.node_id] = node
                            self._update_indexes(node)
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue  # 跳过损坏的文件

        # 加载边
        edges_file = self.storage_dir / "edges" / "edges.json"
        if edges_file.exists():
            try:
                with open(edges_file, "r", encoding="utf-8") as f:
                    edges_data = json.load(f)
                    for edge_data in edges_data:
                        edge = KnowledgeEdge.from_dict(edge_data)
                        self._edges[edge.edge_id] = edge
                        self._update_adjacency(edge)
            except (json.JSONDecodeError, KeyError, ValueError):
                pass  # 跳过损坏的文件

    def _update_indexes(self, node: KnowledgeNode) -> None:
        """更新节点索引"""
        # 更新标签索引
        for tag in node.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = set()
            self._tag_index[tag].add(node.node_id)

        # 更新类型索引
        if node.node_type not in self._type_index:
            self._type_index[node.node_type] = set()
        self._type_index[node.node_type].add(node.node_id)

    def _remove_from_indexes(self, node: KnowledgeNode) -> None:
        """从索引中移除节点"""
        # 从标签索引移除
        for tag in node.tags:
            if tag in self._tag_index:
                self._tag_index[tag].discard(node.node_id)
                if not self._tag_index[tag]:
                    del self._tag_index[tag]

        # 从类型索引移除
        if node.node_type in self._type_index:
            self._type_index[node.node_type].discard(node.node_id)

    def _update_adjacency(self, edge: KnowledgeEdge) -> None:
        """更新邻接表"""
        # 出边
        if edge.source_id not in self._adjacency:
            self._adjacency[edge.source_id] = set()
        self._adjacency[edge.source_id].add(edge.edge_id)

        # 入边
        if edge.target_id not in self._reverse_adjacency:
            self._reverse_adjacency[edge.target_id] = set()
        self._reverse_adjacency[edge.target_id].add(edge.edge_id)

    def _remove_from_adjacency(self, edge: KnowledgeEdge) -> None:
        """从邻接表移除边"""
        if edge.source_id in self._adjacency:
            self._adjacency[edge.source_id].discard(edge.edge_id)
        if edge.target_id in self._reverse_adjacency:
            self._reverse_adjacency[edge.target_id].discard(edge.edge_id)

    def _save_node(self, node: KnowledgeNode) -> None:
        """保存节点到文件"""
        node_file = (
            self.storage_dir / "nodes" / node.node_type.value / f"{node.node_id}.json"
        )
        with open(node_file, "w", encoding="utf-8") as f:
            json.dump(node.to_dict(), f, ensure_ascii=False, indent=2)

    def _delete_node_file(self, node: KnowledgeNode) -> None:
        """删除节点文件"""
        node_file = (
            self.storage_dir / "nodes" / node.node_type.value / f"{node.node_id}.json"
        )
        if node_file.exists():
            node_file.unlink()

    def _save_edges(self) -> None:
        """保存所有边到文件"""
        edges_file = self.storage_dir / "edges" / "edges.json"
        edges_data = [edge.to_dict() for edge in self._edges.values()]
        with open(edges_file, "w", encoding="utf-8") as f:
            json.dump(edges_data, f, ensure_ascii=False, indent=2)

    # ==================== 节点操作 ====================

    def add_node(
        self,
        node_type: NodeType,
        name: str,
        description: str,
        source_path: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        node_id: Optional[str] = None,
    ) -> str:
        """添加知识节点

        Args:
            node_type: 节点类型
            name: 节点名称
            description: 节点描述
            source_path: 来源路径
            tags: 标签列表
            metadata: 元数据
            node_id: 节点ID（可选，默认自动生成）

        Returns:
            节点ID
        """
        node_id = node_id or str(uuid.uuid4())
        now = datetime.now()

        node = KnowledgeNode(
            node_id=node_id,
            node_type=node_type,
            name=name,
            description=description,
            source_path=source_path,
            tags=tags or [],
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )

        self._nodes[node_id] = node
        self._update_indexes(node)
        self._save_node(node)

        return node_id

    def get_node(self, node_id: str) -> Optional[KnowledgeNode]:
        """获取知识节点

        Args:
            node_id: 节点ID

        Returns:
            节点对象，不存在则返回None
        """
        return self._nodes.get(node_id)

    def update_node(self, node_id: str, updates: Dict[str, Any]) -> bool:
        """更新知识节点

        Args:
            node_id: 节点ID
            updates: 要更新的字段字典

        Returns:
            是否更新成功
        """
        node = self._nodes.get(node_id)
        if not node:
            return False

        # 从索引中移除旧数据
        self._remove_from_indexes(node)

        # 更新字段
        for key, value in updates.items():
            if hasattr(node, key) and key not in ("node_id", "created_at"):
                if key == "node_type" and isinstance(value, str):
                    value = NodeType(value)
                setattr(node, key, value)

        node.updated_at = datetime.now()

        # 重新添加到索引
        self._update_indexes(node)
        self._save_node(node)

        return True

    def delete_node(self, node_id: str) -> bool:
        """删除知识节点

        同时删除与该节点相关的所有边。

        Args:
            node_id: 节点ID

        Returns:
            是否删除成功
        """
        node = self._nodes.get(node_id)
        if not node:
            return False

        # 删除相关的边
        edges_to_delete = []
        for edge_id, edge in self._edges.items():
            if edge.source_id == node_id or edge.target_id == node_id:
                edges_to_delete.append(edge_id)

        for edge_id in edges_to_delete:
            self.delete_edge(edge_id)

        # 从索引中移除
        self._remove_from_indexes(node)

        # 删除节点
        del self._nodes[node_id]
        self._delete_node_file(node)

        return True

    def query_nodes(
        self,
        node_type: Optional[NodeType] = None,
        tags: Optional[List[str]] = None,
        name_pattern: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[KnowledgeNode]:
        """查询知识节点

        Args:
            node_type: 节点类型过滤
            tags: 标签过滤（包含任一标签即匹配）
            name_pattern: 名称模式（子字符串匹配）
            limit: 返回数量限制

        Returns:
            匹配的节点列表
        """
        candidates: Set[str] = set(self._nodes.keys())

        # 按类型过滤
        if node_type is not None:
            type_nodes = self._type_index.get(node_type, set())
            candidates &= type_nodes

        # 按标签过滤
        if tags:
            tag_nodes: Set[str] = set()
            for tag in tags:
                tag_nodes |= self._tag_index.get(tag, set())
            candidates &= tag_nodes

        # 获取节点并按名称过滤
        results: List[KnowledgeNode] = []
        for node_id in candidates:
            node = self._nodes[node_id]
            if name_pattern and name_pattern.lower() not in node.name.lower():
                continue
            results.append(node)

        # 按更新时间排序
        results.sort(key=lambda n: n.updated_at, reverse=True)

        # 限制数量
        if limit:
            results = results[:limit]

        return results

    # ==================== 边操作 ====================

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType,
        strength: float = 1.0,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        edge_id: Optional[str] = None,
    ) -> Optional[str]:
        """添加知识关系

        Args:
            source_id: 源节点ID
            target_id: 目标节点ID
            relation_type: 关系类型
            strength: 关系强度 (0-1)
            description: 关系描述
            metadata: 元数据
            edge_id: 边ID（可选，默认自动生成）

        Returns:
            边ID，如果源或目标节点不存在则返回None
        """
        # 验证节点存在
        if source_id not in self._nodes or target_id not in self._nodes:
            return None

        edge_id = edge_id or str(uuid.uuid4())

        edge = KnowledgeEdge(
            edge_id=edge_id,
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            strength=max(0.0, min(1.0, strength)),  # 限制在0-1范围
            description=description,
            metadata=metadata or {},
            created_at=datetime.now(),
        )

        self._edges[edge_id] = edge
        self._update_adjacency(edge)
        self._save_edges()

        return edge_id

    def get_edges(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relation_type: Optional[RelationType] = None,
    ) -> List[KnowledgeEdge]:
        """获取知识关系

        Args:
            source_id: 源节点ID过滤
            target_id: 目标节点ID过滤
            relation_type: 关系类型过滤

        Returns:
            匹配的边列表
        """
        results: List[KnowledgeEdge] = []

        for edge in self._edges.values():
            if source_id and edge.source_id != source_id:
                continue
            if target_id and edge.target_id != target_id:
                continue
            if relation_type and edge.relation_type != relation_type:
                continue
            results.append(edge)

        return results

    def delete_edge(self, edge_id: str) -> bool:
        """删除知识关系

        Args:
            edge_id: 边ID

        Returns:
            是否删除成功
        """
        edge = self._edges.get(edge_id)
        if not edge:
            return False

        self._remove_from_adjacency(edge)
        del self._edges[edge_id]
        self._save_edges()

        return True

    # ==================== 图查询 ====================

    def get_neighbors(
        self,
        node_id: str,
        relation_types: Optional[List[RelationType]] = None,
        direction: str = "both",
    ) -> List[KnowledgeNode]:
        """获取邻居节点

        Args:
            node_id: 节点ID
            relation_types: 关系类型过滤
            direction: 方向 ("out", "in", "both")

        Returns:
            邻居节点列表
        """
        if node_id not in self._nodes:
            return []

        neighbor_ids: Set[str] = set()

        # 出边邻居
        if direction in ("out", "both"):
            for edge_id in self._adjacency.get(node_id, set()):
                edge = self._edges.get(edge_id)
                if edge:
                    if relation_types is None or edge.relation_type in relation_types:
                        neighbor_ids.add(edge.target_id)

        # 入边邻居
        if direction in ("in", "both"):
            for edge_id in self._reverse_adjacency.get(node_id, set()):
                edge = self._edges.get(edge_id)
                if edge:
                    if relation_types is None or edge.relation_type in relation_types:
                        neighbor_ids.add(edge.source_id)

        return [self._nodes[nid] for nid in neighbor_ids if nid in self._nodes]

    def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
    ) -> Optional[List[KnowledgeNode]]:
        """查找两个节点之间的路径

        使用BFS查找最短路径。

        Args:
            source_id: 源节点ID
            target_id: 目标节点ID
            max_depth: 最大搜索深度

        Returns:
            路径节点列表，不存在则返回None
        """
        if source_id not in self._nodes or target_id not in self._nodes:
            return None

        if source_id == target_id:
            return [self._nodes[source_id]]

        # BFS
        visited: Set[str] = {source_id}
        queue: List[Tuple[str, List[str]]] = [(source_id, [source_id])]

        while queue:
            current_id, path = queue.pop(0)

            if len(path) > max_depth:
                continue

            # 获取所有邻居
            for edge_id in self._adjacency.get(current_id, set()):
                edge = self._edges.get(edge_id)
                if edge and edge.target_id not in visited:
                    new_path = path + [edge.target_id]
                    if edge.target_id == target_id:
                        return [self._nodes[nid] for nid in new_path]
                    visited.add(edge.target_id)
                    queue.append((edge.target_id, new_path))

        return None

    def get_related_knowledge(
        self,
        node_id: str,
        depth: int = 2,
        limit: int = 10,
    ) -> List[KnowledgeNode]:
        """获取相关知识

        通过BFS获取指定深度内的所有相关节点。

        Args:
            node_id: 节点ID
            depth: 搜索深度
            limit: 返回数量限制

        Returns:
            相关节点列表（按距离排序）
        """
        if node_id not in self._nodes:
            return []

        visited: Set[str] = {node_id}
        results: List[Tuple[int, str]] = []  # (距离, 节点ID)
        queue: List[Tuple[str, int]] = [(node_id, 0)]  # (节点ID, 距离)

        while queue:
            current_id, dist = queue.pop(0)

            if dist >= depth:
                continue

            # 获取所有邻居（双向）
            neighbor_ids: Set[str] = set()

            for edge_id in self._adjacency.get(current_id, set()):
                edge = self._edges.get(edge_id)
                if edge:
                    neighbor_ids.add(edge.target_id)

            for edge_id in self._reverse_adjacency.get(current_id, set()):
                edge = self._edges.get(edge_id)
                if edge:
                    neighbor_ids.add(edge.source_id)

            for neighbor_id in neighbor_ids:
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    results.append((dist + 1, neighbor_id))
                    queue.append((neighbor_id, dist + 1))

        # 按距离排序并限制数量
        results.sort(key=lambda x: x[0])
        return [self._nodes[nid] for _, nid in results[:limit] if nid in self._nodes]

    # ==================== 统计信息 ====================

    def get_stats(self) -> Dict[str, Any]:
        """获取图谱统计信息

        Returns:
            统计信息字典
        """
        type_counts = {}
        for node_type in NodeType:
            type_counts[node_type.value] = len(self._type_index.get(node_type, set()))

        relation_counts: Dict[str, int] = {}
        for edge in self._edges.values():
            rel_type = edge.relation_type.value
            relation_counts[rel_type] = relation_counts.get(rel_type, 0) + 1

        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "node_types": type_counts,
            "relation_types": relation_counts,
            "total_tags": len(self._tag_index),
        }
