# -*- coding: utf-8 -*-
"""PluginRegistry 可逆效应测试。

覆盖插件资源（工具/规则）的登记、查询、撤销闭环，以及 ToolRegistry /
RulesManager / uninstall_plugin 的接入。所有测试用临时数据目录隔离，
不污染真实环境。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from jarvis.jarvis_tools.plugin_registry import PluginRegistry


@pytest.fixture(autouse=True)
def _isolate_registry():
    """每个用例前清空 PluginRegistry 全局单例，避免用例间相互污染。"""
    PluginRegistry.instance().clear()
    yield
    PluginRegistry.instance().clear()


class TestPluginRegistry:
    """PluginRegistry 基本登记/查询/撤销。"""

    def test_register_and_query(self):
        pr = PluginRegistry.instance()
        pr.register_tool("p1", "tool_a")
        pr.register_tools("p1", ["tool_b", "tool_c"])
        pr.register_rule("p1", "rule_x")
        pr.register_rule("p2", "rule_y")

        assert pr.get_plugin_tools("p1") == ["tool_a", "tool_b", "tool_c"]
        assert pr.get_plugin_rules("p1") == ["rule_x"]
        assert pr.get_plugin_rules("p2") == ["rule_y"]
        assert set(pr.registered_plugins()) == {"p1", "p2"}
        assert pr.has_plugin("p1")
        assert not pr.has_plugin("nonexistent")

    def test_unregister_plugin_returns_resources(self):
        pr = PluginRegistry.instance()
        pr.register_tool("p1", "tool_a")
        pr.register_rule("p1", "rule_x")

        result = pr.unregister_plugin("p1")
        assert set(result["tools"]) == {"tool_a"}
        assert set(result["rules"]) == {"rule_x"}
        assert not pr.has_plugin("p1")

    def test_clear_tools_only_clears_tools(self):
        pr = PluginRegistry.instance()
        pr.register_tool("p1", "tool_a")
        pr.register_rule("p1", "rule_x")

        pr.clear_tools("p1")
        assert pr.get_plugin_tools("p1") == []
        assert pr.get_plugin_rules("p1") == ["rule_x"]

    def test_clear_rules_only_clears_rules(self):
        pr = PluginRegistry.instance()
        pr.register_tool("p1", "tool_a")
        pr.register_rule("p1", "rule_x")

        pr.clear_rules("p1")
        assert pr.get_plugin_rules("p1") == []
        assert pr.get_plugin_tools("p1") == ["tool_a"]

    def test_revoke_plugin_without_revoker(self):
        """无撤销器时 revoke_plugin 仅清理登记，不抛异常。"""
        pr = PluginRegistry.instance()
        pr.register_tool("p1", "tool_a")
        pr.register_rule("p1", "rule_x")

        result = pr.revoke_plugin("p1")
        assert result == {"tools": 0, "rules": 0}
        assert not pr.has_plugin("p1")

    def test_revoke_plugin_with_revokers(self):
        """有撤销器时 revoke_plugin 调用撤销器并清理登记。"""
        pr = PluginRegistry.instance()
        pr.register_tool("p1", "tool_a")
        pr.register_rule("p1", "rule_x")

        revoked = {"tools": [], "rules": []}

        def tool_revoker(name):
            revoked["tools"].append(name)
            return 1

        def rules_revoker(name):
            revoked["rules"].append(name)
            return 1

        pr.set_tool_revoker(tool_revoker)
        pr.set_rules_revoker(rules_revoker)

        result = pr.revoke_plugin("p1")
        assert result == {"tools": 1, "rules": 1}
        assert revoked["tools"] == ["p1"]
        assert revoked["rules"] == ["p1"]
        assert not pr.has_plugin("p1")

    def test_singleton(self):
        assert PluginRegistry.instance() is PluginRegistry.instance()


def _make_plugin_tool(tmp_path, plugin_name, tool_name):
    """在临时数据目录下构造一个插件工具文件。"""
    tool_dir = tmp_path / "plugins" / plugin_name / "tools"
    tool_dir.mkdir(parents=True, exist_ok=True)
    tool_file = tool_dir / f"{tool_name}.py"
    tool_file.write_text(
        f"# -*- coding: utf-8 -*-\n"
        f"class {tool_name}:\n"
        f'    name = "{tool_name}"\n'
        f'    description = "plugin tool"\n'
        f'    parameters = {{"type": "object", "properties": {{}}, "required": []}}\n'
        f"    def execute(self, **kwargs):\n"
        f'        return {{"success": True}}\n',
        encoding="utf-8",
    )
    return str(tool_file)


def _make_plugin_rule(tmp_path, plugin_name, rule_name):
    """在临时数据目录下构造一个插件规则文件。"""
    rule_dir = tmp_path / "plugins" / plugin_name / "rules"
    rule_dir.mkdir(parents=True, exist_ok=True)
    rule_file = rule_dir / f"{rule_name}.md"
    rule_file.write_text(
        f"---\nname: {rule_name}\ndescription: plugin rule\n---\n# {rule_name}\n",
        encoding="utf-8",
    )
    return str(rule_dir)


class TestToolRegistryIntegration:
    """ToolRegistry 对插件工具的登记与撤销。"""

    def test_register_and_unregister_plugin_tool(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
        tool_file = _make_plugin_tool(tmp_path, "demo_plugin", "demo_tool")

        from jarvis.jarvis_tools.registry import ToolRegistry

        tr = ToolRegistry.__new__(ToolRegistry)
        tr.tools = {}
        tr._all_tools = {}
        tr._builtin_tool_names = set()
        tr._external_tool_sources = {}
        tr._required_tools = []

        assert tr.register_tool_by_file(tool_file)
        pr = PluginRegistry.instance()
        assert pr.get_plugin_tools("demo_plugin") == ["demo_tool"]
        assert "demo_tool" in tr.tools

        # 撤销
        count = tr.unregister_tools_by_plugin("demo_plugin")
        assert count == 1
        assert "demo_tool" not in tr.tools
        assert pr.get_plugin_tools("demo_plugin") == []

    def test_builtin_tool_not_affected(self, tmp_path, monkeypatch):
        """撤销插件工具不影响内置工具。"""
        monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
        tool_file = _make_plugin_tool(tmp_path, "demo_plugin", "demo_tool")

        from jarvis.jarvis_tools.registry import ToolRegistry

        tr = ToolRegistry.__new__(ToolRegistry)
        tr.tools = {}
        tr._all_tools = {}
        tr._builtin_tool_names = {"builtin_tool"}
        tr._external_tool_sources = {}
        tr._required_tools = []

        # 模拟内置工具
        tr.tools["builtin_tool"] = object()
        tr._all_tools["builtin_tool"] = object()

        assert tr.register_tool_by_file(tool_file)
        tr.unregister_tools_by_plugin("demo_plugin")
        # 内置工具仍在
        assert "builtin_tool" in tr.tools


class TestRulesManagerIntegration:
    """RulesManager 对插件规则的登记与撤销。"""

    def test_register_and_unregister_plugin_rule(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
        rule_dir = _make_plugin_rule(tmp_path, "demo_plugin", "demo_rule")

        from jarvis.jarvis_utils.config import set_global_config_data, set_config
        from jarvis.jarvis_agent.rules_manager import RulesManager

        # 构造完整规则目录结构（central + project + rules_load_dirs），
        # 使 config 前缀索引正确对应插件规则目录。
        project_dir = tmp_path / "proj"
        (project_dir / ".jarvis" / "rules").mkdir(parents=True, exist_ok=True)
        central_dir = tmp_path / "central"
        (central_dir / "rules").mkdir(parents=True, exist_ok=True)
        set_global_config_data({"rules_load_dirs": [rule_dir]})
        set_config("central_rules_repo", str(central_dir))

        rm = RulesManager(str(project_dir))
        assert rm.load_rule("config1:demo_rule.md")
        pr = PluginRegistry.instance()
        assert pr.get_plugin_rules("demo_plugin") == ["config1:demo_rule.md"]

        # 撤销
        count = rm.unregister_rules_by_plugin("demo_plugin")
        assert count == 1
        assert "config1:demo_rule.md" not in rm.loaded_rules
        assert pr.get_plugin_rules("demo_plugin") == []

    def test_non_plugin_rule_not_registered(self, tmp_path, monkeypatch):
        """非插件来源的规则不登记到 PluginRegistry。"""
        monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
        project_dir = tmp_path / "proj"
        project_rules = project_dir / ".jarvis" / "rules"
        project_rules.mkdir(parents=True, exist_ok=True)
        (project_rules / "proj_rule.md").write_text("# Proj Rule\n", encoding="utf-8")

        from jarvis.jarvis_utils.config import set_global_config_data
        from jarvis.jarvis_agent.rules_manager import RulesManager

        set_global_config_data({})
        rm = RulesManager(str(project_dir))
        assert rm.load_rule("project:proj_rule.md")
        pr = PluginRegistry.instance()
        # 项目规则路径不在 plugins/ 下，不应登记
        assert pr.get_plugin_rules("demo_plugin") == []
        assert pr.registered_plugins() == []
