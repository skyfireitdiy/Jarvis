# -*- coding: utf-8 -*-
"""builtin_rules 入口扫描单元测试"""

from jarvis.jarvis_agent.builtin_rules import list_builtin_rule_entries
from jarvis.jarvis_agent.builtin_rules import list_builtin_rules


def test_entries_are_subset_of_full_rules():
    full = {n.lower() for n in list_builtin_rules()}
    entries = list_builtin_rule_entries()
    assert entries
    assert all(e.lower() in full for e in entries)


def test_removed_noise_categories_not_listed():
    entries = list_builtin_rule_entries()
    # 已清理的低价值/惰性目录不应再作为自动选择候选
    for marker in ("superpowers", "agent_personality", "investment_analysis", "technical_analysis"):
        assert not any(marker in e for e in entries), marker
