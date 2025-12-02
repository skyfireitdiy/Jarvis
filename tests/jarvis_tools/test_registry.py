# -*- coding: utf-8 -*-
"""jarvis_tools.registry 模块单元测试"""

import pytest
from unittest.mock import MagicMock, patch

from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_tools.base import Tool


class TestToolRegistry:
    """测试 ToolRegistry 类"""

    @pytest.fixture
    def registry(self):
        """创建测试用的 ToolRegistry 实例"""
        reg = ToolRegistry()
        # 清空自动加载的工具，只测试我们注册的工具
        reg.tools.clear()
        return reg

    @pytest.fixture
    def sample_tool(self):
        """创建示例工具"""

        def tool_func(args):
            return {"success": True, "stdout": "test output", "stderr": ""}

        return Tool(
            name="test_tool",
            description="Test tool",
            parameters={"type": "object"},
            func=tool_func,
        )

    def test_init(self, registry):
        """测试初始化"""
        assert registry is not None
        assert hasattr(registry, "tools")
        assert isinstance(registry.tools, dict)

    def test_register_tool(self, registry, sample_tool):
        """测试注册工具"""
        registry.register_tool(
            sample_tool.name,
            sample_tool.description,
            sample_tool.parameters,
            sample_tool.func,
        )
        assert "test_tool" in registry.tools
        assert registry.tools["test_tool"].name == "test_tool"

    def test_get_tool_existing(self, registry, sample_tool):
        """测试获取已存在的工具"""
        registry.register_tool(
            sample_tool.name,
            sample_tool.description,
            sample_tool.parameters,
            sample_tool.func,
        )
        tool = registry.get_tool("test_tool")
        assert tool is not None
        assert tool.name == "test_tool"

    def test_get_tool_nonexistent(self, registry):
        """测试获取不存在的工具"""
        tool = registry.get_tool("nonexistent_tool")
        assert tool is None

    def test_get_all_tools(self, registry, sample_tool):
        """测试获取所有工具"""
        registry.register_tool(
            sample_tool.name,
            sample_tool.description,
            sample_tool.parameters,
            sample_tool.func,
        )
        tools = registry.get_all_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0
        # 检查工具字典格式
        tool_dict = next((t for t in tools if t["name"] == "test_tool"), None)
        assert tool_dict is not None
        assert tool_dict["name"] == "test_tool"
        assert tool_dict["description"] == "Test tool"

    @patch("jarvis.jarvis_stats.stats.StatsManager")
    def test_execute_tool_success(self, mock_stats_manager, registry, sample_tool):
        """测试成功执行工具"""
        registry.register_tool(
            sample_tool.name,
            sample_tool.description,
            sample_tool.parameters,
            sample_tool.func,
        )
        result = registry.execute_tool("test_tool", {"arg1": "value1"})
        assert result["success"] is True
        assert "stdout" in result

    def test_execute_tool_nonexistent(self, registry):
        """测试执行不存在的工具"""
        result = registry.execute_tool("nonexistent_tool", {})
        assert result["success"] is False
        assert "stderr" in result
        assert "不存在" in result["stderr"]

    @patch("jarvis.jarvis_stats.stats.StatsManager")
    def test_execute_tool_with_agent_v1(
        self, mock_stats_manager, registry, sample_tool
    ):
        """测试使用 v1.0 协议执行工具（带 agent）"""
        registry.register_tool(
            sample_tool.name,
            sample_tool.description,
            sample_tool.parameters,
            sample_tool.func,
        )
        mock_agent = MagicMock()
        result = registry.execute_tool(
            "test_tool", {"arg1": "value1"}, agent=mock_agent
        )
        assert result["success"] is True

    @patch("jarvis.jarvis_stats.stats.StatsManager")
    def test_execute_tool_with_agent_v2(self, mock_stats_manager, registry):
        """测试使用 v2.0 协议执行工具"""

        def v2_tool_func(args, agent):
            return {"success": True, "stdout": "v2 output", "stderr": ""}

        registry.register_tool(
            "v2_tool",
            "V2 tool",
            {"type": "object"},
            v2_tool_func,
            protocol_version="2.0",
        )

        mock_agent = MagicMock()
        result = registry.execute_tool("v2_tool", {"arg1": "value1"}, agent=mock_agent)
        assert result["success"] is True
        assert result["stdout"] == "v2 output"

    @patch("jarvis.jarvis_stats.stats.StatsManager")
    def test_execute_tool_exception(self, mock_stats_manager, registry):
        """测试工具执行异常"""

        def failing_tool(args):
            raise ValueError("Tool error")

        registry.register_tool(
            "failing_tool", "Failing tool", {"type": "object"}, failing_tool
        )

        result = registry.execute_tool("failing_tool", {})
        assert result["success"] is False
        assert "stderr" in result
