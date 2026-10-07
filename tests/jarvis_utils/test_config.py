# -*- coding: utf-8 -*-
"""jarvis_utils.config 模块插件功能单元测试"""

import yaml
import pytest

from jarvis.jarvis_utils.config import (
    get_plugin_dirs,
    get_plugin_config,
    get_all_plugin_configs,
    set_global_config_data,
    GLOBAL_CONFIG_DATA,
)
from jarvis.jarvis_utils.utils import _load_plugin_configs


@pytest.fixture
def disable_auto_discover(monkeypatch):
    """禁用自动发现功能，避免测试时加载真实的 ~/.jarvis/plugins 目录"""
    monkeypatch.setenv("JARVIS_DISABLE_AUTO_DISCOVER", "1")


class TestGetPluginDirs:
    """测试 get_plugin_dirs 函数"""

    def test_default_empty_list(self):
        """测试默认返回空列表"""
        # 当 GLOBAL_CONFIG_DATA 中没有 plugin_dirs 时，应返回空列表
        try:
            # 清空配置
            if "plugin_dirs" in GLOBAL_CONFIG_DATA:
                del GLOBAL_CONFIG_DATA["plugin_dirs"]
            result = get_plugin_dirs()
            assert result == []
        finally:
            # 恢复原始配置（如果可能）
            pass

    def test_returns_configured_dirs(self):
        """测试返回配置的插件目录"""
        # 当配置了 plugin_dirs 时，应返回配置的列表
        original_value = GLOBAL_CONFIG_DATA.get("plugin_dirs", None)
        try:
            GLOBAL_CONFIG_DATA["plugin_dirs"] = ["/path/to/plugin1", "/path/to/plugin2"]
            result = get_plugin_dirs()
            assert result == ["/path/to/plugin1", "/path/to/plugin2"]
        finally:
            # 恢复原始配置
            if original_value is None:
                GLOBAL_CONFIG_DATA.pop("plugin_dirs", None)
            else:
                GLOBAL_CONFIG_DATA["plugin_dirs"] = original_value


class TestLoadPluginConfigs:
    """测试 _load_plugin_configs 函数"""

    @pytest.fixture(autouse=True)
    def setup(self, disable_auto_discover):
        """为所有测试禁用自动发现"""
        pass

    def test_empty_plugin_dirs(self):
        """测试空插件目录列表"""
        # 当 plugin_dirs 为空时，配置不应改变
        base_config = {"model": "test-model", "plugin_dirs": []}
        result = _load_plugin_configs(base_config)
        assert result == base_config

    def test_single_plugin_loading(self, tmp_path):
        """测试单个插件加载"""
        # 创建临时插件目录和 config.yaml
        plugin_dir = tmp_path / "plugin1"
        plugin_dir.mkdir()

        plugin_config = {"model": "plugin-model", "custom_key": "custom_value"}
        config_file = plugin_dir / "config.yaml"
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(plugin_config, f)

        # 测试加载（model/custom_key 是插件私有字段，应隔离到 plugin_configs）
        base_config = {"plugin_dirs": [str(plugin_dir)]}
        result = _load_plugin_configs(base_config)

        # 私有字段不再污染全局配置顶层，而是隔离到 plugin_configs.<plugin_name>
        assert "model" not in result
        assert "custom_key" not in result
        assert result["plugin_configs"]["plugin1"]["model"] == "plugin-model"
        assert result["plugin_configs"]["plugin1"]["custom_key"] == "custom_value"
        assert str(plugin_dir) in result["plugin_dirs"]  # plugin_dirs 保持不变

    def test_multiple_plugins_loading(self, tmp_path):
        """测试多个插件加载"""
        # 创建两个临时插件目录
        plugin_dir1 = tmp_path / "plugin1"
        plugin_dir1.mkdir()
        plugin_config1 = {"model": "plugin1-model", "key1": "value1"}
        with open(plugin_dir1 / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump(plugin_config1, f)

        plugin_dir2 = tmp_path / "plugin2"
        plugin_dir2.mkdir()
        plugin_config2 = {"model": "plugin2-model", "key2": "value2"}
        with open(plugin_dir2 / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump(plugin_config2, f)

        # 测试加载（model/key1/key2 是插件私有字段，应隔离到各自的 plugin_configs）
        base_config = {"plugin_dirs": [str(plugin_dir1), str(plugin_dir2)]}
        result = _load_plugin_configs(base_config)

        # 私有字段按插件名隔离，互不覆盖、不污染全局顶层
        assert "model" not in result
        assert "key1" not in result
        assert "key2" not in result
        assert result["plugin_configs"]["plugin1"]["model"] == "plugin1-model"
        assert result["plugin_configs"]["plugin2"]["model"] == "plugin2-model"
        assert result["plugin_configs"]["plugin1"]["key1"] == "value1"
        assert result["plugin_configs"]["plugin2"]["key2"] == "value2"

    def test_nonexistent_plugin_dir(self, tmp_path):
        """测试不存在的插件目录"""
        # 插件目录不存在时应警告但不报错
        nonexistent_dir = tmp_path / "nonexistent"
        base_config = {"model": "base-model", "plugin_dirs": [str(nonexistent_dir)]}

        # 应该不抛出异常
        result = _load_plugin_configs(base_config)

        # 配置应保持不变（除了 plugin_dirs）
        assert result["model"] == "base-model"

    def test_missing_config_yaml(self, tmp_path):
        """测试缺少 config.yaml 的插件目录"""
        # 创建插件目录但不创建 config.yaml
        plugin_dir = tmp_path / "plugin_no_config"
        plugin_dir.mkdir()

        base_config = {"model": "base-model", "plugin_dirs": [str(plugin_dir)]}
        result = _load_plugin_configs(base_config)

        # 配置应保持不变
        assert result["model"] == "base-model"

    def test_invalid_yaml_format(self, tmp_path):
        """测试无效的 YAML 文件"""
        # 创建插件目录和无效的 config.yaml
        plugin_dir = tmp_path / "plugin_invalid"
        plugin_dir.mkdir()

        config_file = plugin_dir / "config.yaml"
        with open(config_file, "w", encoding="utf-8") as f:
            f.write("invalid: yaml: content: [")  # 无效的 YAML

        base_config = {"model": "base-model", "plugin_dirs": [str(plugin_dir)]}
        result = _load_plugin_configs(base_config)

        # 配置应保持不变（加载失败）
        assert result["model"] == "base-model"

    def test_relative_path_resolution(self, tmp_path):
        """测试相对路径解析"""
        # 创建插件目录
        plugin_dir = tmp_path / "plugin_relative"
        plugin_dir.mkdir()

        plugin_config = {"custom_key": "relative_value"}
        with open(plugin_dir / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump(plugin_config, f)

        # 使用相对路径（相对于配置文件所在目录）
        # 配置文件目录为 tmp_path，相对路径为 'plugin_relative'
        base_config = {"plugin_dirs": ["plugin_relative"]}
        result = _load_plugin_configs(base_config, str(tmp_path))

        # 验证相对路径正确解析（私有字段隔离到 plugin_configs）
        assert (
            result["plugin_configs"]["plugin_relative"]["custom_key"]
            == "relative_value"
        )


class TestConfigPriority:
    """测试配置优先级"""

    @pytest.fixture(autouse=True)
    def setup(self, disable_auto_discover):
        """为所有测试禁用自动发现"""
        pass

    def test_project_config_priority_over_plugin(self, tmp_path):
        """测试项目配置不会被插件私有字段覆盖"""
        # 创建插件
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        plugin_config = {"model": "plugin-model", "plugin_only_key": "plugin_value"}
        with open(plugin_dir / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump(plugin_config, f)

        # 项目配置（base_config）
        base_config = {"model": "project-model", "plugin_dirs": [str(plugin_dir)]}
        result = _load_plugin_configs(base_config)

        # 插件私有字段隔离到 plugin_configs，不会覆盖项目配置
        assert result["model"] == "project-model"  # 项目配置保留
        assert "plugin_only_key" not in result  # 插件私有字段不进全局顶层
        assert result["plugin_configs"]["plugin"]["model"] == "plugin-model"
        assert result["plugin_configs"]["plugin"]["plugin_only_key"] == "plugin_value"

    def test_multiple_plugins_priority(self, tmp_path):
        """测试多个插件的私有字段按插件名隔离（互不覆盖）"""
        # 创建两个插件
        plugin_dir1 = tmp_path / "plugin1"
        plugin_dir1.mkdir()
        with open(plugin_dir1 / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump({"key": "value1"}, f)

        plugin_dir2 = tmp_path / "plugin2"
        plugin_dir2.mkdir()
        with open(plugin_dir2 / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump({"key": "value2"}, f)

        # 按顺序加载
        base_config = {"plugin_dirs": [str(plugin_dir1), str(plugin_dir2)]}
        result = _load_plugin_configs(base_config)

        # 同名私有字段按插件名隔离，后加载的不会覆盖前面的
        assert "key" not in result
        assert result["plugin_configs"]["plugin1"]["key"] == "value1"
        assert result["plugin_configs"]["plugin2"]["key"] == "value2"

    def test_deep_merge_nested_dict(self, tmp_path):
        """测试嵌套字典私有字段隔离（项目配置不受影响）"""
        # 创建插件
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        # 插件配置
        plugin_config = {
            "llm": {"model": "plugin-model", "plugin_only_key": "plugin_value"}
        }
        with open(plugin_dir / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump(plugin_config, f)

        # 项目配置包含嵌套字典
        base_config = {
            "llm": {"model": "project-model", "temperature": 0.7, "max_tokens": 2000},
            "plugin_dirs": [str(plugin_dir)],
        }
        result = _load_plugin_configs(base_config)

        # 插件私有 llm 字段隔离，项目配置的 llm 不受影响
        assert result["llm"] == {
            "model": "project-model",
            "temperature": 0.7,
            "max_tokens": 2000,
        }
        assert result["plugin_configs"]["plugin"]["llm"]["model"] == "plugin-model"
        assert (
            result["plugin_configs"]["plugin"]["llm"]["plugin_only_key"]
            == "plugin_value"
        )

    def test_deep_merge_multiple_levels(self, tmp_path):
        """测试多级嵌套字典私有字段隔离"""
        # 创建插件
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        plugin_config = {
            "level1": {
                "level2": {"level3_key": "plugin-value", "plugin_only": "plugin_data"}
            }
        }
        with open(plugin_dir / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump(plugin_config, f)

        # 项目配置有多级嵌套
        base_config = {
            "level1": {
                "level1_key": "project-value",
                "level2": {
                    "level2_key": "project-value",
                    "level3_key": "project-value",
                },
            },
            "plugin_dirs": [str(plugin_dir)],
        }
        result = _load_plugin_configs(base_config)

        # 插件私有 level1 隔离，项目配置的 level1 不受影响
        assert result["level1"]["level1_key"] == "project-value"
        assert result["level1"]["level2"]["level2_key"] == "project-value"
        assert result["level1"]["level2"]["level3_key"] == "project-value"
        assert "plugin_only" not in result["level1"]["level2"]
        assert (
            result["plugin_configs"]["plugin"]["level1"]["level2"]["level3_key"]
            == "plugin-value"
        )
        assert (
            result["plugin_configs"]["plugin"]["level1"]["level2"]["plugin_only"]
            == "plugin_data"
        )

    def test_deep_merge_list_append(self, tmp_path):
        """测试扩展点列表追加合并 + 私有列表隔离"""
        # 创建插件
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        plugin_config = {
            "tool_load_dirs": ["/plugin/tools"],  # 扩展点：合并进全局
            "methodology_dirs": ["/plugin/methods"],  # 私有：隔离
        }
        with open(plugin_dir / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump(plugin_config, f)

        # 项目配置包含列表
        base_config = {
            "tool_load_dirs": ["/project/tools"],
            "methodology_dirs": ["/project/methods"],
            "plugin_dirs": [str(plugin_dir)],
        }
        result = _load_plugin_configs(base_config)

        # 扩展点 tool_load_dirs 追加合并；私有 methodology_dirs 隔离
        assert result["tool_load_dirs"] == ["/project/tools", "/plugin/tools"]
        assert result["methodology_dirs"] == ["/project/methods"]  # 项目私有保留
        assert result["plugin_configs"]["plugin"]["methodology_dirs"] == [
            "/plugin/methods"
        ]

    def test_deep_mixed_types(self, tmp_path):
        """测试混合类型：扩展点合并 + 私有字段隔离"""
        # 创建插件
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        plugin_config = {
            "llm": {
                "model": "plugin-model",
                "plugin_key": "plugin_val",
            },  # 私有字典：隔离
            "tool_load_dirs": ["/plugin/tools"],  # 扩展点：追加合并
            "execute_tool_confirm": True,  # 私有标量：隔离
        }
        with open(plugin_dir / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump(plugin_config, f)

        # 项目配置
        base_config = {
            "llm": {"model": "project-model", "temperature": 0.7},
            "tool_load_dirs": ["/project/tools"],
            "execute_tool_confirm": False,
            "plugin_dirs": [str(plugin_dir)],
        }
        result = _load_plugin_configs(base_config)

        # 项目配置的 llm/execute_tool_confirm 不受插件影响
        assert result["llm"]["model"] == "project-model"
        assert result["llm"]["temperature"] == 0.7
        assert "plugin_key" not in result["llm"]
        # 扩展点 tool_load_dirs 追加合并
        assert result["tool_load_dirs"] == ["/project/tools", "/plugin/tools"]
        assert result["execute_tool_confirm"] is False
        # 插件私有字段隔离
        assert result["plugin_configs"]["plugin"]["llm"]["model"] == "plugin-model"
        assert result["plugin_configs"]["plugin"]["llm"]["plugin_key"] == "plugin_val"
        assert result["plugin_configs"]["plugin"]["execute_tool_confirm"] is True

    def test_plugin_dirs_not_list(self):
        """测试 plugin_dirs 格式错误（非列表类型）"""
        # plugin_dirs 为字符串而非列表
        base_config = {"model": "test-model", "plugin_dirs": "/invalid/path"}
        result = _load_plugin_configs(base_config)

        # 应返回原配置并输出警告
        assert result["model"] == "test-model"
        assert result["plugin_dirs"] == "/invalid/path"

    def test_plugin_dir_item_not_str(self, tmp_path):
        """测试插件目录路径格式错误（非字符串类型）"""
        # 创建有效插件
        valid_plugin_dir = tmp_path / "valid_plugin"
        valid_plugin_dir.mkdir()
        with open(valid_plugin_dir / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump({"valid_key": "valid_value"}, f)

        # plugin_dirs 包含非字符串元素（数字）
        base_config = {
            "model": "test-model",
            "plugin_dirs": [123, str(valid_plugin_dir)],  # 第一个无效，第二个有效
        }
        result = _load_plugin_configs(base_config)

        # 应跳过无效项，加载有效项
        assert result["model"] == "test-model"
        assert result["plugin_configs"]["valid_plugin"]["valid_key"] == "valid_value"

    def test_plugin_dir_template_variable(self, tmp_path):
        """测试插件配置中的 {{plugin_dir}} 模板变量"""
        # 创建临时插件目录
        plugin_dir = tmp_path / "my_plugin"
        plugin_dir.mkdir()

        # 创建包含 {{plugin_dir}} 变量的配置文件
        config_content = """model: plugin-model
tool_load_dirs:
  - {{plugin_dir}}/tools
data_path: {{plugin_dir}}/data
"""
        config_file = plugin_dir / "config.yaml"
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(config_content)

        # 测试加载
        base_config = {"plugin_dirs": [str(plugin_dir)]}
        result = _load_plugin_configs(base_config)

        # 验证模板变量已正确渲染：扩展点 tool_load_dirs 进全局，私有字段隔离
        expected_path = str(plugin_dir)
        assert result["tool_load_dirs"] == [f"{expected_path}/tools"]
        assert "model" not in result
        assert "data_path" not in result
        assert result["plugin_configs"]["my_plugin"]["model"] == "plugin-model"
        assert (
            result["plugin_configs"]["my_plugin"]["data_path"]
            == f"{expected_path}/data"
        )

    def test_plugin_dir_template_in_nested_dict(self, tmp_path):
        """测试嵌套字典中的 {{plugin_dir}} 模板变量"""
        # 创建临时插件目录
        plugin_dir = tmp_path / "nested_plugin"
        plugin_dir.mkdir()

        # 创建包含嵌套字典的配置文件
        config_content = """model: plugin-model
llm:
  model: nested-model
  cache_dir: {{plugin_dir}}/cache
  tools:
    path: {{plugin_dir}}/tools
"""
        config_file = plugin_dir / "config.yaml"
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(config_content)

        # 测试加载
        base_config = {"plugin_dirs": [str(plugin_dir)]}
        result = _load_plugin_configs(base_config)

        # 私有字段隔离到 plugin_configs，模板变量已正确渲染
        expected_path = str(plugin_dir)
        assert "llm" not in result
        assert "model" not in result
        assert (
            result["plugin_configs"]["nested_plugin"]["llm"]["cache_dir"]
            == f"{expected_path}/cache"
        )
        assert (
            result["plugin_configs"]["nested_plugin"]["llm"]["tools"]["path"]
            == f"{expected_path}/tools"
        )

    def test_plugin_dir_template_multiple_occurrences(self, tmp_path):
        """测试配置中多次使用 {{plugin_dir}} 模板变量"""
        # 创建临时插件目录
        plugin_dir = tmp_path / "multi_plugin"
        plugin_dir.mkdir()

        # 创建多次使用 {{plugin_dir}} 的配置文件
        config_content = """model: plugin-model
path1: {{plugin_dir}}/path1
path2: {{plugin_dir}}/path2
path3: {{plugin_dir}}/path3
"""
        config_file = plugin_dir / "config.yaml"
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(config_content)

        # 测试加载
        base_config = {"plugin_dirs": [str(plugin_dir)]}
        result = _load_plugin_configs(base_config)

        # 私有字段隔离到 plugin_configs，所有模板变量都已正确渲染
        expected_path = str(plugin_dir)
        assert "path1" not in result
        assert (
            result["plugin_configs"]["multi_plugin"]["path1"]
            == f"{expected_path}/path1"
        )
        assert (
            result["plugin_configs"]["multi_plugin"]["path2"]
            == f"{expected_path}/path2"
        )
        assert (
            result["plugin_configs"]["multi_plugin"]["path3"]
            == f"{expected_path}/path3"
        )


class TestInstallPlugin:
    """测试 install_plugin 函数"""

    def test_install_from_directory(self, tmp_path, monkeypatch):
        """测试从目录安装插件"""
        from jarvis.jarvis_agent.utils import install_plugin

        # 创建临时插件目录
        plugin_source = tmp_path / "my_plugin"
        plugin_source.mkdir()

        # 创建插件配置文件
        config_content = """name: test-plugin
model: plugin-model
tool_load_dirs:
  - '{{plugin_dir}}/tools'
"""
        with open(plugin_source / "config.yaml", "w", encoding="utf-8") as f:
            f.write(config_content)

        # Mock 数据目录到临时目录
        test_data_dir = tmp_path / ".jarvis"
        monkeypatch.setenv("JARVIS_DATA_DIR", str(test_data_dir))

        # 安装插件
        result = install_plugin(str(plugin_source))

        # 验证安装成功
        assert result is True
        # 插件名从 config.yaml 的 name 字段读取
        assert (test_data_dir / "plugins" / "test-plugin").exists()
        assert (test_data_dir / "plugins" / "test-plugin" / "config.yaml").exists()

    def test_install_from_zip(self, tmp_path, monkeypatch):
        """测试从 zip 文件安装插件"""
        import zipfile
        from jarvis.jarvis_agent.utils import install_plugin

        # 创建临时插件目录
        plugin_source = tmp_path / "zip_plugin"
        plugin_source.mkdir()

        config_content = "name: zip-plugin\nmodel: zip-model\n"
        with open(plugin_source / "config.yaml", "w", encoding="utf-8") as f:
            f.write(config_content)

        # 创建 zip 文件
        zip_file = tmp_path / "plugin.zip"
        with zipfile.ZipFile(zip_file, "w") as zf:
            zf.write(plugin_source / "config.yaml", "config.yaml")

        # Mock 数据目录
        test_data_dir = tmp_path / ".jarvis"
        monkeypatch.setenv("JARVIS_DATA_DIR", str(test_data_dir))

        # 安装插件
        result = install_plugin(str(zip_file))

        # 验证安装成功
        assert result is True
        assert (test_data_dir / "plugins" / "zip-plugin").exists()

    def test_install_missing_config_yaml(self, tmp_path, monkeypatch):
        """测试安装缺少 config.yaml 的插件"""
        from jarvis.jarvis_agent.utils import install_plugin

        # 创建临时插件目录（无 config.yaml）
        plugin_source = tmp_path / "invalid_plugin"
        plugin_source.mkdir()
        with open(plugin_source / "readme.txt", "w") as f:
            f.write("This is not a valid plugin")

        # Mock 数据目录
        test_data_dir = tmp_path / ".jarvis"
        monkeypatch.setenv("JARVIS_DATA_DIR", str(test_data_dir))

        # 安装插件应失败
        result = install_plugin(str(plugin_source))
        assert result is False

    def test_install_auto_install_plugin_dep_with_url(self, tmp_path, monkeypatch):
        """测试依赖插件缺失但带 url 时自动安装"""
        from jarvis.jarvis_agent import utils

        # 主插件依赖 depA（带 url + tag）
        plugin_source = tmp_path / "main_plugin"
        plugin_source.mkdir()
        config_content = """name: main-plugin
model: plugin-model
dependencies:
  plugins:
    depA:
      url: https://github.com/owner/repoA
      tag: v1.0
"""
        with open(plugin_source / "config.yaml", "w", encoding="utf-8") as f:
            f.write(config_content)

        test_data_dir = tmp_path / ".jarvis"
        monkeypatch.setenv("JARVIS_DATA_DIR", str(test_data_dir))

        calls = {}
        orig_install = utils.install_plugin

        def fake_install(src, force=False, source_url=None, _installing_deps=None):
            calls["src"] = src
            calls["source_url"] = source_url
            # 模拟依赖安装成功：创建 depA 目录
            dep_dir = test_data_dir / "plugins" / "depA"
            dep_dir.mkdir(parents=True, exist_ok=True)
            with open(dep_dir / "config.yaml", "w", encoding="utf-8") as f:
                f.write("name: depA\nversion: 1.0\n")
            return True

        monkeypatch.setattr(utils, "install_plugin", fake_install)

        result = orig_install(str(plugin_source))

        # 自动安装触发，且 URL 按 tag 解析为 archive 地址
        assert result is True
        assert calls["src"] == (
            "https://github.com/owner/repoA/archive/refs/tags/v1.0.tar.gz"
        )
        assert calls["source_url"] == calls["src"]
        assert (test_data_dir / "plugins" / "main-plugin").exists()

    def test_install_reject_plugin_dep_without_url(self, tmp_path, monkeypatch):
        """测试依赖插件缺失且无 url 时拒绝安装"""
        from jarvis.jarvis_agent import utils

        plugin_source = tmp_path / "p2"
        plugin_source.mkdir()
        config_content = """name: p2
model: plugin-model
dependencies:
  plugins:
    depB: ">=1.0"
"""
        with open(plugin_source / "config.yaml", "w", encoding="utf-8") as f:
            f.write(config_content)

        test_data_dir = tmp_path / ".jarvis"
        monkeypatch.setenv("JARVIS_DATA_DIR", str(test_data_dir))

        result = utils.install_plugin(str(plugin_source))
        assert result is False
        assert not (test_data_dir / "plugins" / "p2").exists()

    def test_install_cycle_dependency_guard(self, tmp_path, monkeypatch):
        """测试循环依赖时终止，避免死循环"""
        from jarvis.jarvis_agent import utils

        plugin_source = tmp_path / "p3"
        plugin_source.mkdir()
        config_content = """name: p3
model: plugin-model
dependencies:
  plugins:
    depC:
      url: https://github.com/c/d
"""
        with open(plugin_source / "config.yaml", "w", encoding="utf-8") as f:
            f.write(config_content)

        test_data_dir = tmp_path / ".jarvis"
        monkeypatch.setenv("JARVIS_DATA_DIR", str(test_data_dir))

        orig_install = utils.install_plugin

        def fake_install(src, force=False, source_url=None, _installing_deps=None):
            # 模拟 depC 又依赖回 p3，触发循环
            if _installing_deps is None:
                _installing_deps = set()
            _installing_deps.add("depC")
            return orig_install(str(plugin_source), _installing_deps=_installing_deps)

        monkeypatch.setattr(utils, "install_plugin", fake_install)

        result = orig_install(str(plugin_source))
        assert result is False

    def test_resolve_plugin_dep_url(self):
        """测试 _resolve_plugin_dep_url 的 URL 解析"""
        from jarvis.jarvis_agent.utils import _resolve_plugin_dep_url

        # GitHub 仓库 + tag
        assert (
            _resolve_plugin_dep_url("https://github.com/owner/repo", "v1.0", None)
            == "https://github.com/owner/repo/archive/refs/tags/v1.0.tar.gz"
        )
        # GitHub 仓库 + branch
        assert (
            _resolve_plugin_dep_url("https://github.com/owner/repo", None, "main")
            == "https://github.com/owner/repo/archive/refs/heads/main.tar.gz"
        )
        # GitHub 仓库 + .git 后缀 + tag
        assert (
            _resolve_plugin_dep_url("https://github.com/owner/repo.git", "v2", None)
            == "https://github.com/owner/repo/archive/refs/tags/v2.tar.gz"
        )
        # 无 tag/branch 原样返回
        assert (
            _resolve_plugin_dep_url("https://github.com/owner/repo", None, None)
            == "https://github.com/owner/repo"
        )
        # 非 GitHub 地址原样返回
        assert (
            _resolve_plugin_dep_url("https://example.com/x.tar.gz", "v1", None)
            == "https://example.com/x.tar.gz"
        )
        # 空 url 原样返回
        assert _resolve_plugin_dep_url("", "v1", None) == ""


class TestAutoDiscoverPlugins:
    """测试自动发现插件功能"""

    def test_auto_discover_plugins(self, tmp_path, monkeypatch):
        """测试自动发现 plugins 目录下的插件"""
        from jarvis.jarvis_utils.utils import _load_plugin_configs

        # Mock 数据目录
        test_data_dir = tmp_path / ".jarvis"
        monkeypatch.setenv("JARVIS_DATA_DIR", str(test_data_dir))

        # 创建插件目录
        plugins_dir = test_data_dir / "plugins"
        plugins_dir.mkdir(parents=True)

        plugin1 = plugins_dir / "plugin1"
        plugin1.mkdir()
        with open(plugin1 / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump({"model": "plugin1-model", "key1": "value1"}, f)

        plugin2 = plugins_dir / "plugin2"
        plugin2.mkdir()
        with open(plugin2 / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump({"model": "plugin2-model", "key2": "value2"}, f)

        # 加载配置（不指定 plugin_dirs）
        base_config = {}
        result = _load_plugin_configs(base_config)

        # 自动发现的插件已加载，私有字段隔离到各自的 plugin_configs
        assert "model" not in result
        assert "key1" not in result
        assert "key2" not in result
        assert result["plugin_configs"]["plugin1"]["model"] == "plugin1-model"
        assert result["plugin_configs"]["plugin2"]["model"] == "plugin2-model"
        assert result["plugin_configs"]["plugin1"]["key1"] == "value1"
        assert result["plugin_configs"]["plugin2"]["key2"] == "value2"

    def test_auto_discover_with_config_dirs(self, tmp_path, monkeypatch):
        """测试配置指定的插件目录和自动发现的插件目录合并"""
        from jarvis.jarvis_utils.utils import _load_plugin_configs

        # Mock 数据目录
        test_data_dir = tmp_path / ".jarvis"
        monkeypatch.setenv("JARVIS_DATA_DIR", str(test_data_dir))

        # 创建配置指定的插件
        config_plugin = tmp_path / "config_plugin"
        config_plugin.mkdir()
        with open(config_plugin / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump({"model": "config-model", "config_key": "config_value"}, f)

        # 创建自动发现的插件
        plugins_dir = test_data_dir / "plugins"
        plugins_dir.mkdir(parents=True)
        auto_plugin = plugins_dir / "auto_plugin"
        auto_plugin.mkdir()
        with open(auto_plugin / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump({"auto_key": "auto_value"}, f)

        # 加载配置（指定 plugin_dirs）
        base_config = {"plugin_dirs": [str(config_plugin)]}
        result = _load_plugin_configs(base_config)

        # 两种插件都已加载，私有字段隔离到各自的 plugin_configs
        assert "model" not in result
        assert "config_key" not in result
        assert "auto_key" not in result
        assert result["plugin_configs"]["config_plugin"]["model"] == "config-model"
        assert result["plugin_configs"]["config_plugin"]["config_key"] == "config_value"
        assert result["plugin_configs"]["auto_plugin"]["auto_key"] == "auto_value"


class TestPluginConfigIsolation:
    """测试插件私有配置隔离到单独配置项的行为"""

    @pytest.fixture(autouse=True)
    def setup(self, disable_auto_discover):
        """为所有测试禁用自动发现"""
        pass

    def test_private_configs_isolated_by_plugin_name(self, tmp_path):
        """测试两个插件声明同名私有字段时互不覆盖"""
        # 插件 A 和 B 声明同名私有 dict 字段 private_cfg
        pa = tmp_path / "pluginA"
        pa.mkdir()
        with open(pa / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump({"private_cfg": {"mode": "fast", "retries": 3}}, f)

        pb = tmp_path / "pluginB"
        pb.mkdir()
        with open(pb / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump({"private_cfg": {"mode": "slow", "level": 5}}, f)

        base_config = {"plugin_dirs": [str(pa), str(pb)]}
        result = _load_plugin_configs(base_config)

        # 同名私有字段按插件名隔离，后加载的不会覆盖前面的
        assert "private_cfg" not in result  # 不污染全局顶层
        assert result["plugin_configs"]["pluginA"]["private_cfg"] == {
            "mode": "fast",
            "retries": 3,
        }
        assert result["plugin_configs"]["pluginB"]["private_cfg"] == {
            "mode": "slow",
            "level": 5,
        }

    def test_extension_fields_still_merged(self, tmp_path):
        """测试扩展点字段仍合并进全局配置，供 getter 消费"""
        pa = tmp_path / "pluginA"
        pa.mkdir()
        with open(pa / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump({"tool_load_dirs": ["/A/tools"], "private_key": "pv"}, f)

        pb = tmp_path / "pluginB"
        pb.mkdir()
        with open(pb / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump({"rules_load_dirs": ["/B/rules"]}, f)

        base_config = {"plugin_dirs": [str(pa), str(pb)]}
        result = _load_plugin_configs(base_config)

        # 扩展点字段合并进全局
        assert result["tool_load_dirs"] == ["/A/tools"]
        assert result["rules_load_dirs"] == ["/B/rules"]
        # 私有字段隔离
        assert result["plugin_configs"]["pluginA"]["private_key"] == "pv"

    def test_get_plugin_config(self, tmp_path):
        """测试 get_plugin_config / get_all_plugin_configs getter"""
        pa = tmp_path / "pluginA"
        pa.mkdir()
        with open(pa / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump({"name": "pluginA", "custom": {"k": "v"}}, f)

        base_config = {"plugin_dirs": [str(pa)]}
        result = _load_plugin_configs(base_config)
        set_global_config_data(result)

        # get_plugin_config 返回指定插件私有配置
        assert get_plugin_config("pluginA")["custom"] == {"k": "v"}
        assert get_plugin_config("pluginA")["name"] == "pluginA"
        # 不存在的插件返回空字典
        assert get_plugin_config("nonexistent") == {}
        # get_all_plugin_configs 返回全部
        assert "pluginA" in get_all_plugin_configs()

    def test_private_configs_not_pollute_global(self, tmp_path):
        """测试插件私有字段不污染全局配置顶层"""
        pa = tmp_path / "pluginA"
        pa.mkdir()
        with open(pa / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump(
                {
                    "name": "pluginA",
                    "description": "desc",
                    "version": "1.0",
                    "builtin": False,
                    "license": "MIT",
                    "custom_field": "custom",
                },
                f,
            )

        base_config = {"plugin_dirs": [str(pa)]}
        result = _load_plugin_configs(base_config)

        # 元数据字段不污染全局顶层
        for key in (
            "name",
            "description",
            "version",
            "builtin",
            "license",
            "custom_field",
        ):
            assert key not in result, f"{key} 不应出现在全局配置顶层"
        # 全部隔离到 plugin_configs
        assert result["plugin_configs"]["pluginA"]["name"] == "pluginA"
        assert result["plugin_configs"]["pluginA"]["custom_field"] == "custom"
