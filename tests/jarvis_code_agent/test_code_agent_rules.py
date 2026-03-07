# -*- coding: utf-8 -*-
"""code_agent_rules.py 单元测试"""

from pathlib import Path
from unittest.mock import patch


from jarvis.jarvis_agent.rules_manager import RulesManager


class TestRulesManager:
    """测试 RulesManager 类"""

    @patch("jarvis.jarvis_agent.rules_manager.get_data_dir")
    def test_get_named_rule_not_found(self, mock_get_data_dir, tmp_path):
        """测试规则不存在的情况"""
        mock_get_data_dir.return_value = str(tmp_path)
        manager = RulesManager("/tmp/test")
        result = manager.get_named_rule("nonexistent")

        assert result is None

    @patch("jarvis.jarvis_agent.rules_manager.get_data_dir")
    def test_get_named_rule_from_global_dir(self, mock_get_data_dir, tmp_path):
        """测试从全局 rules 目录获取 .md 规则文件"""
        data_dir = str(tmp_path)
        mock_get_data_dir.return_value = data_dir
        rules_dir = Path(data_dir) / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        rule_file = rules_dir / "test_rule.md"
        rule_file.write_text("Global test rule content", encoding="utf-8")

        manager = RulesManager("/tmp/test")
        result = manager.get_named_rule("global:test_rule")

        assert result == "Global test rule content"

    @patch("jarvis.jarvis_agent.rules_manager.get_data_dir")
    def test_get_named_rule_from_project_dir(self, mock_get_data_dir, tmp_path):
        """测试从项目 .jarvis/rules 目录获取 .md 规则文件"""
        data_dir = str(tmp_path)
        mock_get_data_dir.return_value = data_dir
        project_root = tmp_path / "project"
        project_root.mkdir()
        project_rules_dir = project_root / ".jarvis" / "rules"
        project_rules_dir.mkdir(parents=True, exist_ok=True)
        rule_file = project_rules_dir / "test_rule.md"
        rule_file.write_text("Project test rule content", encoding="utf-8")

        manager = RulesManager(str(project_root))
        result = manager.get_named_rule("project:test_rule")

        assert result == "Project test rule content"

    @patch("jarvis.jarvis_agent.rules_manager.get_data_dir")
    def test_get_named_rule_project_overrides_global(self, mock_get_data_dir, tmp_path):
        """测试项目规则覆盖全局规则（.md 文件）"""
        data_dir = str(tmp_path)
        mock_get_data_dir.return_value = data_dir
        global_rules_dir = Path(data_dir) / "rules"
        global_rules_dir.mkdir(parents=True, exist_ok=True)
        global_rule = global_rules_dir / "test_rule.md"
        global_rule.write_text("Global rule content", encoding="utf-8")

        project_root = tmp_path / "project"
        project_root.mkdir()
        project_rules_dir = project_root / ".jarvis" / "rules"
        project_rules_dir.mkdir(parents=True, exist_ok=True)
        project_rule = project_rules_dir / "test_rule.md"
        project_rule.write_text("Project rule content", encoding="utf-8")

        manager = RulesManager(str(project_root))

        # 项目规则应该被优先加载
        result_project = manager.get_named_rule("project:test_rule")
        assert result_project == "Project rule content"

        # 全局规则也应该可以访问
        result_global = manager.get_named_rule("global:test_rule")
        assert result_global == "Global rule content"

    @patch("jarvis.jarvis_agent.rules_manager.get_data_dir")
    def test_load_all_rules_with_md_files(self, mock_get_data_dir, tmp_path):
        """测试加载 .md 规则文件"""
        data_dir = str(tmp_path)
        mock_get_data_dir.return_value = data_dir
        rules_dir = Path(data_dir) / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        rule1 = rules_dir / "rule1.md"
        rule1.write_text("Rule 1 content", encoding="utf-8")
        rule2 = rules_dir / "rule2.md"
        rule2.write_text("Rule 2 content", encoding="utf-8")

        manager = RulesManager("/tmp/test")
        merged_rules, loaded_names = manager.load_all_rules("global:rule1,global:rule2")

        assert "Rule 1 content" in merged_rules
        assert "Rule 2 content" in merged_rules
        assert "global:rule1" in loaded_names
        assert "global:rule2" in loaded_names

    @patch("jarvis.jarvis_agent.rules_manager.get_data_dir")
    def test_load_all_rules_with_whitespace_in_names(self, mock_get_data_dir, tmp_path):
        """测试规则名称包含空白字符的情况"""
        data_dir = str(tmp_path)
        mock_get_data_dir.return_value = data_dir
        rules_dir = Path(data_dir) / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        rule_file = rules_dir / "rule1.md"
        rule_file.write_text("Named rule content", encoding="utf-8")

        manager = RulesManager("/tmp/test")
        merged_rules, loaded_names = manager.load_all_rules(
            " global:rule1 , global:rule2 "
        )

        assert "Named rule content" in merged_rules
        assert "global:rule1" in loaded_names
        # rule2 文件不存在，不应该被加载
        assert "global:rule2" not in loaded_names

    @patch("jarvis.jarvis_agent.rules_manager.get_data_dir")
    def test_rule_with_yaml_front_matter(self, mock_get_data_dir, tmp_path):
        """测试带有 YAML Front Matter 的规则文件"""
        data_dir = str(tmp_path)
        mock_get_data_dir.return_value = data_dir
        rules_dir = Path(data_dir) / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        rule_file = rules_dir / "test_rule.md"
        rule_file.write_text(
            "---\ndescription: Test rule description\n---\nActual rule content here",
            encoding="utf-8",
        )

        manager = RulesManager("/tmp/test")
        result = manager.get_named_rule("global:test_rule")

        # YAML Front Matter 应该被移除
        assert "description: Test rule description" not in result
        assert "Actual rule content here" in result

    @patch("jarvis.jarvis_agent.rules_manager.get_data_dir")
    def test_activate_and_deactivate_rule(self, mock_get_data_dir, tmp_path):
        """测试激活和停用规则"""
        data_dir = str(tmp_path)
        mock_get_data_dir.return_value = data_dir
        rules_dir = Path(data_dir) / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        rule_file = rules_dir / "test_rule.md"
        rule_file.write_text("Test rule content", encoding="utf-8")

        manager = RulesManager("/tmp/test")

        # 激活规则
        assert manager.activate_rule("global:test_rule") is True
        assert manager.get_rule_status("global:test_rule") == "active"
        assert "Test rule content" in manager.get_active_rules_content()

        # 停用规则
        assert manager.deactivate_rule("global:test_rule") is True
        assert manager.get_rule_status("global:test_rule") == "loaded"
        assert manager.get_active_rules_content() == ""

    @patch("jarvis.jarvis_agent.rules_manager.get_data_dir")
    def test_get_rule_file_path(self, mock_get_data_dir, tmp_path):
        """测试获取规则文件路径"""
        data_dir = str(tmp_path)
        mock_get_data_dir.return_value = data_dir
        project_root = tmp_path / "project"
        project_root.mkdir()
        project_rules_dir = project_root / ".jarvis" / "rules"
        project_rules_dir.mkdir(parents=True, exist_ok=True)
        rule_file = project_rules_dir / "test_rule.md"
        rule_file.write_text("Test content", encoding="utf-8")

        manager = RulesManager(str(project_root))
        path = manager.get_rule_file_path("project:test_rule.md")

        assert path.endswith(".jarvis/rules/test_rule.md")
