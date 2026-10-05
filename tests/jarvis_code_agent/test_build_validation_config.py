# -*- coding: utf-8 -*-
"""build_validation_config.py 单元测试"""

import yaml

from jarvis.jarvis_code_agent.build_validation_config import (
    BuildValidationConfig,
    STATE_FILE_NAME,
)
from jarvis.jarvis_utils import config as config_module
from jarvis.jarvis_utils.config import GLOBAL_CONFIG_DATA


def _mock_update(monkeypatch):
    """模拟 update_build_validation_config：只同步 GLOBAL_CONFIG_DATA，不写磁盘"""

    def fake_update(project_root, updates):
        bv = dict(GLOBAL_CONFIG_DATA.get("build_validation", {}))
        bv.update(updates)
        GLOBAL_CONFIG_DATA["build_validation"] = bv
        return True

    monkeypatch.setattr(config_module, "update_build_validation_config", fake_update)


class TestBuildValidationConfig:
    """测试 BuildValidationConfig 类"""

    def test_init(self, tmp_path):
        """测试初始化"""
        config = BuildValidationConfig(str(tmp_path))

        assert config.project_root == str(tmp_path)
        assert config.config_dir == str(tmp_path / ".jarvis")
        assert config.state_path == str(tmp_path / ".jarvis" / STATE_FILE_NAME)
        assert config._state is None

    def test_is_build_validation_disabled_default(self, tmp_path, monkeypatch):
        """测试默认情况下构建验证未禁用"""
        monkeypatch.setitem(GLOBAL_CONFIG_DATA, "build_validation", {})
        config = BuildValidationConfig(str(tmp_path))
        result = config.is_build_validation_disabled()

        assert result is False

    def test_is_build_validation_disabled_when_disabled(self, tmp_path, monkeypatch):
        """测试构建验证被禁用的情况"""
        _mock_update(monkeypatch)
        config = BuildValidationConfig(str(tmp_path))
        config.disable_build_validation("Test reason")
        result = config.is_build_validation_disabled()

        assert result is True

    def test_disable_build_validation(self, tmp_path, monkeypatch):
        """测试禁用构建验证"""
        _mock_update(monkeypatch)
        config = BuildValidationConfig(str(tmp_path))
        result = config.disable_build_validation("Test reason")

        assert result is True
        assert config.is_build_validation_disabled() is True
        assert config.get_disable_reason() == "Test reason"

    def test_disable_build_validation_without_reason(self, tmp_path, monkeypatch):
        """测试禁用构建验证但不提供原因"""
        _mock_update(monkeypatch)
        config = BuildValidationConfig(str(tmp_path))
        result = config.disable_build_validation()

        assert result is True
        assert config.is_build_validation_disabled() is True
        assert config.get_disable_reason() is None

    def test_enable_build_validation(self, tmp_path, monkeypatch):
        """测试重新启用构建验证"""
        _mock_update(monkeypatch)
        config = BuildValidationConfig(str(tmp_path))
        config.disable_build_validation("Test reason")
        result = config.enable_build_validation()

        assert result is True
        assert config.is_build_validation_disabled() is False

    def test_get_disable_reason(self, tmp_path, monkeypatch):
        """测试获取禁用原因"""
        _mock_update(monkeypatch)
        config = BuildValidationConfig(str(tmp_path))
        config.disable_build_validation("Test reason")
        result = config.get_disable_reason()

        assert result == "Test reason"

    def test_get_disable_reason_not_disabled(self, tmp_path, monkeypatch):
        """测试未禁用时获取禁用原因"""
        monkeypatch.setitem(GLOBAL_CONFIG_DATA, "build_validation", {})
        config = BuildValidationConfig(str(tmp_path))
        result = config.get_disable_reason()

        assert result is None

    def test_get_custom_build_command_default(self, tmp_path, monkeypatch):
        """测试默认情况下未配置自定义构建命令"""
        monkeypatch.setitem(GLOBAL_CONFIG_DATA, "build_validation", {})
        config = BuildValidationConfig(str(tmp_path))
        result = config.get_custom_build_command()

        assert result is None

    def test_set_custom_build_command(self, tmp_path, monkeypatch):
        """测试设置自定义构建命令"""
        _mock_update(monkeypatch)
        config = BuildValidationConfig(str(tmp_path))
        result = config.set_custom_build_command("make && make test")

        assert result is True
        assert config.get_custom_build_command() == "make && make test"

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

    def test_state_persistence(self, tmp_path, monkeypatch):
        """测试运行时状态持久化（跨实例）"""
        _mock_update(monkeypatch)
        config1 = BuildValidationConfig(str(tmp_path))
        config1.disable_build_validation("Test reason")
        config1.set_selected_build_system("rust")
        config1.mark_as_asked()

        # 创建新实例，应该能读取之前的运行时状态
        config2 = BuildValidationConfig(str(tmp_path))

        assert config2.get_selected_build_system() == "rust"
        assert config2.has_been_asked() is True

    def test_static_config_persistence(self, tmp_path, monkeypatch):
        """测试静态配置持久化（跨实例，通过 GLOBAL_CONFIG_DATA）"""
        _mock_update(monkeypatch)
        config1 = BuildValidationConfig(str(tmp_path))
        config1.disable_build_validation("Test reason")

        # 创建新实例，静态配置从 GLOBAL_CONFIG_DATA 读取
        config2 = BuildValidationConfig(str(tmp_path))

        assert config2.is_build_validation_disabled() is True
        assert config2.get_disable_reason() == "Test reason"

    def test_load_state_file_not_exists(self, tmp_path):
        """测试状态文件不存在时加载默认配置"""
        config = BuildValidationConfig(str(tmp_path))
        state_data = config._load_state()

        assert state_data == {}

    def test_load_state_file_exists(self, tmp_path):
        """测试状态文件存在时加载配置"""
        config_dir = tmp_path / ".jarvis"
        config_dir.mkdir()
        state_file = config_dir / STATE_FILE_NAME
        state_data = {
            "has_been_asked": True,
            "selected_build_system": "rust",
        }
        with open(state_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(state_data, f)

        config = BuildValidationConfig(str(tmp_path))
        loaded_data = config._load_state()

        assert loaded_data["has_been_asked"] is True
        assert loaded_data["selected_build_system"] == "rust"

    def test_load_state_invalid_yaml(self, tmp_path):
        """测试状态文件格式无效时使用默认配置"""
        config_dir = tmp_path / ".jarvis"
        config_dir.mkdir()
        state_file = config_dir / STATE_FILE_NAME
        state_file.write_text("invalid: yaml: content: [", encoding="utf-8")

        config = BuildValidationConfig(str(tmp_path))
        loaded_data = config._load_state()

        # 应该返回空配置而不是抛出异常
        assert isinstance(loaded_data, dict)

    def test_save_state_creates_directory(self, tmp_path):
        """测试保存状态时自动创建目录"""
        config = BuildValidationConfig(str(tmp_path))
        config.mark_as_asked()

        assert (tmp_path / ".jarvis").exists()
        assert (tmp_path / ".jarvis" / STATE_FILE_NAME).exists()

    def test_state_caching(self, tmp_path):
        """测试状态缓存机制"""
        config = BuildValidationConfig(str(tmp_path))
        config.mark_as_asked()

        # 第一次调用应该加载状态
        state1 = config._load_state()
        # 第二次调用应该使用缓存
        state2 = config._load_state()

        assert state1 is state2

    def test_multiple_config_changes(self, tmp_path, monkeypatch):
        """测试多次配置更改"""
        _mock_update(monkeypatch)
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

    def test_write_config_yaml_preserves_schema_header(self, tmp_path, monkeypatch):
        """测试真实写入项目级 config.yaml 时保留 schema 注释头"""
        config_dir = tmp_path / ".jarvis"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text(
            "# yaml-language-server: $schema=../src/jarvis/jarvis_data/config_schema.json\n"
            "# enable_tmux: true\n",
            encoding="utf-8",
        )

        config = BuildValidationConfig(str(tmp_path))
        result = config.disable_build_validation("Test reason")

        assert result is True
        # schema 注释头保留
        content = config_file.read_text(encoding="utf-8")
        assert content.startswith("# yaml-language-server: $schema=")
        # build_validation 配置写入
        parsed = yaml.safe_load(content)
        assert parsed["build_validation"]["disable_build_validation"] is True
        assert parsed["build_validation"]["disable_reason"] == "Test reason"
        # 运行时状态写入独立文件
        assert (config_dir / STATE_FILE_NAME).exists()
        # 清理 GLOBAL_CONFIG_DATA，避免污染其他测试
        GLOBAL_CONFIG_DATA.pop("build_validation", None)
