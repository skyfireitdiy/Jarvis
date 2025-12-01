# -*- coding: utf-8 -*-
"""build_validation_config.py 单元测试"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from jarvis.jarvis_code_agent.build_validation_config import (
    BuildValidationConfig,
    CONFIG_FILE_NAME,
)


class TestBuildValidationConfig:
    """测试 BuildValidationConfig 类"""

    def test_init(self, tmp_path):
        """测试初始化"""
        config = BuildValidationConfig(str(tmp_path))

        assert config.project_root == str(tmp_path)
        assert config.config_dir == str(tmp_path / ".jarvis")
        assert config.config_path == str(tmp_path / ".jarvis" / CONFIG_FILE_NAME)
        assert config._config is None

    def test_is_build_validation_disabled_default(self, tmp_path):
        """测试默认情况下构建验证未禁用"""
        config = BuildValidationConfig(str(tmp_path))
        result = config.is_build_validation_disabled()

        assert result is False

    def test_is_build_validation_disabled_when_disabled(self, tmp_path):
        """测试构建验证被禁用的情况"""
        config = BuildValidationConfig(str(tmp_path))
        config.disable_build_validation("Test reason")
        result = config.is_build_validation_disabled()

        assert result is True

    def test_disable_build_validation(self, tmp_path):
        """测试禁用构建验证"""
        config = BuildValidationConfig(str(tmp_path))
        result = config.disable_build_validation("Test reason")

        assert result is True
        assert config.is_build_validation_disabled() is True
        assert config.get_disable_reason() == "Test reason"

    def test_disable_build_validation_without_reason(self, tmp_path):
        """测试禁用构建验证但不提供原因"""
        config = BuildValidationConfig(str(tmp_path))
        result = config.disable_build_validation()

        assert result is True
        assert config.is_build_validation_disabled() is True
        assert config.get_disable_reason() is None

    def test_enable_build_validation(self, tmp_path):
        """测试重新启用构建验证"""
        config = BuildValidationConfig(str(tmp_path))
        config.disable_build_validation("Test reason")
        result = config.enable_build_validation()

        assert result is True
        assert config.is_build_validation_disabled() is False

    def test_get_disable_reason(self, tmp_path):
        """测试获取禁用原因"""
        config = BuildValidationConfig(str(tmp_path))
        config.disable_build_validation("Test reason")
        result = config.get_disable_reason()

        assert result == "Test reason"

    def test_get_disable_reason_not_disabled(self, tmp_path):
        """测试未禁用时获取禁用原因"""
        config = BuildValidationConfig(str(tmp_path))
        result = config.get_disable_reason()

        assert result is None

    def test_has_been_asked_default(self, tmp_path):
        """测试默认情况下未询问过用户"""
        config = BuildValidationConfig(str(tmp_path))
        result = config.has_been_asked()

        assert result is False

    def test_mark_as_asked(self, tmp_path):
        """测试标记为已询问"""
        config = BuildValidationConfig(str(tmp_path))
        result = config.mark_as_asked()

        assert result is True
        assert config.has_been_asked() is True

    def test_get_selected_build_system_default(self, tmp_path):
        """测试默认情况下未选择构建系统"""
        config = BuildValidationConfig(str(tmp_path))
        result = config.get_selected_build_system()

        assert result is None

    def test_set_selected_build_system(self, tmp_path):
        """测试设置选择的构建系统"""
        config = BuildValidationConfig(str(tmp_path))
        result = config.set_selected_build_system("rust")

        assert result is True
        assert config.get_selected_build_system() == "rust"

    def test_set_selected_build_system_python(self, tmp_path):
        """测试设置 Python 构建系统"""
        config = BuildValidationConfig(str(tmp_path))
        config.set_selected_build_system("python")
        result = config.get_selected_build_system()

        assert result == "python"

    def test_config_persistence(self, tmp_path):
        """测试配置持久化"""
        config1 = BuildValidationConfig(str(tmp_path))
        config1.disable_build_validation("Test reason")
        config1.set_selected_build_system("rust")
        config1.mark_as_asked()

        # 创建新实例，应该能读取之前的配置
        config2 = BuildValidationConfig(str(tmp_path))

        assert config2.is_build_validation_disabled() is True
        assert config2.get_disable_reason() == "Test reason"
        assert config2.get_selected_build_system() == "rust"
        assert config2.has_been_asked() is True

    def test_load_config_file_not_exists(self, tmp_path):
        """测试配置文件不存在时加载默认配置"""
        config = BuildValidationConfig(str(tmp_path))
        config_data = config._load_config()

        assert config_data == {}

    def test_load_config_file_exists(self, tmp_path):
        """测试配置文件存在时加载配置"""
        config_dir = tmp_path / ".jarvis"
        config_dir.mkdir()
        config_file = config_dir / CONFIG_FILE_NAME
        config_data = {
            "disable_build_validation": True,
            "disable_reason": "Test",
            "selected_build_system": "rust",
        }
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        config = BuildValidationConfig(str(tmp_path))
        loaded_data = config._load_config()

        assert loaded_data["disable_build_validation"] is True
        assert loaded_data["disable_reason"] == "Test"
        assert loaded_data["selected_build_system"] == "rust"

    def test_load_config_invalid_yaml(self, tmp_path):
        """测试配置文件格式无效时使用默认配置"""
        config_dir = tmp_path / ".jarvis"
        config_dir.mkdir()
        config_file = config_dir / CONFIG_FILE_NAME
        config_file.write_text("invalid: yaml: content: [", encoding="utf-8")

        config = BuildValidationConfig(str(tmp_path))
        loaded_data = config._load_config()

        # 应该返回空配置而不是抛出异常
        assert isinstance(loaded_data, dict)

    def test_save_config_creates_directory(self, tmp_path):
        """测试保存配置时自动创建目录"""
        config = BuildValidationConfig(str(tmp_path))
        config.disable_build_validation("Test")

        assert (tmp_path / ".jarvis").exists()
        assert (tmp_path / ".jarvis" / CONFIG_FILE_NAME).exists()

    def test_config_caching(self, tmp_path):
        """测试配置缓存机制"""
        config = BuildValidationConfig(str(tmp_path))
        config.disable_build_validation("Test")

        # 第一次调用应该加载配置
        config1 = config._load_config()
        # 第二次调用应该使用缓存
        config2 = config._load_config()

        assert config1 is config2

    def test_disable_reason_persistence(self, tmp_path):
        """测试禁用原因的持久化"""
        config1 = BuildValidationConfig(str(tmp_path))
        config1.disable_build_validation("Persistent reason")

        config2 = BuildValidationConfig(str(tmp_path))
        assert config2.get_disable_reason() == "Persistent reason"

    def test_multiple_config_changes(self, tmp_path):
        """测试多次配置更改"""
        config = BuildValidationConfig(str(tmp_path))

        # 禁用并设置原因
        config.disable_build_validation("Reason 1")
        assert config.get_disable_reason() == "Reason 1"

        # 更改原因
        config.disable_build_validation("Reason 2")
        assert config.get_disable_reason() == "Reason 2"

        # 启用
        config.enable_build_validation()
        assert config.is_build_validation_disabled() is False

        # 再次禁用
        config.disable_build_validation("Reason 3")
        assert config.get_disable_reason() == "Reason 3"
