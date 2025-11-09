# -*- coding: utf-8 -*-
"""jarvis_tools.base 模块单元测试"""

import pytest
from unittest.mock import MagicMock

from jarvis.jarvis_tools.base import Tool


class TestTool:
    """测试 Tool 类"""

    def test_init(self):
        """测试 Tool 初始化"""
        def test_func(args):
            return {"success": True, "stdout": "test"}

        tool = Tool(
            name="test_tool",
            description="Test tool",
            parameters={"type": "object"},
            func=test_func,
        )

        assert tool.name == "test_tool"
        assert tool.description == "Test tool"
        assert tool.parameters == {"type": "object"}
        assert tool.func == test_func
        assert tool.protocol_version == "1.0"

    def test_init_with_protocol_version(self):
        """测试带协议版本的初始化"""
        def test_func(args):
            return {"success": True}

        tool = Tool(
            name="test_tool",
            description="Test tool",
            parameters={"type": "object"},
            func=test_func,
            protocol_version="2.0",
        )

        assert tool.protocol_version == "2.0"

    def test_to_dict(self):
        """测试 to_dict 方法"""
        def test_func(args):
            return {"success": True}

        tool = Tool(
            name="test_tool",
            description="Test tool",
            parameters={"type": "object", "properties": {"arg1": {"type": "string"}}},
            func=test_func,
        )

        result = tool.to_dict()
        assert result["name"] == "test_tool"
        assert result["description"] == "Test tool"
        assert "parameters" in result
        # 验证 parameters 是 JSON 字符串
        import json
        params = json.loads(result["parameters"])
        assert params["type"] == "object"

    def test_execute_success(self):
        """测试 execute 方法成功执行"""
        def test_func(args):
            return {"success": True, "stdout": "test output", "stderr": ""}

        tool = Tool(
            name="test_tool",
            description="Test tool",
            parameters={"type": "object"},
            func=test_func,
        )

        result = tool.execute({"arg1": "value1"})
        assert result["success"] is True
        assert result["stdout"] == "test output"

    def test_execute_with_exception(self):
        """测试 execute 方法处理异常"""
        def test_func(args):
            raise ValueError("Test error")

        tool = Tool(
            name="test_tool",
            description="Test tool",
            parameters={"type": "object"},
            func=test_func,
        )

        result = tool.execute({"arg1": "value1"})
        assert result["success"] is False
        assert "stderr" in result
        assert "执行失败" in result["stderr"]
        assert "Test error" in result["stderr"]

    def test_execute_with_empty_arguments(self):
        """测试使用空参数执行"""
        def test_func(args):
            return {"success": True, "stdout": "empty", "stderr": ""}

        tool = Tool(
            name="test_tool",
            description="Test tool",
            parameters={"type": "object"},
            func=test_func,
        )

        result = tool.execute({})
        assert result["success"] is True

