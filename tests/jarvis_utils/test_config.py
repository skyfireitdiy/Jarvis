# -*- coding: utf-8 -*-
"""jarvis_utils.config 模块插件功能单元测试"""

import yaml

from jarvis.jarvis_utils.config import get_plugin_dirs, GLOBAL_CONFIG_DATA
from jarvis.jarvis_utils.utils import _load_plugin_configs


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

        # 测试加载（项目配置无 model，应使用插件配置）
        base_config = {"plugin_dirs": [str(plugin_dir)]}
        result = _load_plugin_configs(base_config)

        # 验证配置合并：项目配置无 model，使用插件配置
        assert result["model"] == "plugin-model"  # 插件配置生效
        assert result["custom_key"] == "custom_value"  # 插件新增配置
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

        # 测试加载（项目配置无 model，应使用最后一个插件的配置）
        base_config = {"plugin_dirs": [str(plugin_dir1), str(plugin_dir2)]}
        result = _load_plugin_configs(base_config)

        # 验证配置合并（后加载的插件覆盖前面的）
        assert result["model"] == "plugin2-model"  # plugin2 覆盖 plugin1
        assert result["key1"] == "value1"  # plugin1 的配置
        assert result["key2"] == "value2"  # plugin2 的配置

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

        # 验证相对路径正确解析
        assert result["custom_key"] == "relative_value"


class TestConfigPriority:
    """测试配置优先级"""

    def test_project_config_priority_over_plugin(self, tmp_path):
        """测试项目配置优先级高于插件配置"""
        # 创建插件
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        plugin_config = {"model": "plugin-model", "plugin_only_key": "plugin_value"}
        with open(plugin_dir / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump(plugin_config, f)

        # 项目配置（base_config）
        base_config = {"model": "project-model", "plugin_dirs": [str(plugin_dir)]}
        result = _load_plugin_configs(base_config)

        # 项目配置应优先于插件配置
        assert result["model"] == "project-model"  # 项目配置覆盖插件配置
        assert result["plugin_only_key"] == "plugin_value"  # 插件独有配置保留

    def test_multiple_plugins_priority(self, tmp_path):
        """测试多个插件的优先级（后加载的覆盖前面的）"""
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

        # 后加载的插件应覆盖前面的
        assert result["key"] == "value2"

    def test_deep_merge_nested_dict(self, tmp_path):
        """测试深度合并嵌套字典（项目配置优先）"""
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

        # 验证深度合并：项目配置优先，但保留插件独有配置
        assert result["llm"]["model"] == "project-model"  # 项目配置覆盖插件配置
        assert result["llm"]["temperature"] == 0.7  # 项目配置保留
        assert result["llm"]["max_tokens"] == 2000  # 项目配置保留
        assert result["llm"]["plugin_only_key"] == "plugin_value"  # 插件独有配置保留

    def test_deep_merge_multiple_levels(self, tmp_path):
        """测试多级嵌套字典的深度合并（项目配置优先）"""
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

        # 验证多级深度合并：项目配置优先
        assert result["level1"]["level1_key"] == "project-value"  # 项目配置保留
        assert (
            result["level1"]["level2"]["level2_key"] == "project-value"
        )  # 项目配置保留
        assert (
            result["level1"]["level2"]["level3_key"] == "project-value"
        )  # 项目配置覆盖插件配置
        assert (
            result["level1"]["level2"]["plugin_only"] == "plugin_data"
        )  # 插件独有配置保留

    def test_deep_merge_list_append(self, tmp_path):
        """测试列表追加合并"""
        # 创建插件
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        plugin_config = {
            "tool_load_dirs": ["/plugin/tools"],
            "methodology_dirs": ["/plugin/methods"],
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

        # 验证列表追加：项目列表 + 插件列表
        assert result["tool_load_dirs"] == ["/project/tools", "/plugin/tools"]
        assert result["methodology_dirs"] == ["/project/methods", "/plugin/methods"]

    def test_deep_mixed_types(self, tmp_path):
        """测试混合类型合并（项目配置优先）"""
        # 创建插件
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        plugin_config = {
            "llm": {
                "model": "plugin-model",
                "plugin_key": "plugin_val",
            },  # 字典：深度合并
            "tool_load_dirs": ["/plugin/tools"],  # 列表：追加
            "execute_tool_confirm": True,  # 基本类型：项目配置覆盖
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

        # 验证混合类型合并：项目配置优先
        assert result["llm"]["model"] == "project-model"  # 项目配置覆盖插件配置
        assert result["llm"]["temperature"] == 0.7  # 项目配置保留
        assert result["llm"]["plugin_key"] == "plugin_val"  # 插件独有配置保留
        assert result["tool_load_dirs"] == [
            "/project/tools",
            "/plugin/tools",
        ]  # 列表：追加
        assert result["execute_tool_confirm"] is False  # 项目配置覆盖插件配置

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
        assert result["valid_key"] == "valid_value"  # 有效插件配置已加载

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

        # 验证模板变量已正确渲染
        expected_path = str(plugin_dir)
        assert result["model"] == "plugin-model"
        assert result["tool_load_dirs"] == [f"{expected_path}/tools"]
        assert result["data_path"] == f"{expected_path}/data"

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

        # 验证嵌套字典中的模板变量已正确渲染
        expected_path = str(plugin_dir)
        assert result["llm"]["cache_dir"] == f"{expected_path}/cache"
        assert result["llm"]["tools"]["path"] == f"{expected_path}/tools"

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

        # 验证所有模板变量都已正确渲染
        expected_path = str(plugin_dir)
        assert result["path1"] == f"{expected_path}/path1"
        assert result["path2"] == f"{expected_path}/path2"
        assert result["path3"] == f"{expected_path}/path3"
