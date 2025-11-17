# -*- coding: utf-8 -*-
"""jarvis_platform_manager.main 模块单元测试"""

import yaml
from unittest.mock import patch

from jarvis.jarvis_platform_manager.main import validate_platform_model, load_role_config


class TestValidatePlatformModel:
    """测试 validate_platform_model 函数"""

    @patch("jarvis.jarvis_platform_manager.main.print")
    def test_valid_platform_and_model(self, mock_print):
        """测试有效的平台和模型"""
        result = validate_platform_model("openai", "gpt-4")
        assert result is True

    @patch("jarvis.jarvis_platform_manager.main.print")
    def test_missing_platform(self, mock_print):
        """测试缺少平台"""
        result = validate_platform_model(None, "gpt-4")
        assert result is False
        mock_print.assert_called_once()

    @patch("jarvis.jarvis_platform_manager.main.print")
    def test_missing_model(self, mock_print):
        """测试缺少模型"""
        result = validate_platform_model("openai", None)
        assert result is False
        mock_print.assert_called_once()

    @patch("jarvis.jarvis_platform_manager.main.print")
    def test_both_missing(self, mock_print):
        """测试平台和模型都缺少"""
        result = validate_platform_model(None, None)
        assert result is False
        mock_print.assert_called_once()

    @patch("jarvis.jarvis_platform_manager.main.print")
    def test_empty_string_platform(self, mock_print):
        """测试空字符串平台"""
        result = validate_platform_model("", "gpt-4")
        assert result is False

    @patch("jarvis.jarvis_platform_manager.main.print")
    def test_empty_string_model(self, mock_print):
        """测试空字符串模型"""
        result = validate_platform_model("openai", "")
        assert result is False


class TestLoadRoleConfig:
    """测试 load_role_config 函数"""

    def test_valid_yaml_config(self, temp_dir):
        """测试有效的 YAML 配置"""
        config_file = temp_dir / "roles.yaml"
        config_data = {
            "roles": [
                {
                    "name": "test_role",
                    "description": "Test role",
                    "platform": "openai",
                    "model": "gpt-4",
                    "system_prompt": "You are a test assistant",
                }
            ]
        }
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        result = load_role_config(str(config_file))
        assert result == config_data

    def test_nonexistent_file(self, temp_dir):
        """测试不存在的文件"""
        nonexistent = temp_dir / "nonexistent.yaml"
        with patch("jarvis.jarvis_platform_manager.main.print") as mock_print:
            result = load_role_config(str(nonexistent))
            assert result == {}
            mock_print.assert_called_once()

    def test_invalid_yaml(self, temp_dir):
        """测试无效的 YAML"""
        config_file = temp_dir / "invalid.yaml"
        config_file.write_text("invalid: yaml: content: [", encoding="utf-8")

        with patch("jarvis.jarvis_platform_manager.main.print") as mock_print:
            result = load_role_config(str(config_file))
            assert result == {}
            mock_print.assert_called_once()

    def test_empty_file(self, temp_dir):
        """测试空文件"""
        config_file = temp_dir / "empty.yaml"
        config_file.write_text("", encoding="utf-8")

        result = load_role_config(str(config_file))
        assert result == {}

    def test_empty_config_dict(self, temp_dir):
        """测试空配置字典"""
        config_file = temp_dir / "empty_dict.yaml"
        config_file.write_text("{}", encoding="utf-8")

        result = load_role_config(str(config_file))
        assert result == {}

    def test_multiple_roles(self, temp_dir):
        """测试多个角色"""
        config_file = temp_dir / "multiple_roles.yaml"
        config_data = {
            "roles": [
                {
                    "name": "role1",
                    "description": "Role 1",
                    "platform": "openai",
                    "model": "gpt-4",
                },
                {
                    "name": "role2",
                    "description": "Role 2",
                    "platform": "kimi",
                    "model": "moonshot-v1-8k",
                },
            ]
        }
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        result = load_role_config(str(config_file))
        assert result == config_data
        assert len(result["roles"]) == 2

