# -*- coding: utf-8 -*-
"""Issue #94 回归测试：插件规则 configN 前缀与目录索引错位。

复现场景：多个 rules_load_dirs（插件规则目录）时，扫描侧
get_all_available_rule_names 曾把所有配置目录统一标为 config0:，
而解析侧按硬编码偏移 target_idx = 2 + config_num 映射到
_get_all_rules_dirs() 索引，导致 config0:gh.md 这类规则名
无法被 get_named_rule / get_rule_file_path 正确解析。

修复后：扫描侧按 rules_dirs 实际索引生成 configN（N>=1，
rules_dirs[0] 为全局目录用 global: 前缀），解析侧直接基于
rules_dirs 索引，扫描与解析严格对齐。
"""

import os
from pathlib import Path

from jarvis.jarvis_agent.rules_manager import RulesManager
from jarvis.jarvis_utils.config import set_global_config_data


def _make_rule(dir_path: Path, name: str, description: str) -> None:
    """在指定目录写一个带 YAML Front Matter 的规则文件。"""
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n# {name}\n",
        encoding="utf-8",
    )


def test_config_prefix_generation_and_resolution(tmp_path, monkeypatch):
    """多配置目录下 configN 前缀生成与解析一致，能正确加载规则。"""
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)

    # 项目规则目录
    project_dir = tmp_path / "proj"
    project_rules = project_dir / ".jarvis" / "rules"
    _make_rule(project_rules, "proj_rule", "项目规则")

    # 两个插件规则目录（模拟多个 rules_load_dirs）
    plugin_a = tmp_path / "plugins" / "plugin-a" / "rules"
    plugin_b = tmp_path / "plugins" / "plugin-b" / "rules"
    _make_rule(plugin_a, "alpha", "插件A规则")
    _make_rule(plugin_b, "beta", "插件B规则")

    set_global_config_data({"rules_load_dirs": [str(plugin_a), str(plugin_b)]})

    rm = RulesManager(str(project_dir))

    # 1) 扫描侧：config 前缀按 rules_dirs 实际索引生成（config1/config2）
    files = rm.get_all_available_rule_names()["files"]
    alpha_name = next(n for n in files if n.endswith("alpha.md"))
    beta_name = next(n for n in files if n.endswith("beta.md"))
    assert alpha_name == "config1:alpha.md", f"插件A应标 config1，实际 {alpha_name}"
    assert beta_name == "config2:beta.md", f"插件B应标 config2，实际 {beta_name}"

    # 2) 解析侧：get_named_rule 能正确加载 configN 规则（修复前返回 None）
    for name in (alpha_name, beta_name):
        assert rm.get_named_rule(name) is not None, f"get_named_rule({name}) 返回 None"

    # 3) get_rule_file_path 返回真实存在的文件路径
    for name, expect_dir in ((alpha_name, plugin_a), (beta_name, plugin_b)):
        path = rm.get_rule_file_path(name)
        assert path != "--", f"get_rule_file_path({name}) 返回 --"
        assert os.path.isfile(path), f"get_rule_file_path({name}) = {path} 不是有效文件"
        assert Path(path).parent == expect_dir, f"{name} 路径错位: {path}"

    # 4) load_rule 全链路可加载
    assert rm.load_rule(alpha_name)
    assert rm.load_rule(beta_name)


def test_config_prefix_works_without_central_and_project(tmp_path, monkeypatch):
    """无 central/project 目录时 configN 前缀仍能正确解析（回归旧偏移假设）。"""
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)

    plugin_a = tmp_path / "plugins" / "plugin-a" / "rules"
    _make_rule(plugin_a, "alpha", "插件A规则")

    set_global_config_data({"rules_load_dirs": [str(plugin_a)]})

    # 项目目录不存在 .jarvis/rules，也无 central
    rm = RulesManager(str(tmp_path / "empty_proj"))

    files = rm.get_all_available_rule_names()["files"]
    alpha_name = next(n for n in files if n.endswith("alpha.md"))
    assert alpha_name == "config1:alpha.md", f"应标 config1，实际 {alpha_name}"
    assert rm.get_named_rule(alpha_name) is not None
    assert os.path.isfile(rm.get_rule_file_path(alpha_name))


def test_unknown_config_num_returns_none(tmp_path, monkeypatch):
    """越界的 configN 前缀返回 None，不抛异常。"""
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    set_global_config_data({"rules_load_dirs": []})

    rm = RulesManager(str(tmp_path / "proj"))
    assert rm.get_named_rule("config99:gh.md") is None
    assert rm.get_rule_file_path("config99:gh.md") == "--"
