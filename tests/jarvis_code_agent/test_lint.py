# -*- coding: utf-8 -*-
"""lint.py 单元测试"""

from unittest.mock import patch, mock_open

from jarvis.jarvis_code_agent.lint import (
    load_lint_tools_config,
    get_lint_commands_for_files,
    LINT_COMMAND_TEMPLATES_BY_FILE,
)


class TestLintTools:
    """lint工具相关功能的测试"""

    def test_lint_tools_default_config(self):
        """测试默认的lint工具配置"""
        # 验证一些常见文件类型的配置
        assert ".py" in LINT_COMMAND_TEMPLATES_BY_FILE
        py_templates = LINT_COMMAND_TEMPLATES_BY_FILE[".py"]
        assert any("ruff check" in t for t in py_templates)
        assert any("mypy" in t for t in py_templates)

        assert ".js" in LINT_COMMAND_TEMPLATES_BY_FILE
        js_templates = LINT_COMMAND_TEMPLATES_BY_FILE[".js"]
        assert any("eslint" in t for t in js_templates)

        assert ".go" in LINT_COMMAND_TEMPLATES_BY_FILE
        go_templates = LINT_COMMAND_TEMPLATES_BY_FILE[".go"]
        assert any("go vet" in t for t in go_templates)

        assert "dockerfile" in LINT_COMMAND_TEMPLATES_BY_FILE
        dockerfile_templates = LINT_COMMAND_TEMPLATES_BY_FILE["dockerfile"]
        assert any("hadolint" in t for t in dockerfile_templates)

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    def test_load_lint_tools_config_with_file(
        self, mock_yaml_load, mock_file, mock_exists
    ):
        """测试从yaml文件加载配置"""
        mock_exists.return_value = True
        mock_yaml_load.return_value = {
            ".custom": ["custom-linter {file_path}"],
            ".PY": ["additional-python-linter {file_path}"],  # 测试大写转小写
            ".new": ["new-linter1 {file_path}", "new-linter2 {file_path}"],
        }

        result = load_lint_tools_config()

        # 验证结果
        assert result[".custom"] == ["custom-linter {file_path}"]
        assert result[".py"] == ["additional-python-linter {file_path}"]  # 应该转为小写
        assert result[".new"] == ["new-linter1 {file_path}", "new-linter2 {file_path}"]
        assert ".PY" not in result  # 大写版本不应存在

    @patch("os.path.exists")
    def test_load_lint_tools_config_no_file(self, mock_exists):
        """测试配置文件不存在的情况"""
        mock_exists.return_value = False

        result = load_lint_tools_config()

        assert result == {}

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    def test_load_lint_tools_config_empty_file(
        self, mock_yaml_load, mock_file, mock_exists
    ):
        """测试空配置文件的情况"""
        mock_exists.return_value = True
        mock_yaml_load.return_value = None

        result = load_lint_tools_config()

        assert result == {}

    def test_get_lint_commands_by_extension(self):
        """测试通过文件扩展名获取lint命令"""
        # Python文件
        cmds = get_lint_commands_for_files(["test.py"], None)
        assert len(cmds) >= 2  # ruff 和 mypy
        cmd_strs = [cmd for _, cmd in cmds]
        assert any("ruff check" in cmd for cmd in cmd_strs)
        assert any("mypy" in cmd for cmd in cmd_strs)

        # JavaScript文件
        cmds = get_lint_commands_for_files(["app.js"], None)
        assert len(cmds) >= 1
        assert any("eslint" in cmd for _, cmd in cmds)

        # Go文件
        cmds = get_lint_commands_for_files(["main.go"], None)
        assert len(cmds) >= 1
        assert any("go vet" in cmd for _, cmd in cmds)

        # 未知扩展名
        cmds = get_lint_commands_for_files(["unknown.xyz"], None)
        assert len(cmds) == 0

    def test_get_lint_commands_with_path(self):
        """测试带路径的文件名"""
        # 应该只使用基础文件名进行匹配
        cmds = get_lint_commands_for_files(["/home/user/project/test.py"], None)
        assert len(cmds) >= 2
        assert any("test.py" in file_path for file_path, _ in cmds)

        cmds = get_lint_commands_for_files(["../src/main.go"], None)
        assert len(cmds) >= 1
        assert any("go vet" in cmd for _, cmd in cmds)

        cmds = get_lint_commands_for_files(["/var/lib/docker/dockerfile"], None)
        assert len(cmds) >= 1
        assert any("hadolint" in cmd for _, cmd in cmds)

    def test_get_lint_commands_special_cases(self):
        """测试特殊情况"""
        # 没有扩展名的文件
        cmds = get_lint_commands_for_files(["README"], None)
        assert len(cmds) == 0

        # 多个点的文件名
        cmds = get_lint_commands_for_files(["test.spec.js"], None)
        assert len(cmds) >= 1
        assert any("eslint" in cmd for _, cmd in cmds)

        cmds = get_lint_commands_for_files(["app.test.py"], None)
        assert len(cmds) >= 2

        # 隐藏文件
        cmds = get_lint_commands_for_files([".bashrc"], None)
        assert len(cmds) >= 1
        assert any("shellcheck" in cmd for _, cmd in cmds)

        cmds = get_lint_commands_for_files([".gitignore"], None)
        assert len(cmds) >= 1
        assert any("git-lint" in cmd for _, cmd in cmds)

    @patch("jarvis.jarvis_code_agent.lint.get_data_dir")
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    def test_config_merge(
        self, mock_yaml_load, mock_file, mock_exists, mock_get_data_dir
    ):
        """测试配置合并功能"""
        # 设置mock返回值
        mock_get_data_dir.return_value = "/mock/data/dir"
        mock_exists.return_value = True
        mock_yaml_load.return_value = {
            ".py": ["additional-linter {file_path}"],  # 应该更新现有配置
            ".custom": ["custom-linter {file_path}"],  # 应该添加新配置
        }

        # 测试load_lint_tools_config的返回值
        config = load_lint_tools_config()

        # 验证配置加载正确
        assert config[".py"] == ["additional-linter {file_path}"]
        assert config[".custom"] == ["custom-linter {file_path}"]

        # 创建一个新的配置字典来模拟合并后的效果
        test_config = LINT_COMMAND_TEMPLATES_BY_FILE.copy()
        test_config.update(config)

        # 验证合并后的效果
        assert test_config[".py"] == ["additional-linter {file_path}"]  # 被覆盖
        assert test_config[".custom"] == ["custom-linter {file_path}"]  # 新增
        assert ".js" in test_config  # 保持不变
        assert any("eslint" in t for t in test_config[".js"])
