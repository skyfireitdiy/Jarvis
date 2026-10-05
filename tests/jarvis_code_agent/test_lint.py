# -*- coding: utf-8 -*-
"""lint.py 单元测试"""

from unittest.mock import patch

from jarvis.jarvis_utils.collections import CaseInsensitiveDict
from jarvis.jarvis_utils.config import get_lint_tools_config
from jarvis.jarvis_code_agent.lint import (
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
        assert any("ty check" in t for t in py_templates)

        assert ".js" in LINT_COMMAND_TEMPLATES_BY_FILE
        js_templates = LINT_COMMAND_TEMPLATES_BY_FILE[".js"]
        assert any("eslint" in t for t in js_templates)

        assert ".go" in LINT_COMMAND_TEMPLATES_BY_FILE
        go_templates = LINT_COMMAND_TEMPLATES_BY_FILE[".go"]
        assert any("go vet" in t for t in go_templates)

        assert "dockerfile" in LINT_COMMAND_TEMPLATES_BY_FILE
        dockerfile_templates = LINT_COMMAND_TEMPLATES_BY_FILE["dockerfile"]
        assert any("hadolint" in t for t in dockerfile_templates)

    @patch("jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA")
    def test_get_lint_tools_config_with_config(self, mock_config):
        """测试从GLOBAL_CONFIG_DATA加载配置"""
        mock_config.get.side_effect = lambda key, default=None: {
            "lint_tools": {
                ".custom": ["custom-linter {file_path}"],
                ".PY": ["additional-python-linter {file_path}"],  # 测试大写转小写
                ".new": ["new-linter1 {file_path}", "new-linter2 {file_path}"],
            }
        }.get(key, default)

        result = get_lint_tools_config()

        # 验证结果
        assert result[".custom"] == ["custom-linter {file_path}"]
        assert result[".py"] == ["additional-python-linter {file_path}"]  # 应该转为小写
        assert result[".new"] == ["new-linter1 {file_path}", "new-linter2 {file_path}"]
        assert ".PY" not in result  # 大写版本不应存在

    @patch("jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA", CaseInsensitiveDict())
    def test_get_lint_tools_config_no_config(self):
        """测试未配置的情况"""
        result = get_lint_tools_config()
        assert result == {}

    @patch("jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA")
    def test_get_lint_tools_config_empty_config(self, mock_config):
        """测试配置为空的情况"""
        mock_config.get.return_value = None
        result = get_lint_tools_config()
        assert result == {}

    def test_get_lint_commands_by_extension(self):
        """测试通过文件扩展名获取lint命令"""
        # Python文件
        cmds = get_lint_commands_for_files(["test.py"], None)
        assert len(cmds) >= 2  # ruff 和 ty
        cmd_strs = [cmd for _, cmd in cmds]
        assert any("ruff check" in cmd for cmd in cmd_strs)
        assert any("ty check" in cmd for cmd in cmd_strs)

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

    @patch("jarvis.jarvis_code_agent.lint.get_lint_tools_config")
    def test_config_merge(self, mock_get_config):
        """测试配置合并功能（从 config.yaml 读取）"""
        # 模拟 config.yaml 中配置的 lint_tools
        mock_get_config.return_value = {
            ".py": ["additional-linter {file_path}"],  # 覆盖现有配置
            ".custom": ["custom-linter {file_path}"],  # 新增配置
        }

        # .py 文件：.py 被覆盖，只生成 additional-linter
        cmds = get_lint_commands_for_files(["test.py"], None)
        cmd_strs = [cmd for _, cmd in cmds]
        assert any("additional-linter" in cmd for cmd in cmd_strs)
        assert not any("ruff check" in cmd for cmd in cmd_strs)  # 被覆盖

        # .custom 文件：新增配置生效
        cmds = get_lint_commands_for_files(["app.custom"], None)
        cmd_strs = [cmd for _, cmd in cmds]
        assert any("custom-linter" in cmd for cmd in cmd_strs)

        # .js 文件：未配置，保持内置默认
        cmds = get_lint_commands_for_files(["app.js"], None)
        cmd_strs = [cmd for _, cmd in cmds]
        assert any("eslint" in cmd for cmd in cmd_strs)
