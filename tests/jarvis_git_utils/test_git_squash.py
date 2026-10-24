# -*- coding: utf-8 -*-
"""jarvis_git_squash.main 模块单元测试（-g/--llm-group 模型组参数）"""

from unittest.mock import patch

from typer.testing import CliRunner

from jarvis.jarvis_git_squash.main import GitSquashTool
from jarvis.jarvis_git_squash.main import app

runner = CliRunner()


class TestCliLlmGroup:
    """测试 cli() 的 -g/--llm-group 参数"""

    def test_help_shows_llm_group_option(self):
        """jgs --help 显示 -g/--llm-group 选项及说明"""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "-g" in result.stdout
        assert "--llm-group" in result.stdout
        assert "使用的模型组" in result.stdout

    def test_cli_passes_llm_group_to_init_env(self):
        """指定 -g 时 init_env 收到对应模型组"""
        with (
            patch(
                "jarvis.jarvis_git_squash.main.init_env"
            ) as mock_init_env,
            patch.object(GitSquashTool, "execute") as mock_execute,
        ):
            result = runner.invoke(app, ["-g", "test-group", "abc123"])
            assert result.exit_code == 0
        mock_init_env.assert_called_once_with(llm_group="test-group")
        mock_execute.assert_called_once()

    def test_cli_passes_long_option_to_init_env(self):
        """指定 --llm-group 时 init_env 收到对应模型组"""
        with (
            patch(
                "jarvis.jarvis_git_squash.main.init_env"
            ) as mock_init_env,
            patch.object(GitSquashTool, "execute") as mock_execute,
        ):
            result = runner.invoke(app, ["--llm-group", "test-group", "abc123"])
            assert result.exit_code == 0
        mock_init_env.assert_called_once_with(llm_group="test-group")
        mock_execute.assert_called_once()

    def test_cli_passes_llm_group_to_execute(self):
        """指定 -g 时 llm_group 透传到 execute 的 args"""
        with (
            patch("jarvis.jarvis_git_squash.main.init_env"),
            patch.object(GitSquashTool, "execute") as mock_execute,
        ):
            result = runner.invoke(app, ["-g", "test-group", "abc123"])
            assert result.exit_code == 0
        mock_execute.assert_called_once_with(
            {"commit_hash": "abc123", "lang": "Chinese", "llm_group": "test-group"}
        )

    def test_cli_without_llm_group_passes_none(self):
        """不带 -g 时 init_env 收到 llm_group=None"""
        with (
            patch(
                "jarvis.jarvis_git_squash.main.init_env"
            ) as mock_init_env,
            patch.object(GitSquashTool, "execute") as mock_execute,
        ):
            result = runner.invoke(app, ["abc123"])
            assert result.exit_code == 0
        mock_init_env.assert_called_once_with(llm_group=None)
        mock_execute.assert_called_once()

    def test_cli_lang_and_llm_group_coexist(self):
        """--lang 与 -g 可同时使用，互不干扰"""
        with (
            patch("jarvis.jarvis_git_squash.main.init_env"),
            patch.object(GitSquashTool, "execute") as mock_execute,
        ):
            result = runner.invoke(
                app, ["--lang", "English", "-g", "test-group", "abc123"]
            )
            assert result.exit_code == 0
        mock_execute.assert_called_once_with(
            {"commit_hash": "abc123", "lang": "English", "llm_group": "test-group"}
        )


class TestGitSquashTool:
    """测试 GitSquashTool 类"""

    def test_init(self):
        """测试初始化"""
        tool = GitSquashTool()
        assert tool.name == "git_squash_agent"
        assert "git" in tool.labels
        assert "squash" in tool.labels

    def test_execute_keeps_existing_exec_args_structure(self):
        """execute() 内部调用 GitCommitTool 时 exec_args 保持 lang+agent 结构，不新增 llm_group"""
        tool = GitSquashTool()
        with (
            patch.object(tool, "_confirm_squash", return_value=True),
            patch.object(tool, "_reset_to_commit", return_value=True),
            patch(
                "jarvis.jarvis_git_squash.main.GitCommitTool"
            ) as MockCommitTool,
            patch(
                "jarvis.jarvis_git_squash.main.get_agent", return_value=None
            ),
        ):
            tool.execute({"commit_hash": "abc123", "lang": "Chinese", "llm_group": "g"})

        mock_commit_tool = MockCommitTool.return_value
        mock_commit_tool.execute.assert_called_once_with({"lang": "Chinese"})
