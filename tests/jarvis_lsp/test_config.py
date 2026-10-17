"""LSP 配置读取器测试：验证插件 lsp 扩展点合并后的配置可被 LSPConfigReader 消费"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

import pytest

from jarvis.jarvis_lsp.config import LSPConfigReader
from jarvis.jarvis_utils.config import set_global_config_data


@pytest.fixture(autouse=True)
def _reset_global_config():
    """每个测试前清空全局配置，避免用例间相互污染"""
    set_global_config_data({})
    yield
    set_global_config_data({})


def test_reader_reads_plugin_merged_lsp_languages():
    """插件合并进全局的 lsp.languages 可被 LSPConfigReader 读取"""
    # 模拟 _load_plugin_configs 合并插件 lsp 扩展点后的全局配置
    set_global_config_data(
        {
            "lsp": {
                "languages": {
                    "python": {
                        "command": "pyright-langserver",
                        "args": ["--stdio"],
                        "file_extensions": [".py"],
                    }
                }
            }
        }
    )

    reader = LSPConfigReader()
    config = reader.load_config()

    # 插件声明的语言生效
    assert "python" in config.languages
    python_cfg = config.languages["python"]
    assert python_cfg.command == "pyright-langserver"
    assert python_cfg.args == ["--stdio"]
    assert ".py" in python_cfg.file_extensions


def test_reader_detects_language_from_plugin_extension():
    """插件声明的文件扩展名可被语言检测识别"""
    set_global_config_data(
        {
            "lsp": {
                "languages": {
                    "python": {
                        "command": "pyright-langserver",
                        "file_extensions": [".py"],
                    }
                }
            }
        }
    )

    reader = LSPConfigReader()
    assert reader.detect_language("/tmp/foo.py") == "python"


def test_reader_plugin_language_overrides_default():
    """插件声明的语言整体覆盖内置默认同名项"""
    set_global_config_data(
        {
            "lsp": {
                "languages": {
                    "python": {
                        "command": "plugin-pyright",
                        "args": ["--stdio"],
                        "file_extensions": [".py"],
                        "root_markers": ["pyproject.toml"],
                    }
                }
            }
        }
    )

    reader = LSPConfigReader()
    config = reader.load_config()

    # 内置默认 python 项被插件配置整体覆盖
    assert config.languages["python"].command == "plugin-pyright"
    assert config.languages["python"].root_markers == ["pyproject.toml"]
