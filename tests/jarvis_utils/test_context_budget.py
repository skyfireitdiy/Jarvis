# -*- coding: utf-8 -*-
"""上下文工程·预算配置与分层预算计算器单元测试"""

from jarvis.jarvis_utils.config import (
    GLOBAL_CONFIG_DATA,
    calculate_layer_token_budget,
    get_context_budget_usage_ratio,
    get_context_layer_ratios,
    get_context_memory_retrieval_budget,
)


def _restore(key, original):
    if original is None:
        GLOBAL_CONFIG_DATA.pop(key, None)
    else:
        GLOBAL_CONFIG_DATA[key] = original


class TestContextBudgetUsageRatio:
    """测试 get_context_budget_usage_ratio"""

    def test_default_ratio(self):
        key = "context_budget_usage_ratio"
        original = GLOBAL_CONFIG_DATA.get(key)
        try:
            GLOBAL_CONFIG_DATA.pop(key, None)
            assert get_context_budget_usage_ratio() == 0.9
        finally:
            _restore(key, original)

    def test_configured_ratio(self):
        key = "context_budget_usage_ratio"
        original = GLOBAL_CONFIG_DATA.get(key)
        try:
            GLOBAL_CONFIG_DATA[key] = 0.75
            assert get_context_budget_usage_ratio() == 0.75
        finally:
            _restore(key, original)


class TestContextLayerRatios:
    """测试 get_context_layer_ratios"""

    def test_default_ratios(self):
        key = "context_layer_ratios"
        original = GLOBAL_CONFIG_DATA.get(key)
        try:
            GLOBAL_CONFIG_DATA.pop(key, None)
            ratios = get_context_layer_ratios()
            assert set(ratios.keys()) == {
                "system_prompt",
                "memory_retrieval",
                "tool_description",
                "rules",
                "conversation_history",
                "current_task",
            }
            assert ratios["system_prompt"] == 0.20
            assert ratios["memory_retrieval"] == 0.20
            assert ratios["tool_description"] == 0.15
            assert ratios["rules"] == 0.10
            assert ratios["conversation_history"] == 0.25
            assert ratios["current_task"] == 0.10
        finally:
            _restore(key, original)

    def test_partial_override(self):
        key = "context_layer_ratios"
        original = GLOBAL_CONFIG_DATA.get(key)
        try:
            # 部分覆盖：只改 memory_retrieval，其余保持默认
            GLOBAL_CONFIG_DATA[key] = {"memory_retrieval": 0.3}
            ratios = get_context_layer_ratios()
            assert ratios["memory_retrieval"] == 0.3
            assert ratios["system_prompt"] == 0.20
            assert ratios["conversation_history"] == 0.25
        finally:
            _restore(key, original)

    def test_invalid_override_ignored(self):
        key = "context_layer_ratios"
        original = GLOBAL_CONFIG_DATA.get(key)
        try:
            # 非法值应被忽略，保留默认
            GLOBAL_CONFIG_DATA[key] = {"rules": "not-a-number"}
            ratios = get_context_layer_ratios()
            assert ratios["rules"] == 0.10
        finally:
            _restore(key, original)

    def test_non_dict_config_uses_default(self):
        key = "context_layer_ratios"
        original = GLOBAL_CONFIG_DATA.get(key)
        try:
            GLOBAL_CONFIG_DATA[key] = "not-a-dict"
            ratios = get_context_layer_ratios()
            assert ratios["system_prompt"] == 0.20
        finally:
            _restore(key, original)


class TestContextMemoryRetrievalBudget:
    """测试 get_context_memory_retrieval_budget"""

    def test_default_budget(self):
        key = "context_memory_retrieval_budget"
        original = GLOBAL_CONFIG_DATA.get(key)
        try:
            GLOBAL_CONFIG_DATA.pop(key, None)
            assert get_context_memory_retrieval_budget() == 3000
        finally:
            _restore(key, original)

    def test_configured_budget(self):
        key = "context_memory_retrieval_budget"
        original = GLOBAL_CONFIG_DATA.get(key)
        try:
            GLOBAL_CONFIG_DATA[key] = 5000
            assert get_context_memory_retrieval_budget() == 5000
        finally:
            _restore(key, original)


class TestCalculateLayerTokenBudget:
    """测试 calculate_layer_token_budget 分层预算计算器"""

    def test_budgets_follow_ratios(self):
        key = "context_layer_ratios"
        original = GLOBAL_CONFIG_DATA.get(key)
        try:
            GLOBAL_CONFIG_DATA.pop(key, None)
            budgets = calculate_layer_token_budget(10000)
            assert budgets["system_prompt"] == 2000  # 0.20
            assert budgets["memory_retrieval"] == 2000  # 0.20
            assert budgets["tool_description"] == 1500  # 0.15
            assert budgets["rules"] == 1000  # 0.10
            assert budgets["conversation_history"] == 2500  # 0.25
            assert budgets["current_task"] == 1000  # 0.10
        finally:
            _restore(key, original)

    def test_floor_rounding(self):
        # 预算按向下取整
        key = "context_layer_ratios"
        original = GLOBAL_CONFIG_DATA.get(key)
        try:
            GLOBAL_CONFIG_DATA.pop(key, None)
            budgets = calculate_layer_token_budget(1999)
            assert budgets["system_prompt"] == 399  # 1999 * 0.20 = 399.8 -> 399
            assert budgets["rules"] == 199  # 1999 * 0.10 = 199.9 -> 199
        finally:
            _restore(key, original)

    def test_zero_total(self):
        budgets = calculate_layer_token_budget(0)
        assert all(v == 0 for v in budgets.values())
        assert set(budgets.keys()) == set(get_context_layer_ratios().keys())

    def test_respects_configured_ratios(self):
        key = "context_layer_ratios"
        original = GLOBAL_CONFIG_DATA.get(key)
        try:
            GLOBAL_CONFIG_DATA[key] = {"system_prompt": 0.5}
            budgets = calculate_layer_token_budget(1000)
            assert budgets["system_prompt"] == 500
            assert budgets["conversation_history"] == 250  # 默认 0.25
        finally:
            _restore(key, original)
