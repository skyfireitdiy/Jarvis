# -*- coding: utf-8 -*-
"""retrieve_memory 工具测试"""

import json
from unittest.mock import MagicMock, patch

import pytest

from jarvis.jarvis_tools.retrieve_memory import RetrieveMemoryTool


class TestRetrieveMemoryTool:
    """RetrieveMemoryTool 测试类"""

    @pytest.fixture
    def tool(self):
        """创建工具实例"""
        return RetrieveMemoryTool()

    @pytest.fixture
    def temp_memory_dir(self, tmp_path):
        """创建临时记忆目录"""
        memory_dir = tmp_path / ".jarvis" / "memory"
        memory_dir.mkdir(parents=True)
        return memory_dir

    @pytest.fixture
    def sample_memories(self, temp_memory_dir):
        """创建示例记忆文件"""
        memories = [
            {
                "id": "memory_001",
                "type": "project_long_term",
                "tags": ["python", "testing"],
                "content": "Python 测试最佳实践",
                "created_at": "2024-01-01T00:00:00Z",
            },
            {
                "id": "memory_002",
                "type": "project_long_term",
                "tags": ["architecture", "design"],
                "content": "系统架构设计文档",
                "created_at": "2024-01-02T00:00:00Z",
            },
            {
                "id": "memory_003",
                "type": "project_long_term",
                "tags": ["python", "refactoring"],
                "content": "代码重构指南",
                "created_at": "2024-01-03T00:00:00Z",
            },
        ]

        for memory in memories:
            file_path = temp_memory_dir / f"{memory['id']}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(memory, f, ensure_ascii=False)

        return memories

    def test_tool_attributes(self, tool):
        """测试工具属性"""
        assert tool.name == "retrieve_memory"
        assert "从长短期记忆系统中检索信息" in tool.description
        assert "smart_search" in tool.parameters["properties"]
        assert "query" in tool.parameters["properties"]

    def test_parameters_structure(self, tool):
        """测试参数结构"""
        params = tool.parameters
        assert params["type"] == "object"
        assert "memory_types" in params["properties"]
        assert "tags" in params["properties"]
        assert "limit" in params["properties"]
        assert "smart_search" in params["properties"]
        assert "query" in params["properties"]
        assert params["required"] == ["memory_types"]

    def test_smart_search_parameter_default(self, tool):
        """测试 smart_search 参数默认值"""
        smart_search_param = tool.parameters["properties"]["smart_search"]
        assert smart_search_param["type"] == "boolean"
        assert smart_search_param["default"] is False

    def test_retrieve_project_memories(self, tool, temp_memory_dir, sample_memories):
        """测试检索项目记忆（标签过滤模式）"""
        # 修改工具的记忆目录
        tool.project_memory_dir = temp_memory_dir

        result = tool.execute(
            {
                "memory_types": ["project_long_term"],
                "tags": ["python"],
            }
        )

        assert result["success"] is True
        assert "memory_001" in result["stdout"]
        assert "memory_003" in result["stdout"]
        # memory_002 没有 python 标签，不应该出现
        assert "memory_002" not in result["stdout"]

    def test_retrieve_all_memories(self, tool, temp_memory_dir, sample_memories):
        """测试检索所有记忆"""
        tool.project_memory_dir = temp_memory_dir

        result = tool.execute(
            {
                "memory_types": ["project_long_term"],
            }
        )

        assert result["success"] is True
        assert "memory_001" in result["stdout"]
        assert "memory_002" in result["stdout"]
        assert "memory_003" in result["stdout"]

    def test_retrieve_with_limit(self, tool, temp_memory_dir, sample_memories):
        """测试限制返回数量"""
        tool.project_memory_dir = temp_memory_dir

        result = tool.execute(
            {
                "memory_types": ["project_long_term"],
                "limit": 1,
            }
        )

        assert result["success"] is True
        # 应该只返回1条记忆（最新的）
        assert result["stdout"].count("## ") == 1

    def test_smart_search_without_query(self, tool):
        """测试智能检索模式缺少 query 参数"""
        result = tool.execute(
            {
                "memory_types": ["project_long_term"],
                "smart_search": True,
            }
        )

        assert result["success"] is False
        assert "query" in result["stderr"]

    def test_smart_search_with_short_term_only(self, tool):
        """测试智能检索模式不支持 short_term"""
        result = tool.execute(
            {
                "memory_types": ["short_term"],
                "smart_search": True,
                "query": "测试查询",
            }
        )

        assert result["success"] is False
        assert "仅支持" in result["stderr"]

    @patch("jarvis.jarvis_tools.retrieve_memory._get_smart_retriever")
    def test_smart_search_success(self, mock_get_retriever, tool):
        """测试智能检索成功"""
        # 创建模拟的 Memory 对象
        mock_memory = MagicMock()
        mock_memory.id = "smart_memory_001"
        mock_memory.type = "project_long_term"
        mock_memory.tags = ["python", "testing"]
        mock_memory.content = "智能检索测试内容"
        mock_memory.created_at = "2024-01-01T00:00:00Z"

        # 配置模拟的 SmartRetriever
        mock_retriever = MagicMock()
        mock_retriever.semantic_search.return_value = [mock_memory]
        mock_get_retriever.return_value = mock_retriever

        result = tool.execute(
            {
                "memory_types": ["project_long_term"],
                "smart_search": True,
                "query": "Python 测试",
            }
        )

        assert result["success"] is True
        assert "智能语义检索结果" in result["stdout"]
        assert "smart_memory_001" in result["stdout"]
        assert "智能检索测试内容" in result["stdout"]

        # 验证 semantic_search 被正确调用
        mock_retriever.semantic_search.assert_called_once_with(
            query="Python 测试",
            memory_types=["project_long_term"],
            limit=10,
        )

    @patch("jarvis.jarvis_tools.retrieve_memory._get_smart_retriever")
    def test_smart_search_with_all_types(self, mock_get_retriever, tool):
        """测试智能检索使用 all 类型"""
        mock_retriever = MagicMock()
        mock_retriever.semantic_search.return_value = []
        mock_get_retriever.return_value = mock_retriever

        result = tool.execute(
            {
                "memory_types": ["all"],
                "smart_search": True,
                "query": "测试查询",
            }
        )

        assert result["success"] is True
        # 验证 all 被转换为 project_long_term 和 global_long_term
        mock_retriever.semantic_search.assert_called_once_with(
            query="测试查询",
            memory_types=["project_long_term", "global_long_term"],
            limit=10,
        )

    @patch("jarvis.jarvis_tools.retrieve_memory._get_smart_retriever")
    def test_smart_search_with_limit(self, mock_get_retriever, tool):
        """测试智能检索带 limit 参数"""
        mock_retriever = MagicMock()
        mock_retriever.semantic_search.return_value = []
        mock_get_retriever.return_value = mock_retriever

        result = tool.execute(
            {
                "memory_types": ["project_long_term"],
                "smart_search": True,
                "query": "测试查询",
                "limit": 5,
            }
        )

        assert result["success"] is True
        mock_retriever.semantic_search.assert_called_once_with(
            query="测试查询",
            memory_types=["project_long_term"],
            limit=5,
        )

    @patch("jarvis.jarvis_tools.retrieve_memory._get_smart_retriever")
    def test_smart_search_exception_handling(self, mock_get_retriever, tool):
        """测试智能检索异常处理"""
        mock_retriever = MagicMock()
        mock_retriever.semantic_search.side_effect = Exception("检索错误")
        mock_get_retriever.return_value = mock_retriever

        result = tool.execute(
            {
                "memory_types": ["project_long_term"],
                "smart_search": True,
                "query": "测试查询",
            }
        )

        assert result["success"] is False
        assert "智能检索失败" in result["stderr"]

    def test_backward_compatibility_default_mode(
        self, tool, temp_memory_dir, sample_memories
    ):
        """测试向后兼容性 - 默认模式"""
        tool.project_memory_dir = temp_memory_dir

        # 不传 smart_search 参数，应该使用标签过滤模式
        result = tool.execute(
            {
                "memory_types": ["project_long_term"],
                "tags": ["architecture"],
            }
        )

        assert result["success"] is True
        assert "memory_002" in result["stdout"]
        # 不应该出现 "智能语义检索" 字样
        assert "智能语义检索" not in result["stdout"]

    def test_backward_compatibility_explicit_false(
        self, tool, temp_memory_dir, sample_memories
    ):
        """测试向后兼容性 - 显式设置 smart_search=False"""
        tool.project_memory_dir = temp_memory_dir

        result = tool.execute(
            {
                "memory_types": ["project_long_term"],
                "tags": ["design"],
                "smart_search": False,
            }
        )

        assert result["success"] is True
        assert "memory_002" in result["stdout"]
        assert "智能语义检索" not in result["stdout"]

    def test_empty_memory_directory(self, tool, tmp_path):
        """测试空记忆目录"""
        empty_dir = tmp_path / ".jarvis" / "memory"
        empty_dir.mkdir(parents=True)
        tool.project_memory_dir = empty_dir

        result = tool.execute(
            {
                "memory_types": ["project_long_term"],
            }
        )

        assert result["success"] is True
        assert "检索到 0 条记忆" in result["stdout"]

    def test_nonexistent_memory_directory(self, tool, tmp_path):
        """测试不存在的记忆目录"""
        tool.project_memory_dir = tmp_path / "nonexistent" / "memory"

        result = tool.execute(
            {
                "memory_types": ["project_long_term"],
            }
        )

        assert result["success"] is True
        assert "检索到 0 条记忆" in result["stdout"]
