# -*- coding: utf-8 -*-
"""code_agent_prompts.py 单元测试"""

from jarvis.jarvis_code_agent.code_agent_prompts import get_system_prompt


class TestGetSystemPrompt:
    """测试 get_system_prompt 函数"""

    def test_get_system_prompt_returns_string(self):
        """测试返回值为字符串"""
        result = get_system_prompt()

        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_system_prompt_contains_key_elements(self):
        """测试提示词包含关键元素"""
        result = get_system_prompt()

        # 检查是否包含 ARCHER 工作流相关内容
        assert "ARCHER" in result
        assert "MODE" in result

        # 检查是否包含工作流程
        assert "ANALYZE" in result or "分析" in result
        assert "EXECUTE" in result or "执行" in result

        # 检查是否包含工具使用规范
        assert "工具" in result

    def test_get_system_prompt_contains_mode_definitions(self):
        """测试包含模式定义"""
        result = get_system_prompt()

        # 检查是否包含 ARCHER 各个模式
        assert "ANALYZE" in result or "分析" in result
        assert "RULE" in result or "规则" in result
        assert "COLLECT" in result or "收集" in result
        assert "HYPOTHESIZE" in result or "方案" in result
        assert "EXECUTE" in result or "执行" in result
        assert "REVIEW" in result or "审查" in result

    def test_get_system_prompt_non_empty(self):
        """测试提示词不为空"""
        result = get_system_prompt()

        assert result.strip() != ""

    def test_get_system_prompt_consistent(self):
        """测试多次调用返回一致的结果"""
        result1 = get_system_prompt()
        result2 = get_system_prompt()

        assert result1 == result2
