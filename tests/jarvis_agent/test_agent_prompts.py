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

    def test_inherit_core_scenario_composes_with_default_core(self):
        """声明 inherit_core 的场景 = 自身要点 + default 共享核心"""
        prompt = get_system_prompt("planning", scenario_subdir=_SCENARIO_SUBDIR)
        assert "规划决策要点" in prompt
        assert "## 工作方法" in prompt
        assert "## 沟通" in prompt


def test_classify_returns_recommended_temperature(monkeypatch):
    """分类结果里应带按任务性质推荐的温度档（low/medium/high → 0.5/0.7/1.0）"""

    from jarvis.jarvis_agent.agent_prompts import classify_user_request
    from jarvis.jarvis_platform.registry import PlatformRegistry

    class _FakePlatform:
        def __init__(self, text):
            self._text = text

        def set_suppress_output(self, value):
            pass

        def chat_until_success(self, prompt):
            assert "temperature:" in prompt  # 分类 prompt 需请求温度档
            return self._text

    monkeypatch.setattr(
        PlatformRegistry,
        "get_cheap_platform",
        lambda self: _FakePlatform(
            "scenario: default\ndifficulty: medium\ntemperature: low"
        ),
    )
    _, difficulty, temperature = classify_user_request("修复一个精确的 bug")
    assert difficulty == "medium"
    assert temperature == 0.5

    monkeypatch.setattr(
        PlatformRegistry,
        "get_cheap_platform",
        lambda self: _FakePlatform("scenario: default\ndifficulty: easy"),
    )
    _, _, temperature = classify_user_request("闲聊")
    assert temperature == 0.7  # 缺省回落到均衡

    monkeypatch.setattr(
        PlatformRegistry,
        "get_cheap_platform",
        lambda self: _FakePlatform(
            "scenario: default\ndifficulty: medium\ntemperature: high"
        ),
    )
    _, _, temperature = classify_user_request("写一篇创意文案")
    assert temperature == 1.0
