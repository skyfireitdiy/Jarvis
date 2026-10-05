# -*- coding: utf-8 -*-
"""rules_manager 强触发 cheap 判定单测"""

from unittest.mock import patch

from jarvis.jarvis_agent.rules_manager import RulesManager, _preselect_rules


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

    monkeypatch.setattr(
        PlatformRegistry, "get_global_platform_registry", lambda: _Reg()
    )
    out = mgr.match_task_cheap("帮我做个安全代码审查", max_rules=3)
    assert out == ["builtin:tdd.md", "builtin:security.md"]


def test_match_task_cheap_no_cheap_returns_empty(monkeypatch):
    from jarvis.jarvis_platform.registry import PlatformRegistry

    mgr = object.__new__(RulesManager)
    mgr._catalog_cache = [["builtin:security.md", "安全审查"]]

    class _NoCheap:
        def create_platform(self, platform_type="cheap"):
            return None

    monkeypatch.setattr(
        PlatformRegistry, "get_global_platform_registry", lambda: _NoCheap()
    )
    assert mgr.match_task_cheap("你好") == []


def test_match_task_cheap_none_answer_returns_empty(monkeypatch):
    from jarvis.jarvis_platform.registry import PlatformRegistry

    mgr = object.__new__(RulesManager)
    mgr._catalog_cache = [["builtin:security.md", "安全审查"]]
    cheap = _FakeCheap("<NUM>none</NUM>")

    class _Reg:
        def create_platform(self, platform_type="cheap"):
            return cheap

    monkeypatch.setattr(
        PlatformRegistry, "get_global_platform_registry", lambda: _Reg()
    )
    assert mgr.match_task_cheap("今天天气不错") == []


class TestPreselectRules:
    """测试 _preselect_rules 预筛函数"""

    def _make_rules(self):
        rules = [
            "builtin:security.md",
            "builtin:tdd.md",
            "builtin:deploy.md",
            "builtin:refactor.md",
        ]
        desc = {
            "builtin:security.md": "安全代码审查",
            "builtin:tdd.md": "测试驱动开发",
            "builtin:deploy.md": "部署上线",
            "builtin:refactor.md": "遗留代码重构",
        }
        return rules, desc

    def test_match_relevant_rules(self):
        """关键词应命中相关规则（名称+描述），过滤无关规则"""
        rules, desc = self._make_rules()
        result = _preselect_rules("帮我做安全代码审查", rules, desc)
        assert "builtin:security.md" in result
        assert "builtin:tdd.md" not in result  # 无关规则被过滤

    def test_match_by_description(self):
        """关键词命中描述而非规则名时也应命中"""
        rules, desc = self._make_rules()
        # "部署" 只出现在 deploy 的描述里，不在规则名里
        result = _preselect_rules("我要部署上线", rules, desc)
        assert "builtin:deploy.md" in result

    def test_no_match_returns_all(self):
        """无任何匹配时回退全量，避免漏选"""
        rules, desc = self._make_rules()
        result = _preselect_rules("完全无关的随机词汇xyz", rules, desc)
        assert result == rules

    def test_no_keywords_returns_all(self):
        """任务描述无有效关键词时回退全量"""
        rules, desc = self._make_rules()
        result = _preselect_rules("的 了 是", rules, desc)
        assert result == rules

    def test_top_n_truncation(self):
        """超过 top_n 时截断到 top_n"""
        rules = [f"builtin:rule{i}.md" for i in range(100)]
        desc = {r: f"主题{i}" for i, r in enumerate(rules)}
        result = _preselect_rules("主题", rules, desc, top_n=10)
        assert len(result) == 10

    def test_exception_returns_all(self):
        """异常时回退全量，保证不改变现有行为"""
        rules, desc = self._make_rules()
        with patch(
            "jarvis.jarvis_agent.rules_manager._RULE_PRESELECT_STOP_WORDS",
            new=None,  # 触发异常
        ):
            result = _preselect_rules("部署", rules, desc)
            assert result == rules


class TestSelectRuleByTaskPreselect:
    """测试 select_rule_by_task 集成预筛：传给 LLM 的候选应为预筛子集"""

    def _make_mgr(self, monkeypatch):
        mgr = object.__new__(RulesManager)
        mgr._catalog_cache = []

        # 全量规则：4 条，其中只有 security 与"安全审查"相关
        all_rules = {
            "builtin": ["builtin:security.md", "builtin:tdd.md"],
            "files": ["project:deploy.md", "project:refactor.md"],
        }
        desc = {
            "builtin:security.md": "安全代码审查",
            "builtin:tdd.md": "测试驱动开发",
            "project:deploy.md": "部署上线",
            "project:refactor.md": "遗留代码重构",
        }

        monkeypatch.setattr(mgr, "get_all_available_rule_names", lambda: all_rules)
        monkeypatch.setattr(mgr, "get_rule_file_path", lambda name: "--")
        monkeypatch.setattr(mgr, "_extract_rule_description", lambda path: "")
        monkeypatch.setattr(mgr, "get_rule_preview", lambda name: desc.get(name, "--"))
        return mgr, desc

    def test_prescreen_reduces_candidates_to_llm(self, monkeypatch):
        """预筛后传给 decide_choice 的候选应只含相关规则"""
        mgr, desc = self._make_mgr(monkeypatch)

        captured = {}

        def fake_decide_choice(task, candidates, fallback, *, max_select=3):
            captured["candidates"] = candidates
            return ["builtin:security.md"]

        monkeypatch.setattr(
            "jarvis.jarvis_agent.rules_manager.decide_choice",
            fake_decide_choice,
        )

        result = mgr.select_rule_by_task("帮我做安全代码审查")

        assert result == ["builtin:security.md"]
        # 预筛后候选应缩减，且包含相关规则
        assert "builtin:security.md" in captured["candidates"]
        assert len(captured["candidates"]) < 4  # 从 4 条缩减

    def test_no_match_falls_back_to_all(self, monkeypatch):
        """无匹配时回退全量，候选不缩减"""
        mgr, desc = self._make_mgr(monkeypatch)

        captured = {}

        def fake_decide_choice(task, candidates, fallback, *, max_select=3):
            captured["candidates"] = candidates
            return ["builtin:security.md"]

        monkeypatch.setattr(
            "jarvis.jarvis_agent.rules_manager.decide_choice",
            fake_decide_choice,
        )

        mgr.select_rule_by_task("完全无关的随机词汇xyz")

        # 无匹配回退全量，4 条候选都保留
        assert len(captured["candidates"]) == 4
