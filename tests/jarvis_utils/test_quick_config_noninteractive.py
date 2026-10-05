# -*- coding: utf-8 -*-
"""jarvis_utils 无交互快速配置的单元测试

覆盖：
1. config.py 的环境变量覆盖（JARVIS_PLATFORM / JARVIS_MODEL），用于 CI 运行期覆盖模型/平台
2. quick_config.py 的 run_quick_config_noninteractive，用于 CI 持久化写入 config.yaml
"""

import yaml
import pytest

from jarvis.jarvis_utils import config as config_mod
from jarvis.jarvis_utils import quick_config


@pytest.fixture
def clear_env_overrides(monkeypatch):
    """清除环境变量覆盖，保证测试隔离"""
    monkeypatch.delenv("JARVIS_PLATFORM", raising=False)
    monkeypatch.delenv("JARVIS_MODEL", raising=False)


class TestEnvVarOverride:
    """测试 config.py 的环境变量覆盖机制"""

    def test_default_no_override(self, clear_env_overrides):
        """不设环境变量时返回默认值"""
        assert config_mod.get_normal_platform_name() == "openai"
        assert config_mod.get_normal_model_name() == "gpt-5"

    def test_model_override(self, clear_env_overrides, monkeypatch):
        """JARVIS_MODEL 覆盖 model"""
        monkeypatch.setenv("JARVIS_MODEL", "deepseek-chat")
        assert config_mod.get_normal_model_name() == "deepseek-chat"

    def test_platform_override(self, clear_env_overrides, monkeypatch):
        """JARVIS_PLATFORM 覆盖 platform"""
        monkeypatch.setenv("JARVIS_PLATFORM", "claude")
        assert config_mod.get_normal_platform_name() == "claude"

    def test_both_override(self, clear_env_overrides, monkeypatch):
        """JARVIS_MODEL + JARVIS_PLATFORM 同时覆盖"""
        monkeypatch.setenv("JARVIS_MODEL", "claude-3-5-sonnet")
        monkeypatch.setenv("JARVIS_PLATFORM", "claude")
        assert config_mod.get_normal_platform_name() == "claude"
        assert config_mod.get_normal_model_name() == "claude-3-5-sonnet"

    def test_env_priority_over_config(self, clear_env_overrides, monkeypatch):
        """环境变量优先级高于 config.yaml 中的配置"""
        original = config_mod.GLOBAL_CONFIG_DATA.get("model", None)
        try:
            config_mod.GLOBAL_CONFIG_DATA["model"] = "config-model"
            monkeypatch.setenv("JARVIS_MODEL", "env-model")
            assert config_mod.get_normal_model_name() == "env-model"
        finally:
            if original is not None:
                config_mod.GLOBAL_CONFIG_DATA["model"] = original
            else:
                config_mod.GLOBAL_CONFIG_DATA.pop("model", None)


class TestQuickConfigNoninteractive:
    """测试 jqc 非交互模式写入 config.yaml"""

    @pytest.fixture
    def isolated_home(self, tmp_path, monkeypatch):
        """把 HOME 指向临时目录，避免污染真实 ~/.jarvis"""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        return home

    def test_writes_llms_and_groups(self, isolated_home, monkeypatch):
        """非交互写入 llms/llm_groups/llm_group 结构正确"""
        monkeypatch.setattr(quick_config, "init_env", lambda *a, **k: None)
        quick_config.run_quick_config_noninteractive(
            platform="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test-123",
            model="gpt-4o",
            group="default",
            skip_test=True,
        )
        config_path = isolated_home / ".jarvis" / "config.yaml"
        assert config_path.exists()
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        # llms 包含该模型配置
        llm_entry = next(v for v in data["llms"].values() if v.get("model") == "gpt-4o")
        assert llm_entry["platform"] == "openai"
        assert llm_entry["max_input_token_count"] == 200000
        assert llm_entry["llm_config"]["openai_api_key"] == "sk-test-123"
        assert llm_entry["llm_config"]["openai_api_base"] == "https://api.openai.com/v1"
        # llm_groups 与默认组
        assert (
            data["llm_groups"]["default"]["normal_llm"] == list(data["llms"].keys())[0]
        )
        assert data["llm_group"] == "default"

    def test_claude_platform(self, isolated_home, monkeypatch):
        """claude 平台写入 anthropic 字段"""
        monkeypatch.setattr(quick_config, "init_env", lambda *a, **k: None)
        quick_config.run_quick_config_noninteractive(
            platform="claude",
            base_url="https://api.anthropic.com",
            api_key="sk-anthropic",
            model="claude-3-5-sonnet",
            skip_test=True,
        )
        config_path = isolated_home / ".jarvis" / "config.yaml"
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        llm_entry = next(
            v for v in data["llms"].values() if v.get("model") == "claude-3-5-sonnet"
        )
        assert llm_entry["llm_config"]["anthropic_api_key"] == "sk-anthropic"
        assert (
            llm_entry["llm_config"]["anthropic_base_url"] == "https://api.anthropic.com"
        )

    def test_reuse_existing_model_config(self, isolated_home, monkeypatch):
        """重复配置同一模型时复用已有 llms 配置，不新增"""
        monkeypatch.setattr(quick_config, "init_env", lambda *a, **k: None)
        quick_config.run_quick_config_noninteractive(
            platform="openai",
            base_url="https://api.openai.com/v1",
            api_key="k1",
            model="gpt-4o",
            skip_test=True,
        )
        quick_config.run_quick_config_noninteractive(
            platform="openai",
            base_url="https://api.openai.com/v1",
            api_key="k2",
            model="gpt-4o",
            skip_test=True,
        )
        config_path = isolated_home / ".jarvis" / "config.yaml"
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        gpt4o_entries = [v for v in data["llms"].values() if v.get("model") == "gpt-4o"]
        assert len(gpt4o_entries) == 1
        assert gpt4o_entries[0]["llm_config"]["openai_api_key"] == "k2"

    def test_unsupported_platform_raises(self, isolated_home, monkeypatch):
        """不支持的平台类型抛错"""
        monkeypatch.setattr(quick_config, "init_env", lambda *a, **k: None)
        with pytest.raises(Exception):
            quick_config.run_quick_config_noninteractive(
                platform="foo",
                base_url="https://x",
                api_key="k",
                model="m",
                skip_test=True,
            )
