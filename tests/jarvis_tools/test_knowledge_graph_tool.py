# -*- coding: utf-8 -*-
"""知识图谱工具单元测试"""

import os
import shutil
import tempfile
import pytest

from jarvis.jarvis_tools.knowledge_graph_tool import KnowledgeGraphTool


class TestKnowledgeGraphTool:
    """知识图谱工具测试类"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前设置"""
        # 创建临时目录
        self.temp_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.temp_dir)

        # 创建工具实例
        self.tool = KnowledgeGraphTool()

        yield

        # 清理
        os.chdir(self.original_dir)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_tool_attributes(self):
        """测试工具属性"""
        assert self.tool.name == "knowledge_graph_tool"
        assert "知识图谱" in self.tool.description
        assert "operation" in self.tool.parameters["properties"]
        assert "operation" in self.tool.parameters["required"]

    def test_missing_operation(self):
        """测试缺少operation参数"""
        result = self.tool.execute({})
        assert result["success"] is False
        assert "operation" in result["stderr"]

    def test_invalid_operation(self):
        """测试无效的操作类型"""
        result = self.tool.execute({"operation": "invalid_op"})
        assert result["success"] is False
        assert "不支持的操作类型" in result["stderr"]

    def test_add_node_missing_params(self):
        """测试添加节点缺少参数"""
        # 缺少node_type
        result = self.tool.execute({"operation": "add_node"})
        assert result["success"] is False
        assert "node_type" in result["stderr"]

        # 缺少name
        result = self.tool.execute({"operation": "add_node", "node_type": "concept"})
        assert result["success"] is False
        assert "name" in result["stderr"]

        # 缺少description
        result = self.tool.execute(
            {"operation": "add_node", "node_type": "concept", "name": "test"}
        )
        assert result["success"] is False
        assert "description" in result["stderr"]

    def test_add_node_invalid_type(self):
        """测试添加节点无效类型"""
        result = self.tool.execute(
            {
                "operation": "add_node",
                "node_type": "invalid_type",
                "name": "test",
                "description": "test desc",
            }
        )
        assert result["success"] is False
        assert "无效的节点类型" in result["stderr"]

    def test_add_node_success(self):
        """测试成功添加节点"""
        result = self.tool.execute(
            {
                "operation": "add_node",
                "node_type": "concept",
                "name": "测试概念",
                "description": "这是一个测试概念",
                "tags": ["test", "concept"],
            }
        )
        assert result["success"] is True
        assert "节点添加成功" in result["stdout"]
        assert "节点ID" in result["stdout"]

    def test_query_nodes_empty(self):
        """测试查询空结果"""
        result = self.tool.execute({"operation": "query_nodes", "node_type": "concept"})
        assert result["success"] is True
        assert "未找到" in result["stdout"]

    def test_query_nodes_invalid_type(self):
        """测试查询无效类型"""
        result = self.tool.execute(
            {"operation": "query_nodes", "node_type": "invalid_type"}
        )
        assert result["success"] is False
        assert "无效的节点类型" in result["stderr"]

    def test_query_nodes_success(self):
        """测试成功查询节点"""
        # 先添加节点
        self.tool.execute(
            {
                "operation": "add_node",
                "node_type": "concept",
                "name": "查询测试",
                "description": "用于查询测试的节点",
                "tags": ["query", "test"],
            }
        )

        # 查询节点
        result = self.tool.execute({"operation": "query_nodes", "node_type": "concept"})
        assert result["success"] is True
        assert "查询测试" in result["stdout"]

    def test_add_edge_missing_params(self):
        """测试添加关系缺少参数"""
        # 缺少source_id
        result = self.tool.execute({"operation": "add_edge"})
        assert result["success"] is False
        assert "source_id" in result["stderr"]

        # 缺少target_id
        result = self.tool.execute({"operation": "add_edge", "source_id": "id1"})
        assert result["success"] is False
        assert "target_id" in result["stderr"]

        # 缺少relation_type
        result = self.tool.execute(
            {"operation": "add_edge", "source_id": "id1", "target_id": "id2"}
        )
        assert result["success"] is False
        assert "relation_type" in result["stderr"]

    def test_add_edge_invalid_relation_type(self):
        """测试添加关系无效类型"""
        result = self.tool.execute(
            {
                "operation": "add_edge",
                "source_id": "id1",
                "target_id": "id2",
                "relation_type": "invalid_relation",
            }
        )
        assert result["success"] is False
        assert "无效的关系类型" in result["stderr"]

    def test_add_edge_node_not_exist(self):
        """测试添加关系节点不存在"""
        result = self.tool.execute(
            {
                "operation": "add_edge",
                "source_id": "nonexistent1",
                "target_id": "nonexistent2",
                "relation_type": "related_to",
            }
        )
        assert result["success"] is False
        assert "不存在" in result["stderr"]

    def test_add_edge_success(self):
        """测试成功添加关系"""
        # 先添加两个节点
        result1 = self.tool.execute(
            {
                "operation": "add_node",
                "node_type": "concept",
                "name": "节点A",
                "description": "源节点",
            }
        )
        # 从输出中提取节点ID
        node_id_1 = None
        for line in result1["stdout"].split("\n"):
            if "节点ID:" in line:
                node_id_1 = line.split(":")[1].strip()
                break

        result2 = self.tool.execute(
            {
                "operation": "add_node",
                "node_type": "concept",
                "name": "节点B",
                "description": "目标节点",
            }
        )
        node_id_2 = None
        for line in result2["stdout"].split("\n"):
            if "节点ID:" in line:
                node_id_2 = line.split(":")[1].strip()
                break

        # 添加关系
        result = self.tool.execute(
            {
                "operation": "add_edge",
                "source_id": node_id_1,
                "target_id": node_id_2,
                "relation_type": "related_to",
            }
        )
        assert result["success"] is True
        assert "关系添加成功" in result["stdout"]

    def test_get_related_missing_node_id(self):
        """测试获取相关知识缺少node_id"""
        result = self.tool.execute({"operation": "get_related"})
        assert result["success"] is False
        assert "node_id" in result["stderr"]

    def test_get_related_node_not_exist(self):
        """测试获取相关知识节点不存在"""
        result = self.tool.execute(
            {"operation": "get_related", "node_id": "nonexistent"}
        )
        assert result["success"] is False
        assert "不存在" in result["stderr"]

    def test_get_related_no_relations(self):
        """测试获取相关知识无关联"""
        # 先添加节点
        result = self.tool.execute(
            {
                "operation": "add_node",
                "node_type": "concept",
                "name": "孤立节点",
                "description": "没有关联的节点",
            }
        )
        node_id = None
        for line in result["stdout"].split("\n"):
            if "节点ID:" in line:
                node_id = line.split(":")[1].strip()
                break

        # 获取相关知识
        result = self.tool.execute({"operation": "get_related", "node_id": node_id})
        assert result["success"] is True
        assert "没有相关知识" in result["stdout"]

    def test_get_related_success(self):
        """测试成功获取相关知识"""
        # 添加两个节点并建立关系
        result1 = self.tool.execute(
            {
                "operation": "add_node",
                "node_type": "concept",
                "name": "中心节点",
                "description": "中心节点描述",
            }
        )
        node_id_1 = None
        for line in result1["stdout"].split("\n"):
            if "节点ID:" in line:
                node_id_1 = line.split(":")[1].strip()
                break

        result2 = self.tool.execute(
            {
                "operation": "add_node",
                "node_type": "concept",
                "name": "相关节点",
                "description": "相关节点描述",
            }
        )
        node_id_2 = None
        for line in result2["stdout"].split("\n"):
            if "节点ID:" in line:
                node_id_2 = line.split(":")[1].strip()
                break

        # 添加关系
        self.tool.execute(
            {
                "operation": "add_edge",
                "source_id": node_id_1,
                "target_id": node_id_2,
                "relation_type": "related_to",
            }
        )

        # 获取相关知识
        result = self.tool.execute({"operation": "get_related", "node_id": node_id_1})
        assert result["success"] is True
        assert "相关节点" in result["stdout"]

    def test_all_node_types(self):
        """测试所有节点类型"""
        node_types = ["methodology", "rule", "memory", "code", "file", "concept"]
        for node_type in node_types:
            result = self.tool.execute(
                {
                    "operation": "add_node",
                    "node_type": node_type,
                    "name": f"测试{node_type}",
                    "description": f"测试{node_type}节点",
                }
            )
            assert result["success"] is True, f"添加{node_type}节点失败"

    def test_all_relation_types(self):
        """测试所有关系类型"""
        relation_types = [
            "references",
            "depends_on",
            "similar_to",
            "derived_from",
            "implements",
            "related_to",
            "part_of",
            "supersedes",
        ]

        # 先添加两个节点
        result1 = self.tool.execute(
            {
                "operation": "add_node",
                "node_type": "concept",
                "name": "源节点",
                "description": "源节点描述",
            }
        )
        node_id_1 = None
        for line in result1["stdout"].split("\n"):
            if "节点ID:" in line:
                node_id_1 = line.split(":")[1].strip()
                break

        result2 = self.tool.execute(
            {
                "operation": "add_node",
                "node_type": "concept",
                "name": "目标节点",
                "description": "目标节点描述",
            }
        )
        node_id_2 = None
        for line in result2["stdout"].split("\n"):
            if "节点ID:" in line:
                node_id_2 = line.split(":")[1].strip()
                break

        # 测试所有关系类型
        for relation_type in relation_types:
            result = self.tool.execute(
                {
                    "operation": "add_edge",
                    "source_id": node_id_1,
                    "target_id": node_id_2,
                    "relation_type": relation_type,
                }
            )
            assert result["success"] is True, f"添加{relation_type}关系失败"
