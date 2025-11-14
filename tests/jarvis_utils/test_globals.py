# -*- coding: utf-8 -*-
"""jarvis_utils.globals 模块单元测试"""


from jarvis.jarvis_utils.globals import make_agent_name, global_agents


class TestMakeAgentName:
    """测试 make_agent_name 函数"""

    def test_unique_name(self):
        """测试唯一名称"""
        # 清空全局代理字典
        global_agents.clear()
        
        name = make_agent_name("test_agent")
        assert name == "test_agent"
        # make_agent_name 只生成名称，不会自动添加到 global_agents

    def test_duplicate_name(self):
        """测试重复名称"""
        global_agents.clear()
        
        # 添加第一个代理
        global_agents["test_agent"] = {}
        
        # 创建同名代理，应该自动添加后缀
        name = make_agent_name("test_agent")
        assert name == "test_agent_1"
        # make_agent_name 只生成名称，不会自动添加到 global_agents

    def test_multiple_duplicates(self):
        """测试多个重复名称"""
        global_agents.clear()
        
        # 添加多个代理
        global_agents["test_agent"] = {}
        global_agents["test_agent_1"] = {}
        global_agents["test_agent_2"] = {}
        
        # 创建同名代理，应该找到下一个可用编号
        name = make_agent_name("test_agent")
        assert name == "test_agent_3"
        # make_agent_name 只生成名称，不会自动添加到 global_agents

    def test_existing_with_suffix(self):
        """测试已存在带后缀的名称"""
        global_agents.clear()
        
        global_agents["test_agent"] = {}
        global_agents["test_agent_1"] = {}
        # 跳过 test_agent_2
        global_agents["test_agent_3"] = {}
        
        # 应该找到 test_agent_2
        name = make_agent_name("test_agent")
        assert name == "test_agent_2"
        # make_agent_name 只生成名称，不会自动添加到 global_agents

