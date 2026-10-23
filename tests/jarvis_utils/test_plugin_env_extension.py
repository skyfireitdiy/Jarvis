# -*- coding: utf-8 -*-
"""插件 ENV 扩展点测试。

验证：插件 config.yaml 声明的 `ENV` 扩展点字段会被合并进全局配置顶层，
并通过 `_process_env_variables` 注入 `os.environ`（与全局 `ENV` 语义一致）；
插件热加载（reload_plugin_configs）后重新注入。
"""

import os
from pathlib import Path

# 必须在导入 jarvis 模块之前设置环境变量，避免触发交互式配置
os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"

import pytest

from jarvis.jarvis_utils.utils import (
    _PLUGIN_EXTENSION_FIELDS,
    _load_plugin_configs,
    _process_env_variables,
    reload_plugin_configs,
)


def _make_plugin_with_env(plugins_dir: Path, name: str, env: dict) -> Path:
    """构造一个带 ENV 扩展点的最小插件目录。"""
    plugin_dir = plugins_dir / name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "name": name,
        "version": "1.0.0",
        "description": "test plugin",
        "ENV": env,
    }
    (plugin_dir / "config.yaml").write_text(
        __import__("json").dumps(config), encoding="utf-8"
    )
    return plugin_dir


@pytest.fixture()
def isolated_data_dir(tmp_path, monkeypatch):
    """把 JARVIS_DATA_DIR 指向临时目录，隔离插件扫描副作用。"""
    data_dir = tmp_path / "jarvis-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("JARVIS_DATA_DIR", str(data_dir))
    return data_dir


def test_env_is_plugin_extension_field():
    """ENV 应属于插件扩展点字段白名单（合并进全局配置顶层）。"""
    assert "ENV" in _PLUGIN_EXTENSION_FIELDS


def test_plugin_env_merged_into_global_config(isolated_data_dir):
    """插件 config 的 ENV 应合并进全局配置顶层。"""
    plugins_dir = Path(isolated_data_dir) / "plugins"
    _make_plugin_with_env(plugins_dir, "env-plugin", {"MY_PLUGIN_TOKEN": "abc"})

    merged = _load_plugin_configs({"project_name": "test"})
    assert merged.get("ENV", {}).get("MY_PLUGIN_TOKEN") == "abc"


def test_process_env_variables_injects_to_os_environ(isolated_data_dir, monkeypatch):
    """_process_env_variables 应把顶层 ENV 注入 os.environ。"""
    monkeypatch.delenv("MY_PLUGIN_TOKEN", raising=False)
    _process_env_variables({"ENV": {"MY_PLUGIN_TOKEN": "abc"}})
    assert os.environ.get("MY_PLUGIN_TOKEN") == "abc"


def test_reload_plugin_configs_reinjects_env(isolated_data_dir, monkeypatch):
    """插件热加载后 ENV 应重新注入 os.environ。"""
    from jarvis.jarvis_utils.utils import cache_base_config

    plugins_dir = Path(isolated_data_dir) / "plugins"
    _make_plugin_with_env(plugins_dir, "env-plugin", {"RELOAD_ENV_KEY": "xyz"})

    cache_base_config(
        {"project_name": "test", "data_dir": str(isolated_data_dir)},
        str(isolated_data_dir),
    )
    monkeypatch.delenv("RELOAD_ENV_KEY", raising=False)

    assert reload_plugin_configs() is True
    assert os.environ.get("RELOAD_ENV_KEY") == "xyz"
