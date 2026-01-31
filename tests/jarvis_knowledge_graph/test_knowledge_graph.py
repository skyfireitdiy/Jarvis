"""知识图谱模块单元测试"""

import tempfile

import pytest

from jarvis.jarvis_knowledge_graph import (
    KnowledgeEdge,
    KnowledgeGraph,
    KnowledgeNode,
    NodeType,
    RelationType,
)


class TestNodeType:
    """测试节点类型枚举"""

    def test_node_types_exist(self):
        assert NodeType.METHODOLOGY.value == "methodology"
        assert NodeType.RULE.value == "rule"
        assert NodeType.MEMORY.value == "memory"

    def test_node_type_from_string(self):
        assert NodeType("methodology") == NodeType.METHODOLOGY


class TestRelationType:
    """测试关系类型枚举"""

    def test_relation_types_exist(self):
        assert RelationType.REFERENCES.value == "references"
        assert RelationType.DEPENDS_ON.value == "depends_on"


class TestKnowledgeNode:
    """测试知识节点数据类"""

    def test_node_creation(self):
        node = KnowledgeNode(
            node_id="test-1",
            node_type=NodeType.METHODOLOGY,
            name="测试方法论",
            description="这是一个测试方法论",
            tags=["test", "methodology"],
        )
        assert node.node_id == "test-1"
        assert node.node_type == NodeType.METHODOLOGY

    def test_node_to_dict(self):
        node = KnowledgeNode(
            node_id="test-1",
            node_type=NodeType.RULE,
            name="测试规则",
            description="描述",
        )
        data = node.to_dict()
        assert data["node_id"] == "test-1"
        assert data["node_type"] == "rule"

    def test_node_from_dict(self):
        data = {
            "node_id": "test-2",
            "node_type": "memory",
            "name": "测试记忆",
            "description": "描述",
            "source_path": "/path/to/file",
            "tags": ["tag1"],
            "metadata": {"key": "value"},
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
        }
        node = KnowledgeNode.from_dict(data)
        assert node.node_id == "test-2"
        assert node.node_type == NodeType.MEMORY


class TestKnowledgeEdge:
    """测试知识关系数据类"""

    def test_edge_creation(self):
        edge = KnowledgeEdge(
            edge_id="edge-1",
            source_id="node-1",
            target_id="node-2",
            relation_type=RelationType.REFERENCES,
            strength=0.8,
        )
        assert edge.edge_id == "edge-1"
        assert edge.strength == 0.8

    def test_edge_to_dict(self):
        edge = KnowledgeEdge(
            edge_id="edge-1",
            source_id="node-1",
            target_id="node-2",
            relation_type=RelationType.DEPENDS_ON,
        )
        data = edge.to_dict()
        assert data["relation_type"] == "depends_on"

    def test_edge_from_dict(self):
        data = {
            "edge_id": "edge-2",
            "source_id": "node-a",
            "target_id": "node-b",
            "relation_type": "similar_to",
            "strength": 0.5,
            "description": "相似关系",
            "metadata": {},
            "created_at": "2024-01-01T00:00:00",
        }
        edge = KnowledgeEdge.from_dict(data)
        assert edge.edge_id == "edge-2"
        assert edge.relation_type == RelationType.SIMILAR_TO


class TestKnowledgeGraph:
    """测试知识图谱管理类"""

    @pytest.fixture
    def temp_storage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def graph(self, temp_storage):
        return KnowledgeGraph(storage_dir=temp_storage)

    # 节点操作测试
    def test_add_node(self, graph):
        node_id = graph.add_node(
            node_type=NodeType.METHODOLOGY,
            name="测试方法论",
            description="这是一个测试",
            tags=["test"],
        )
        assert node_id is not None
        node = graph.get_node(node_id)
        assert node is not None
        assert node.name == "测试方法论"

    def test_add_node_with_custom_id(self, graph):
        node_id = graph.add_node(
            node_type=NodeType.RULE,
            name="自定义ID规则",
            description="描述",
            node_id="custom-id-123",
        )
        assert node_id == "custom-id-123"

    def test_get_node_not_found(self, graph):
        node = graph.get_node("non-existent")
        assert node is None

    def test_update_node(self, graph):
        node_id = graph.add_node(
            node_type=NodeType.CONCEPT,
            name="原始名称",
            description="原始描述",
        )
        result = graph.update_node(node_id, {"name": "新名称"})
        assert result is True
        node = graph.get_node(node_id)
        assert node.name == "新名称"

    def test_update_node_not_found(self, graph):
        result = graph.update_node("non-existent", {"name": "新名称"})
        assert result is False

    def test_delete_node(self, graph):
        node_id = graph.add_node(
            node_type=NodeType.FILE,
            name="待删除文件",
            description="描述",
        )
        result = graph.delete_node(node_id)
        assert result is True
        assert graph.get_node(node_id) is None

    def test_delete_node_with_edges(self, graph):
        node1_id = graph.add_node(
            node_type=NodeType.CODE,
            name="代码1",
            description="描述",
        )
        node2_id = graph.add_node(
            node_type=NodeType.CODE,
            name="代码2",
            description="描述",
        )
        edge_id = graph.add_edge(
            source_id=node1_id,
            target_id=node2_id,
            relation_type=RelationType.DEPENDS_ON,
        )
        assert edge_id is not None
        graph.delete_node(node1_id)
        edges = graph.get_edges(source_id=node1_id)
        assert len(edges) == 0

    def test_delete_node_not_found(self, graph):
        result = graph.delete_node("non-existent")
        assert result is False

    def test_query_nodes_by_type(self, graph):
        graph.add_node(
            node_type=NodeType.METHODOLOGY, name="方法论1", description="描述"
        )
        graph.add_node(
            node_type=NodeType.METHODOLOGY, name="方法论2", description="描述"
        )
        graph.add_node(node_type=NodeType.RULE, name="规则1", description="描述")
        results = graph.query_nodes(node_type=NodeType.METHODOLOGY)
        assert len(results) == 2

    def test_query_nodes_by_tags(self, graph):
        graph.add_node(
            node_type=NodeType.CONCEPT,
            name="概念1",
            description="描述",
            tags=["python", "coding"],
        )
        graph.add_node(
            node_type=NodeType.CONCEPT,
            name="概念2",
            description="描述",
            tags=["java", "coding"],
        )
        graph.add_node(
            node_type=NodeType.CONCEPT,
            name="概念3",
            description="描述",
            tags=["design"],
        )
        results = graph.query_nodes(tags=["coding"])
        assert len(results) == 2

    def test_query_nodes_by_name_pattern(self, graph):
        graph.add_node(node_type=NodeType.RULE, name="代码审查规则", description="描述")
        graph.add_node(node_type=NodeType.RULE, name="安全规则", description="描述")
        results = graph.query_nodes(name_pattern="代码")
        assert len(results) == 1

    def test_query_nodes_with_limit(self, graph):
        for i in range(5):
            graph.add_node(
                node_type=NodeType.MEMORY, name=f"记忆{i}", description="描述"
            )
        results = graph.query_nodes(node_type=NodeType.MEMORY, limit=3)
        assert len(results) == 3

    # 边操作测试
    def test_add_edge(self, graph):
        node1_id = graph.add_node(
            node_type=NodeType.METHODOLOGY, name="方法论", description="描述"
        )
        node2_id = graph.add_node(
            node_type=NodeType.RULE, name="规则", description="描述"
        )
        edge_id = graph.add_edge(
            source_id=node1_id,
            target_id=node2_id,
            relation_type=RelationType.REFERENCES,
            strength=0.9,
        )
        assert edge_id is not None
        edges = graph.get_edges(source_id=node1_id)
        assert len(edges) == 1
        assert edges[0].strength == 0.9

    def test_add_edge_invalid_nodes(self, graph):
        node_id = graph.add_node(
            node_type=NodeType.CODE, name="代码", description="描述"
        )
        edge_id = graph.add_edge(
            source_id=node_id,
            target_id="non-existent",
            relation_type=RelationType.DEPENDS_ON,
        )
        assert edge_id is None

    def test_add_edge_strength_clamping(self, graph):
        node1_id = graph.add_node(
            node_type=NodeType.CONCEPT, name="概念1", description="描述"
        )
        node2_id = graph.add_node(
            node_type=NodeType.CONCEPT, name="概念2", description="描述"
        )
        graph.add_edge(
            source_id=node1_id,
            target_id=node2_id,
            relation_type=RelationType.SIMILAR_TO,
            strength=1.5,
        )
        edges = graph.get_edges(source_id=node1_id)
        assert edges[0].strength == 1.0

    def test_get_edges_by_relation_type(self, graph):
        node1_id = graph.add_node(
            node_type=NodeType.CODE, name="代码1", description="描述"
        )
        node2_id = graph.add_node(
            node_type=NodeType.CODE, name="代码2", description="描述"
        )
        node3_id = graph.add_node(
            node_type=NodeType.CODE, name="代码3", description="描述"
        )
        graph.add_edge(
            source_id=node1_id,
            target_id=node2_id,
            relation_type=RelationType.DEPENDS_ON,
        )
        graph.add_edge(
            source_id=node1_id,
            target_id=node3_id,
            relation_type=RelationType.SIMILAR_TO,
        )
        edges = graph.get_edges(relation_type=RelationType.DEPENDS_ON)
        assert len(edges) == 1

    def test_delete_edge(self, graph):
        node1_id = graph.add_node(
            node_type=NodeType.FILE, name="文件1", description="描述"
        )
        node2_id = graph.add_node(
            node_type=NodeType.FILE, name="文件2", description="描述"
        )
        edge_id = graph.add_edge(
            source_id=node1_id, target_id=node2_id, relation_type=RelationType.PART_OF
        )
        result = graph.delete_edge(edge_id)
        assert result is True
        assert len(graph.get_edges(source_id=node1_id)) == 0

    def test_delete_edge_not_found(self, graph):
        result = graph.delete_edge("non-existent")
        assert result is False

    # 图查询测试
    def test_get_neighbors_out(self, graph):
        node1_id = graph.add_node(
            node_type=NodeType.METHODOLOGY, name="方法论", description="描述"
        )
        node2_id = graph.add_node(
            node_type=NodeType.RULE, name="规则1", description="描述"
        )
        node3_id = graph.add_node(
            node_type=NodeType.RULE, name="规则2", description="描述"
        )
        graph.add_edge(
            source_id=node1_id,
            target_id=node2_id,
            relation_type=RelationType.REFERENCES,
        )
        graph.add_edge(
            source_id=node1_id,
            target_id=node3_id,
            relation_type=RelationType.REFERENCES,
        )
        neighbors = graph.get_neighbors(node1_id, direction="out")
        assert len(neighbors) == 2

    def test_get_neighbors_in(self, graph):
        node1_id = graph.add_node(
            node_type=NodeType.RULE, name="规则", description="描述"
        )
        node2_id = graph.add_node(
            node_type=NodeType.METHODOLOGY, name="方法论1", description="描述"
        )
        node3_id = graph.add_node(
            node_type=NodeType.METHODOLOGY, name="方法论2", description="描述"
        )
        graph.add_edge(
            source_id=node2_id,
            target_id=node1_id,
            relation_type=RelationType.REFERENCES,
        )
        graph.add_edge(
            source_id=node3_id,
            target_id=node1_id,
            relation_type=RelationType.REFERENCES,
        )
        neighbors = graph.get_neighbors(node1_id, direction="in")
        assert len(neighbors) == 2

    def test_get_neighbors_with_relation_filter(self, graph):
        node1_id = graph.add_node(
            node_type=NodeType.CODE, name="代码", description="描述"
        )
        node2_id = graph.add_node(
            node_type=NodeType.CODE, name="依赖代码", description="描述"
        )
        node3_id = graph.add_node(
            node_type=NodeType.CODE, name="相似代码", description="描述"
        )
        graph.add_edge(
            source_id=node1_id,
            target_id=node2_id,
            relation_type=RelationType.DEPENDS_ON,
        )
        graph.add_edge(
            source_id=node1_id,
            target_id=node3_id,
            relation_type=RelationType.SIMILAR_TO,
        )
        neighbors = graph.get_neighbors(
            node1_id, relation_types=[RelationType.DEPENDS_ON], direction="out"
        )
        assert len(neighbors) == 1
        assert neighbors[0].name == "依赖代码"

    def test_get_neighbors_not_found(self, graph):
        neighbors = graph.get_neighbors("non-existent")
        assert len(neighbors) == 0

    def test_find_path(self, graph):
        node_a = graph.add_node(
            node_type=NodeType.CONCEPT, name="A", description="描述"
        )
        node_b = graph.add_node(
            node_type=NodeType.CONCEPT, name="B", description="描述"
        )
        node_c = graph.add_node(
            node_type=NodeType.CONCEPT, name="C", description="描述"
        )
        node_d = graph.add_node(
            node_type=NodeType.CONCEPT, name="D", description="描述"
        )
        graph.add_edge(
            source_id=node_a, target_id=node_b, relation_type=RelationType.RELATED_TO
        )
        graph.add_edge(
            source_id=node_b, target_id=node_c, relation_type=RelationType.RELATED_TO
        )
        graph.add_edge(
            source_id=node_c, target_id=node_d, relation_type=RelationType.RELATED_TO
        )
        path = graph.find_path(node_a, node_d)
        assert path is not None
        assert len(path) == 4
        assert path[0].name == "A"
        assert path[-1].name == "D"

    def test_find_path_same_node(self, graph):
        node_id = graph.add_node(
            node_type=NodeType.CONCEPT, name="节点", description="描述"
        )
        path = graph.find_path(node_id, node_id)
        assert path is not None
        assert len(path) == 1

    def test_find_path_not_found(self, graph):
        node1_id = graph.add_node(
            node_type=NodeType.CONCEPT, name="孤立节点1", description="描述"
        )
        node2_id = graph.add_node(
            node_type=NodeType.CONCEPT, name="孤立节点2", description="描述"
        )
        path = graph.find_path(node1_id, node2_id)
        assert path is None

    def test_find_path_invalid_nodes(self, graph):
        node_id = graph.add_node(
            node_type=NodeType.CONCEPT, name="节点", description="描述"
        )
        path = graph.find_path("non-existent", node_id)
        assert path is None

    def test_get_related_knowledge(self, graph):
        center = graph.add_node(
            node_type=NodeType.METHODOLOGY, name="中心方法论", description="描述"
        )
        related1 = graph.add_node(
            node_type=NodeType.RULE, name="相关规则1", description="描述"
        )
        related2 = graph.add_node(
            node_type=NodeType.RULE, name="相关规则2", description="描述"
        )
        distant = graph.add_node(
            node_type=NodeType.CONCEPT, name="远距离概念", description="描述"
        )
        graph.add_edge(
            source_id=center, target_id=related1, relation_type=RelationType.REFERENCES
        )
        graph.add_edge(
            source_id=center, target_id=related2, relation_type=RelationType.REFERENCES
        )
        graph.add_edge(
            source_id=related1, target_id=distant, relation_type=RelationType.RELATED_TO
        )
        related = graph.get_related_knowledge(center, depth=1)
        assert len(related) == 2
        related = graph.get_related_knowledge(center, depth=2)
        assert len(related) == 3

    def test_get_related_knowledge_with_limit(self, graph):
        center = graph.add_node(
            node_type=NodeType.CONCEPT, name="中心", description="描述"
        )
        for i in range(5):
            related = graph.add_node(
                node_type=NodeType.CONCEPT, name=f"相关{i}", description="描述"
            )
            graph.add_edge(
                source_id=center,
                target_id=related,
                relation_type=RelationType.RELATED_TO,
            )
        related = graph.get_related_knowledge(center, depth=1, limit=3)
        assert len(related) == 3

    def test_get_related_knowledge_not_found(self, graph):
        related = graph.get_related_knowledge("non-existent")
        assert len(related) == 0

    # 持久化测试
    def test_persistence(self, temp_storage):
        graph1 = KnowledgeGraph(storage_dir=temp_storage)
        node1_id = graph1.add_node(
            node_type=NodeType.METHODOLOGY,
            name="持久化测试方法论",
            description="描述",
            tags=["persistence", "test"],
        )
        node2_id = graph1.add_node(
            node_type=NodeType.RULE, name="持久化测试规则", description="描述"
        )
        graph1.add_edge(
            source_id=node1_id,
            target_id=node2_id,
            relation_type=RelationType.REFERENCES,
        )

        # 创建新实例，验证数据持久化
        graph2 = KnowledgeGraph(storage_dir=temp_storage)
        node = graph2.get_node(node1_id)
        assert node is not None
        assert node.name == "持久化测试方法论"
        edges = graph2.get_edges(source_id=node1_id)
        assert len(edges) == 1

    def test_get_stats(self, graph):
        graph.add_node(
            node_type=NodeType.METHODOLOGY, name="方法论", description="描述"
        )
        graph.add_node(node_type=NodeType.RULE, name="规则", description="描述")
        node1 = graph.add_node(
            node_type=NodeType.CODE, name="代码1", description="描述"
        )
        node2 = graph.add_node(
            node_type=NodeType.CODE, name="代码2", description="描述"
        )
        graph.add_edge(
            source_id=node1, target_id=node2, relation_type=RelationType.DEPENDS_ON
        )
        stats = graph.get_stats()
        assert stats["total_nodes"] == 4
        assert stats["total_edges"] == 1
        assert stats["node_types"]["methodology"] == 1
        assert stats["node_types"]["code"] == 2
