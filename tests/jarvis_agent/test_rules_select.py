# -*- coding: utf-8 -*-
"""rules_manager 两级选择：cheap 短名单单测"""

from types import SimpleNamespace

from jarvis.jarvis_agent.rules_manager import RulesManager


class _FakeCheap:
    def __init__(self, response):
        self.response = response
        self.suppressed = None

    def set_suppress_output(self, v):
        self.suppressed = v

    def chat_until_success(self, prompt):
        return self.response


def test_cheap_shortlist_parses_num():
    mgr = object.__new__(RulesManager)
    cheap = _FakeCheap("<NUM>2,4</NUM>")
    names = ["a.md", "b.md", "c.md", "d.md"]
    descs = {n: f"desc {n}" for n in names}
    out = mgr._select_cheap_shortlist(cheap, "任务", names, descs, max_pre=4)
    assert out == ["b.md", "d.md"]


def test_cheap_shortlist_none_returns_empty():
    mgr = object.__new__(RulesManager)
    cheap = _FakeCheap("<NUM>none</NUM>")
    names = ["a.md", "b.md"]
    out = mgr._select_cheap_shortlist(cheap, "任务", names, {n: "" for n in names})
    assert out == []


def test_cheap_shortlist_limits_and_dedup():
    mgr = object.__new__(RulesManager)
    cheap = _FakeCheap("<NUM>1,1,3,5</NUM>")
    names = ["a.md", "b.md", "c.md", "d.md", "e.md"]
    out = mgr._select_cheap_shortlist(cheap, "任务", names, {n: "" for n in names}, max_pre=2)
    assert out == ["a.md", "c.md"]
