# -*- coding: utf-8 -*-
"""agent_system 通用场景提示词单元测试"""

from jarvis.jarvis_utils.scenario_prompts import _get_scenario_types
from jarvis.jarvis_utils.scenario_prompts import get_system_prompt

_SCENARIO_SUBDIR = "agent_system"


class TestAgentSystemPrompts:
    """测试通用 Agent 各场景系统提示词"""

    def test_all_scenarios_load_and_use_modern_style(self):
        """所有场景文件均可加载，且不再强制 [MODE:] 前缀或使用文言风格"""
        scenarios = _get_scenario_types(_SCENARIO_SUBDIR)
        assert scenarios, "agent_system 场景目录应至少包含一个场景"

        for scenario in scenarios.keys():
            prompt = get_system_prompt(scenario, scenario_subdir=_SCENARIO_SUBDIR)
            assert isinstance(prompt, str) and prompt.strip(), f"{scenario} 系统提示词为空"
            assert "[MODE:" not in prompt, f"{scenario} 不应强制 [MODE:] 前缀"
            assert "汝" not in prompt and "文言文" not in prompt, f"{scenario} 不应使用文言风格"
            assert "工作方法" in prompt, f"{scenario} 应包含共享的工作方法段落"
