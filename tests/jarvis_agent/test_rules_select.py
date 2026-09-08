# -*- coding: utf-8 -*-
"""rules_manager 强触发 cheap 判定单测"""

from jarvis.jarvis_agent.rules_manager import RulesManager


class _FakeCheap:
    def __init__(self, response):
        self.response = response
        self.suppressed = None

    def set_suppress_output(self, v):
        self.suppressed = v

    def chat_until_success(self, prompt):
        return self.response


def test_match_task_cheap_uses_catalog_and_parses(monkeypatch):
    from jarvis.jarvis_platform.registry import PlatformRegistry

    mgr = object.__new__(RulesManager)
    mgr._catalog_cache = [
        ["builtin:security.md", "安全审查"],
        ["builtin:tdd.md", "测试驱动"],
    ]
    cheap = _FakeCheap("<NUM>2,1</NUM>")

    class _Reg:
        def create_platform(self, platform_type="cheap"):
            return cheap

    monkeypatch.setattr(PlatformRegistry, "get_global_platform_registry", lambda: _Reg())
    out = mgr.match_task_cheap("帮我做个安全代码审查", max_rules=3)
    assert out == ["builtin:tdd.md", "builtin:security.md"]


def test_match_task_cheap_no_cheap_returns_empty(monkeypatch):
    from jarvis.jarvis_platform.registry import PlatformRegistry

    mgr = object.__new__(RulesManager)
    mgr._catalog_cache = [["builtin:security.md", "安全审查"]]

    class _NoCheap:
        def create_platform(self, platform_type="cheap"):
            return None

    monkeypatch.setattr(PlatformRegistry, "get_global_platform_registry", lambda: _NoCheap())
    assert mgr.match_task_cheap("你好") == []


def test_match_task_cheap_none_answer_returns_empty(monkeypatch):
    from jarvis.jarvis_platform.registry import PlatformRegistry

    mgr = object.__new__(RulesManager)
    mgr._catalog_cache = [["builtin:security.md", "安全审查"]]
    cheap = _FakeCheap("<NUM>none</NUM>")

    class _Reg:
        def create_platform(self, platform_type="cheap"):
            return cheap

    monkeypatch.setattr(PlatformRegistry, "get_global_platform_registry", lambda: _Reg())
    assert mgr.match_task_cheap("今天天气不错") == []
