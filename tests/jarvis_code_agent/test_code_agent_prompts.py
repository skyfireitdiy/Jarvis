# -*- coding: utf-8 -*-
"""code_agent_prompts.py 单元测试"""

from jarvis.jarvis_code_agent.code_agent_prompts import get_system_prompt
from jarvis.jarvis_utils.scenario_prompts import _get_scenario_types

_SCENARIO_SUBDIR = "code_agent_system"


class TestGetSystemPrompt:
    """测试 get_system_prompt 函数"""

    def test_get_system_prompt_returns_string(self):
        """测试返回值为字符串"""
        result = get_system_prompt()

        assert isinstance(result, str)
        assert len(result) > 0



    def test_get_system_prompt_contains_core_behaviors(self):
        """测试包含核心行为指引"""
        result = get_system_prompt()

        # 检查是否包含工作主线各阶段（重构后不再强制逐轮 [MODE:] 前缀）
        assert "弄清现状" in result or "现状" in result
        assert "方案" in result
        assert "执行" in result
        assert "验证" in result or "收尾" in result

    def test_get_system_prompt_no_forced_mode_prefix(self):
        """测试不强制逐轮输出 [MODE:] 阶段标识"""
        result = get_system_prompt()

        assert "[MODE:" not in result

    def test_get_system_prompt_non_empty(self):
        """测试提示词不为空"""
        result = get_system_prompt()

        assert result.strip() != ""

    def test_get_system_prompt_consistent(self):
        """测试多次调用返回一致的结果"""
        result1 = get_system_prompt()
        result2 = get_system_prompt()

        assert result1 == result2

    def test_all_scenarios_load_and_use_modern_style(self):
        """所有场景文件均可加载，且不再强制 [MODE:] 前缀或使用文言风格"""
        scenarios = _get_scenario_types(_SCENARIO_SUBDIR)
        assert scenarios, "场景目录应至少包含一个场景"

        for scenario in scenarios.keys():
            prompt = get_system_prompt(scenario)
            assert isinstance(prompt, str) and prompt.strip(), f"{scenario} 系统提示词为空"
            assert "[MODE:" not in prompt, f"{scenario} 不应强制 [MODE:] 前缀"
            assert "汝" not in prompt and "文言文" not in prompt, f"{scenario} 不应使用文言风格"
