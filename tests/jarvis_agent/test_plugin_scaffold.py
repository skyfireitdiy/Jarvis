# -*- coding: utf-8 -*-
"""scaffold_plugin 脚手架生成测试。

验证生成的插件骨架符合加载约定：
- 目录结构完整（rules/tools/agents/orchestration/frontend/plugin）
- config.yaml 含 name/version/builtin，可被 yaml 解析
- 工具类名与文件名 stem 一致
- plugin/api.py 语法合法、含 PUBLIC_FUNCTIONS 白名单、函数名是合法 Python 标识符
"""
import importlib.util
import os
import py_compile
import sys

import pytest
import yaml

from jarvis.jarvis_agent.utils import scaffold_plugin


@pytest.fixture
def plugin_dir(tmp_path):
    """生成一个测试插件脚手架，返回其目录路径。"""
    result = scaffold_plugin("my-demo-plugin", output_dir=str(tmp_path))
    assert result is not None, "脚手架生成失败"
    return result


def test_plugin_structure_dirs(plugin_dir):
    """应生成全部扩展点目录（含 plugin/ 私有功能目录）。"""
    for sub in ("rules", "tools", "agents", "orchestration", "frontend", "plugin"):
        assert os.path.isdir(os.path.join(plugin_dir, sub)), f"缺少目录 {sub}"


def test_config_yaml_valid(plugin_dir):
    """config.yaml 应含 name/version/builtin 且可被 yaml 解析。"""
    config_path = os.path.join(plugin_dir, "config.yaml")
    assert os.path.isfile(config_path)
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    assert isinstance(config, dict)
    assert config["name"] == "my-demo-plugin"
    assert config["version"] == "0.1.0"
    assert config.get("builtin") is True
    # 工具/规则扩展点已启用
    assert config.get("tool_load_dirs")
    assert config.get("rules_load_dirs")


def test_tool_module_matches_stem(plugin_dir):
    """工具文件名 stem 应等于工具类 name（注册表加载约定）。"""
    tool_file = os.path.join(plugin_dir, "tools", "my-demo-plugin_tool.py")
    assert os.path.isfile(tool_file)
    # 类名 name 应等于文件名 stem
    stem = "my-demo-plugin_tool"
    with open(tool_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert f'name = "{stem}"' in content


def test_plugin_api_py_valid(plugin_dir):
    """plugin/api.py 应语法合法、含 PUBLIC_FUNCTIONS 白名单、函数名是合法标识符。"""
    api_file = os.path.join(plugin_dir, "plugin", "api.py")
    assert os.path.isfile(api_file)
    # 语法校验
    py_compile.compile(api_file, doraise=True)

    # 动态加载验证 PUBLIC_FUNCTIONS 与函数可调用
    spec = importlib.util.spec_from_file_location("scaffold_api_test", api_file)
    assert spec is not None and spec.loader is not None, "无法加载 api.py"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["scaffold_api_test"] = mod
    spec.loader.exec_module(mod)
    assert isinstance(mod.PUBLIC_FUNCTIONS, list) and mod.PUBLIC_FUNCTIONS
    fn_name = mod.PUBLIC_FUNCTIONS[0]
    # 函数名必须是合法 Python 标识符（连字符被替换为下划线）
    assert fn_name.isidentifier(), f"函数名非法: {fn_name}"
    assert callable(getattr(mod, fn_name))


def test_frontend_files_generated(plugin_dir):
    """frontend/ 应生成 admin_tab.js 与 sidebar_view.js 模板。"""
    assert os.path.isfile(os.path.join(plugin_dir, "frontend", "admin_tab.js"))
    assert os.path.isfile(os.path.join(plugin_dir, "frontend", "sidebar_view.js"))


def test_readme_mentions_plugin_private(plugin_dir):
    """README 应包含 plugin/ 私有功能说明。"""
    readme_path = os.path.join(plugin_dir, "README.md")
    assert os.path.isfile(readme_path)
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "插件私有功能" in content
    assert "PUBLIC_FUNCTIONS" in content
