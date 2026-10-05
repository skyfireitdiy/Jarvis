# -*- coding: utf-8 -*-
"""主动建议机制单元测试"""

from unittest.mock import MagicMock

from jarvis.jarvis_agent import Agent


class TestGenerateProactiveSuggestions:
    """测试 Agent._generate_proactive_suggestions 方法"""

    def _make_agent(self, executed_tools=None, memory_tags=None):
        """创建一个模拟 Agent 实例（使用 object.__new__ 避免完整初始化）"""
        agent = object.__new__(Agent)
        agent.get_user_data = MagicMock(
            return_value=executed_tools if executed_tools is not None else []
        )
        agent.get_memory_tags = MagicMock(return_value=memory_tags or [])
        return agent

    def test_no_tools_returns_empty(self):
        """未执行任何工具时返回空字符串"""
        agent = self._make_agent(executed_tools=[])
        assert agent._generate_proactive_suggestions() == ""

    def test_edit_file_suggests_testing(self):
        """修改代码后建议运行测试验证"""
        agent = self._make_agent(executed_tools=["edit_file"])
        result = agent._generate_proactive_suggestions()
        assert "主动建议" in result
        assert "测试" in result

    def test_execute_script_suggests_check_output(self):
        """执行脚本后建议检查输出"""
        agent = self._make_agent(executed_tools=["execute_script"])
        result = agent._generate_proactive_suggestions()
        assert "主动建议" in result
        assert "输出" in result

    def test_read_only_suggests_implementation(self):
        """仅读取代码未修改时提示可进入实现阶段"""
        agent = self._make_agent(executed_tools=["read_code"])
        result = agent._generate_proactive_suggestions()
        assert "主动建议" in result
        assert "分析" in result

    def test_read_and_edit_no_implementation_suggestion(self):
        """既读取又修改时不提示'仅分析'"""
        agent = self._make_agent(executed_tools=["read_code", "edit_file"])
        result = agent._generate_proactive_suggestions()
        assert "仅" not in result
        assert "测试" in result

    def test_multi_step_suggests_memory(self):
        """多步骤任务建议沉淀为方法论"""
        agent = self._make_agent(
            executed_tools=["read_code", "edit_file", "execute_script"]
        )
        result = agent._generate_proactive_suggestions()
        assert "沉淀" in result

    def test_memory_tags_suggests_retrieval(self):
        """有记忆标签时建议检索相关记忆"""
        agent = self._make_agent(
            executed_tools=["edit_file"], memory_tags=["测试", "重构"]
        )
        result = agent._generate_proactive_suggestions()
        assert "记忆" in result

    def test_exception_returns_empty(self):
        """异常时返回空字符串，不影响主流程"""
        agent = object.__new__(Agent)

        def boom(*args, **kwargs):
            raise RuntimeError("模拟异常")

        agent.get_user_data = boom
        agent.get_memory_tags = MagicMock(return_value=[])
        assert agent._generate_proactive_suggestions() == ""
