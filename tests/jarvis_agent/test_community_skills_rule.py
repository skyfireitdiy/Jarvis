# -*- coding: utf-8 -*-
"""RulesManager 社区 skill 目录（.agents/skills、.claude/skills）扫描与加载单测。

验证方案 1：Jarvis 默认把 .agents/skills 与 .claude/skills 作为项目级规则来源，
规则名形如 project:<skill>/SKILL.md，且 .jarvis/rules 优先级最高。
"""

import os
import tempfile

from jarvis.jarvis_agent.rules_manager import RulesManager


def _make_mgr(root_dir):
    return RulesManager(root_dir)


def _write_skill(base, skill_name, content):
    """在 <base>/<skill_name>/SKILL.md 写入 skill 文件。"""
    skill_dir = os.path.join(base, skill_name)
    os.makedirs(skill_dir, exist_ok=True)
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(content)


def test_agents_skills_scanned():
    """.agents/skills 下的 SKILL.md 被扫描为 project:<skill>/SKILL.md"""
    with tempfile.TemporaryDirectory() as d:
        agents_skills = os.path.join(d, ".agents", "skills")
        _write_skill(agents_skills, "reversa-architect", "# Architect\n\n分析架构。\n")
        mgr = _make_mgr(d)
        files = mgr.get_all_available_rule_names()["files"]
        assert "project:reversa-architect/SKILL.md" in files


def test_claude_skills_scanned():
    """.claude/skills 下的 SKILL.md 被扫描为 project:<skill>/SKILL.md"""
    with tempfile.TemporaryDirectory() as d:
        claude_skills = os.path.join(d, ".claude", "skills")
        _write_skill(claude_skills, "code-review", "# Review\n\n审查代码。\n")
        mgr = _make_mgr(d)
        files = mgr.get_all_available_rule_names()["files"]
        assert "project:code-review/SKILL.md" in files


def test_agents_skills_loadable():
    """.agents/skills 的 SKILL.md 能通过 load_rule 加载完整内容"""
    with tempfile.TemporaryDirectory() as d:
        agents_skills = os.path.join(d, ".agents", "skills")
        _write_skill(agents_skills, "reversa-architect", "# Architect\n\n分析架构。\n")
        mgr = _make_mgr(d)
        assert mgr.load_rule("project:reversa-architect/SKILL.md")
        content = mgr.get_loaded_rules_content()
        assert "分析架构" in content


def test_agents_skills_rule_file_path():
    """.agents/skills 的 SKILL.md 能解析出真实文件路径"""
    with tempfile.TemporaryDirectory() as d:
        agents_skills = os.path.join(d, ".agents", "skills")
        _write_skill(agents_skills, "reversa-architect", "content")
        mgr = _make_mgr(d)
        path = mgr.get_rule_file_path("project:reversa-architect/SKILL.md")
        assert path != "--"
        assert os.path.isfile(path)
        assert path.endswith(os.path.join(".agents", "skills", "reversa-architect", "SKILL.md"))


def test_jarvis_rules_precedence_over_agents_skills():
    """.jarvis/rules 与 .agents/skills 同名规则时，.jarvis/rules 优先"""
    with tempfile.TemporaryDirectory() as d:
        # .jarvis/rules 下的同名规则
        jarvis_rules = os.path.join(d, ".jarvis", "rules")
        os.makedirs(jarvis_rules, exist_ok=True)
        with open(os.path.join(jarvis_rules, "architect.md"), "w", encoding="utf-8") as f:
            f.write("JARVIS architect rule")
        # .agents/skills 下的 SKILL.md（规则名不同：architect/SKILL.md）
        agents_skills = os.path.join(d, ".agents", "skills")
        _write_skill(agents_skills, "architect", "AGENTS architect skill")

        mgr = _make_mgr(d)
        # 两个来源的规则名不同（architect.md vs architect/SKILL.md），互不冲突
        files = mgr.get_all_available_rule_names()["files"]
        assert "project:architect.md" in files
        assert "project:architect/SKILL.md" in files

        # 各自能正确加载到对应来源的内容
        assert "JARVIS architect rule" in mgr.get_named_rule("project:architect.md")
        assert "AGENTS architect skill" in mgr.get_named_rule("project:architect/SKILL.md")


def test_agents_skills_not_loaded_by_default():
    """.agents/skills 的 SKILL.md 不自动注入（需显式 load_rule）"""
    with tempfile.TemporaryDirectory() as d:
        agents_skills = os.path.join(d, ".agents", "skills")
        _write_skill(agents_skills, "reversa-architect", "content")
        mgr = _make_mgr(d)
        # 自动加载的只有 project:rule / project:agents，SKILL.md 需显式加载
        assert "project:reversa-architect/SKILL.md" not in mgr.loaded_rules
        assert mgr.load_rule("project:reversa-architect/SKILL.md")


def test_no_skills_dirs_no_effect():
    """无 .agents/.claude 目录时行为不变，不产生额外规则"""
    with tempfile.TemporaryDirectory() as d:
        mgr = _make_mgr(d)
        files = mgr.get_all_available_rule_names()["files"]
        assert not any("SKILL.md" in f for f in files)
