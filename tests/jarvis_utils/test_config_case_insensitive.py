# -*- coding: utf-8 -*-
"""
测试配置键大小写不敏感功能

验证GLOBAL_CONFIG_DATA使用CaseInsensitiveDict后，配置键访问不再区分大小写
"""

import pytest

from jarvis.jarvis_utils.config import (
    GLOBAL_CONFIG_DATA,
    set_config,
    get_shell_name,
    get_data_dir,
    is_print_prompt,
    get_normal_platform_name,
    get_normal_model_name,
)
from jarvis.jarvis_utils.collections import CaseInsensitiveDict


def test_global_config_is_case_insensitive():
    """验证全局配置使用CaseInsensitiveDict"""
    assert isinstance(GLOBAL_CONFIG_DATA, CaseInsensitiveDict)


def test_case_insensitive_key_access():
    """测试键访问大小写不敏感"""
    # 清理测试环境
    original_data = dict(GLOBAL_CONFIG_DATA)
    GLOBAL_CONFIG_DATA.clear()

    try:
        # 设置配置
        set_config("Test_Key", "test_value")

        # 验证可以通过不同大小写访问
        assert GLOBAL_CONFIG_DATA.get("TEST_KEY") == "test_value"
        assert GLOBAL_CONFIG_DATA.get("test_key") == "test_value"
        assert GLOBAL_CONFIG_DATA.get("Test_Key") == "test_value"

        # 验证覆盖行为
        set_config("TEST_key", "new_value")
        assert GLOBAL_CONFIG_DATA.get("test_KEY") == "new_value"
        assert len(GLOBAL_CONFIG_DATA) == 1

    finally:
        # 恢复原始数据
        GLOBAL_CONFIG_DATA.clear()
        GLOBAL_CONFIG_DATA.update(original_data)


def test_config_functions_case_insensitive():
    """测试配置函数的大小写不敏感访问"""
    # 保存原始数据
    original_data = dict(GLOBAL_CONFIG_DATA)
    GLOBAL_CONFIG_DATA.clear()

    try:
        # 测试平台配置
        set_config("JARVIS_PLATFORM", "test_platform")
        assert get_normal_platform_name() == "test_platform"

        # 测试模型配置
        set_config("JARVIS_MODEL", "test_model")
        assert get_normal_model_name() == "test_model"

        # 测试数据路径配置
        set_config("JARVIS_DATA_PATH", "/test/path")
        assert get_data_dir() == "/test/path"

        # 测试打印提示配置
        set_config("JARVIS_PRINT_PROMPT", True)
        assert is_print_prompt() is True

        # 测试shell配置
        set_config("SHELL", "/bin/zsh")
        assert get_shell_name() == "zsh"

        # 验证小写形式也能工作
        set_config("jarvis_platform", "lower_platform")
        assert get_normal_platform_name() == "lower_platform"

    finally:
        # 恢复原始数据
        GLOBAL_CONFIG_DATA.clear()
        GLOBAL_CONFIG_DATA.update(original_data)


def test_case_insensitive_dict_behavior():
    """测试CaseInsensitiveDict的基本行为"""
    # 清理测试环境
    original_data = dict(GLOBAL_CONFIG_DATA)
    GLOBAL_CONFIG_DATA.clear()

    try:
        # 添加数据
        data = {
            "Content-Type": "text/plain",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        }

        for key, value in data.items():
            set_config(key, value)

        # 验证大小写不敏感访问
        assert GLOBAL_CONFIG_DATA.get("content-type") == "text/plain"
        assert GLOBAL_CONFIG_DATA.get("ACCEPT") == "application/json"
        assert GLOBAL_CONFIG_DATA.get("user-agent") == "Mozilla/5.0"

        # 验证键存在检查
        assert "content-type" in GLOBAL_CONFIG_DATA
        assert "CONTENT-TYPE" in GLOBAL_CONFIG_DATA
        assert "Content-Type" in GLOBAL_CONFIG_DATA

        # 验证迭代
        keys = list(GLOBAL_CONFIG_DATA.keys())
        values = list(GLOBAL_CONFIG_DATA.values())
        assert len(keys) == 3
        assert "text/plain" in values

    finally:
        # 恢复原始数据
        GLOBAL_CONFIG_DATA.clear()
        GLOBAL_CONFIG_DATA.update(original_data)


if __name__ == "__main__":
    import pytest

    pytest.main([__file__])
