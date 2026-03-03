# -*- coding: utf-8 -*-
"""code_agent_rules.py 单元测试"""

from pathlib import Path
from unittest.mock import patch


from jarvis.jarvis_agent.rules_manager import RulesManager


class TestRulesManager:
    """测试 RulesManager 类"""

    @patch("jarvis.jarvis_agent.rules_manager.get_data_dir")
    def test_get_named_rule_from_global(self, mock_get_data_dir, tmp_path):
        """测试从全局 rules.yaml 获取命名规则"""
        data_dir = str(tmp_path)
        mock_get_data_dir.return_value = data_dir
        rules_yaml = Path(data_dir) / "rules.yaml"
        rules_yaml.write_text(
            "rule1: Global rule 1\nrule2: Global rule 2", encoding="utf-8"
        )

        manager = RulesManager("/tmp/test")
        result = manager.get_named_rule("rule1")

        assert result == "Global rule 1"

    @patch("jarvis.jarvis_agent.rules_manager.get_data_dir")
    def test_get_named_rule_from_project(self, mock_get_data_dir, tmp_path):
        """测试从项目 rules.yaml 获取命名规则"""
        data_dir = str(tmp_path)
        mock_get_data_dir.return_value = data_dir
        project_root = tmp_path / "project"
        project_root.mkdir()
        project_rules_yaml = project_root / ".jarvis" / "rules.yaml"
        project_rules_yaml.parent.mkdir(parents=True, exist_ok=True)
        project_rules_yaml.write_text(
            "rule1: Project rule 1\nrule2: Project rule 2", encoding="utf-8"
        )

        manager = RulesManager(str(project_root))
        result = manager.get_named_rule("rule1")

        assert result == "Project rule 1"

    @patch("jarvis.jarvis_agent.rules_manager.get_data_dir")
    def test_get_named_rule_project_overrides_global(self, mock_get_data_dir, tmp_path):
        """测试项目规则覆盖全局规则"""
        data_dir = str(tmp_path)
        mock_get_data_dir.return_value = data_dir
        global_rules_yaml = Path(data_dir) / "rules.yaml"
        global_rules_yaml.write_text("rule1: Global rule", encoding="utf-8")

        project_root = tmp_path / "project"
        project_root.mkdir()
        project_rules_yaml = project_root / ".jarvis" / "rules.yaml"
        project_rules_yaml.parent.mkdir(parents=True, exist_ok=True)
        project_rules_yaml.write_text("rule1: Project rule", encoding="utf-8")

        manager = RulesManager(str(project_root))
        result = manager.get_named_rule("rule1")

        assert result == "Project rule"

    @patch("jarvis.jarvis_agent.rules_manager.get_data_dir")
    def test_get_named_rule_not_found(self, mock_get_data_dir, tmp_path):
        """测试规则不存在的情况"""
        mock_get_data_dir.return_value = str(tmp_path)
        manager = RulesManager("/tmp/test")
        result = manager.get_named_rule("nonexistent")

        assert result is None

    @patch("jarvis.jarvis_agent.rules_manager.get_data_dir")
    def test_get_named_rule_non_string_value(self, mock_get_data_dir, tmp_path):
        """测试规则值为非字符串类型的情况"""
        data_dir = str(tmp_path)
        mock_get_data_dir.return_value = data_dir
        rules_yaml = Path(data_dir) / "rules.yaml"
        rules_yaml.write_text("rule1: 123\nrule2: true", encoding="utf-8")

        manager = RulesManager("/tmp/test")
        result1 = manager.get_named_rule("rule1")
        result2 = manager.get_named_rule("rule2")

        assert result1 == "123"
        assert result2 == "True"

    @patch("jarvis.jarvis_agent.rules_manager.get_data_dir")
    def test_load_all_rules_with_named_rules(self, mock_get_data_dir, tmp_path):
        """测试加载命名规则"""
        data_dir = str(tmp_path)
        mock_get_data_dir.return_value = data_dir
        rules_yaml = Path(data_dir) / "rules.yaml"
        rules_yaml.write_text(
            "rule1: Named rule 1\nrule2: Named rule 2", encoding="utf-8"
        )

        manager = RulesManager("/tmp/test")
        merged_rules, loaded_names = manager.load_all_rules("rule1,rule2")

        assert "Named rule 1" in merged_rules
        assert "Named rule 2" in merged_rules
        assert "rule1" in loaded_names
        assert "rule2" in loaded_names

    @patch("jarvis.jarvis_agent.rules_manager.get_data_dir")
    def test_load_all_rules_with_whitespace_in_names(self, mock_get_data_dir, tmp_path):
        """测试规则名称包含空白字符的情况"""
        data_dir = str(tmp_path)
        mock_get_data_dir.return_value = data_dir
        rules_yaml = Path(data_dir) / "rules.yaml"
        rules_yaml.write_text("rule1: Named rule", encoding="utf-8")

        manager = RulesManager("/tmp/test")
        merged_rules, loaded_names = manager.load_all_rules(" rule1 , rule2 ")

        assert "Named rule" in merged_rules
        assert "rule1" in loaded_names
        # rule2 不存在，不应该被加载
        assert "rule2" not in loaded_names
