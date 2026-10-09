# -*- coding: utf-8 -*-
"""上下文工程·分层注入预算（_get_memory_retrieval_budget）单元测试"""

from unittest.mock import patch

from jarvis.jarvis_agent import Agent


def _make_agent():
    # 不触发 __init__ 的完整初始化，仅用于绑定方法
    agent = Agent.__new__(Agent)
    return agent


class TestGetMemoryRetrievalBudget:
    """测试 Agent._get_memory_retrieval_budget 分层记忆检索预算"""

    def test_uses_layer_ratio_budget(self):
        agent = _make_agent()
        with (
            patch(
                "jarvis.jarvis_utils.config.get_max_input_token_count",
                return_value=200000,
            ),
            patch(
                "jarvis.jarvis_utils.config.get_context_budget_usage_ratio",
                return_value=0.9,
            ),
            patch(
                "jarvis.jarvis_utils.config.calculate_layer_token_budget",
                return_value={"memory_retrieval": 36000, "system_prompt": 36000},
            ),
        ):
            budget = agent._get_memory_retrieval_budget()
        # 200000 × 0.9 = 180000，memory_retrieval 层按 0.20 → 36000
        assert budget == 36000

    def test_falls_back_on_exception(self):
        """预算计算异常时回退到配置的固定预算"""
        agent = _make_agent()
        with (
            patch(
                "jarvis.jarvis_utils.config.get_max_input_token_count",
                side_effect=Exception("boom"),
            ),
            patch(
                "jarvis.jarvis_utils.config.get_context_memory_retrieval_budget",
                return_value=3000,
            ),
        ):
            budget = agent._get_memory_retrieval_budget()
        assert budget == 3000

    def test_missing_layer_key_returns_zero(self):
        """分层预算中缺少 memory_retrieval 键时返回 0"""
        agent = _make_agent()
        with (
            patch(
                "jarvis.jarvis_utils.config.get_max_input_token_count",
                return_value=100000,
            ),
            patch(
                "jarvis.jarvis_utils.config.get_context_budget_usage_ratio",
                return_value=0.9,
            ),
            patch(
                "jarvis.jarvis_utils.config.calculate_layer_token_budget",
                return_value={"system_prompt": 1000},
            ),
        ):
            budget = agent._get_memory_retrieval_budget()
        assert budget == 0
