# -*- coding: utf-8 -*-
"""jarvis_mcp 模块单元测试"""

import pytest

from jarvis.jarvis_mcp import McpClient


class TestMcpClient:
    """测试 McpClient 抽象基类"""

    def test_abstract_class_cannot_instantiate(self):
        """测试抽象类不能直接实例化"""
        with pytest.raises(TypeError):
            McpClient()

    def test_abstract_methods(self):
        """测试抽象方法"""
        # 创建一个未实现所有抽象方法的类
        class IncompleteMcpClient(McpClient):
            def get_tool_list(self):
                return []
        
        # 应该不能实例化，因为缺少其他抽象方法
        with pytest.raises(TypeError):
            IncompleteMcpClient()

    def test_complete_implementation(self):
        """测试完整实现"""
        class CompleteMcpClient(McpClient):
            def get_tool_list(self):
                return []
            
            def execute(self, tool_name: str, arguments: dict):
                return {"success": True, "stdout": "", "stderr": ""}
            
            def get_resource_list(self):
                return []
            
            def get_resource(self, uri: str):
                return {}
        
        # 完整实现应该可以实例化
        client = CompleteMcpClient()
        assert client is not None
        assert isinstance(client, McpClient)

