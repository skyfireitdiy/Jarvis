# -*- coding: utf-8 -*-
"""RulesManager 项目级 AGENTS.md/CLAUDE.md 兼容加载单测"""

import os
import tempfile
from unittest.mock import patch

from jarvis.jarvis_agent.rules_manager import RulesManager


def _make_mgr(root_dir):
    return RulesManager(root_dir)


def test_agents_md_loaded():
    """仓库根存在 AGENTS.md 时自动加载为 project:agents 规则"""
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "AGENTS.md"), "w", encoding="utf-8") as f:
            f.write("# AGENTS\n\nThis project uses Python.\n")
        mgr = _make_mgr(d)
        assert "project:agents" in mgr.loaded_rules
        content = mgr.get_loaded_rules_content()
        assert "This project uses Python" in content


def test_claude_md_fallback():
    """无 AGENTS.md 时回退读取 CLAUDE.md"""
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("# CLAUDE\n\nUse TDD.\n")
        mgr = _make_mgr(d)
        assert "project:agents" in mgr.loaded_rules
        assert "Use TDD" in mgr.get_loaded_rules_content()


def test_agents_precedence_over_claude():
    """AGENTS.md 与 CLAUDE.md 同时存在时，AGENTS.md 优先"""
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "AGENTS.md"), "w", encoding="utf-8") as f:
            f.write("AGENTS content")
        with open(os.path.join(d, "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("CLAUDE content")
        mgr = _make_mgr(d)
        content = mgr.get_loaded_rules_content()
        assert "AGENTS content" in content
        assert "CLAUDE content" not in content


def test_no_file_not_loaded():
    """仓库根无 AGENTS.md/CLAUDE.md 时不加载 project:agents"""
    with tempfile.TemporaryDirectory() as d:
        mgr = _make_mgr(d)
        assert "project:agents" not in mgr.loaded_rules


def test_coexist_with_rule_md():
    """与 .jarvis/rules/rule.md 共存时两者合并注入，不冲突"""
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, ".jarvis", "rules"))
        with open(
            os.path.join(d, ".jarvis", "rules", "rule.md"), "w", encoding="utf-8"
        ) as f:
            f.write("Project rule.md content")
        with open(os.path.join(d, "AGENTS.md"), "w", encoding="utf-8") as f:
            f.write("AGENTS content")
        mgr = _make_mgr(d)
        content = mgr.get_loaded_rules_content()
        assert "Project rule.md content" in content
        assert "AGENTS content" in content


def test_rule_file_path_agents():
    """get_rule_file_path 对 project:agents 返回实际 AGENTS.md 路径"""
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "AGENTS.md"), "w", encoding="utf-8") as f:
            f.write("content")
        mgr = _make_mgr(d)
        path = mgr.get_rule_file_path("project:agents")
        assert path.endswith("AGENTS.md")


def test_rule_file_path_agents_fallback_claude():
    """无 AGENTS.md 时 get_rule_file_path 返回 CLAUDE.md 路径"""
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("content")
        mgr = _make_mgr(d)
        path = mgr.get_rule_file_path("project:agents")
        assert path.endswith("CLAUDE.md")


def test_large_agents_truncated_by_token_budget():
    """超大 AGENTS.md 按模型最大输入 token 的 80% 预算截断"""
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "AGENTS.md"), "w", encoding="utf-8") as f:
            f.write("# AGENTS\n\n" + "x" * 20000 + "\nEND")
        with patch(
            "jarvis.jarvis_utils.config.get_max_input_token_count", return_value=1000
        ):
            mgr = _make_mgr(d)
        content = mgr.get_loaded_rules_content()
        assert "已按 token 预算截断" in content


def test_injectable_content():
    """get_injectable_rules_content 能注入 AGENTS.md 正文"""
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "AGENTS.md"), "w", encoding="utf-8") as f:
            f.write("## 规范\n\n遵循 TDD。\n")
        mgr = _make_mgr(d)
        inj = mgr.get_injectable_rules_content()
        assert "遵循 TDD" in inj
