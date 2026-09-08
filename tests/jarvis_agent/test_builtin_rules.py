# -*- coding: utf-8 -*-
"""builtin_rules 入口扫描单元测试"""

from jarvis.jarvis_agent.builtin_rules import list_builtin_rule_entries
from jarvis.jarvis_agent.builtin_rules import list_builtin_rules


def test_entries_are_subset_of_full_rules():
    full = {n.lower() for n in list_builtin_rules()}
    entries = list_builtin_rule_entries()
    assert entries
    assert all(e.lower() in full for e in entries)


def test_superpowers_only_entry_skill_md_selected():
    entries = list_builtin_rule_entries()
    super_entries = [e for e in entries if "superpowers" in e]
    # vendored superpowers 每个 skill 目录只应暴露 SKILL.md 入口
    assert super_entries
    assert all(e.lower().endswith("/skill.md") for e in super_entries)
