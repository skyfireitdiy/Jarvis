# -*- coding: utf-8 -*-
"""utils.py 单元测试"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from jarvis.jarvis_code_agent.utils import (
    get_git_tracked_files_info,
    get_project_overview,
)


class TestGetGitTrackedFilesInfo:
    """测试 get_git_tracked_files_info 函数"""

    @patch("jarvis.jarvis_code_agent.utils.subprocess.run")
    def test_get_git_tracked_files_info_with_few_files(self, mock_run):
        """测试文件数量少于阈值时返回文件列表"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "file1.py\nfile2.py\nfile3.js\n"
        mock_run.return_value = mock_result

        result = get_git_tracked_files_info("/tmp/test", max_files=100)

        assert result is not None
        assert "Git托管文件列表" in result
        assert "共3个文件" in result
        assert "file1.py" in result
        assert "file2.py" in result
        assert "file3.js" in result

    @patch("jarvis.jarvis_code_agent.utils.subprocess.run")
    def test_get_git_tracked_files_info_with_many_files(self, mock_run):
        """测试文件数量超过阈值时返回目录结构"""
        # 创建超过阈值的文件列表
        files = [f"src/file{i}.py" for i in range(150)]
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "\n".join(files) + "\n"
        mock_run.return_value = mock_result

        result = get_git_tracked_files_info("/tmp/test", max_files=100)

        assert result is not None
        assert "Git托管目录结构" in result
        assert "共150个文件" in result
        assert "src/" in result
        # 应该包含目录树结构
        assert "├──" in result or "└──" in result

    @patch("jarvis.jarvis_code_agent.utils.subprocess.run")
    def test_get_git_tracked_files_info_empty_output(self, mock_run):
        """测试 git ls-files 返回空输出"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        result = get_git_tracked_files_info("/tmp/test")

        assert result is None

    @patch("jarvis.jarvis_code_agent.utils.subprocess.run")
    def test_get_git_tracked_files_info_git_error(self, mock_run):
        """测试 git 命令失败的情况"""
        mock_run.side_effect = Exception("git not found")

        result = get_git_tracked_files_info("/tmp/test")

        assert result is None

    @patch("jarvis.jarvis_code_agent.utils.subprocess.run")
    def test_get_git_tracked_files_info_non_zero_returncode(self, mock_run):
        """测试 git 命令返回非零退出码"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        result = get_git_tracked_files_info("/tmp/test")

        assert result is None

    @patch("jarvis.jarvis_code_agent.utils.subprocess.run")
    def test_get_git_tracked_files_info_with_whitespace(self, mock_run):
        """测试处理包含空白行的输出"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "file1.py\n\nfile2.py\n  \nfile3.js\n"
        mock_run.return_value = mock_result

        result = get_git_tracked_files_info("/tmp/test")

        assert result is not None
        assert "file1.py" in result
        assert "file2.py" in result
        assert "file3.js" in result

    @patch("jarvis.jarvis_code_agent.utils.subprocess.run")
    def test_get_git_tracked_files_info_directory_structure(self, mock_run):
        """测试目录结构的正确性"""
        files = [
            "src/main.py",
            "src/utils.py",
            "tests/test_main.py",
            "README.md",
        ]
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "\n".join(files) + "\n"
        mock_run.return_value = mock_result

        result = get_git_tracked_files_info("/tmp/test", max_files=100)

        assert result is not None
        # 验证目录结构包含 src 和 tests
        assert "src/" in result or "src" in result
        assert "tests/" in result or "tests" in result


class TestGetProjectOverview:
    """测试 get_project_overview 函数"""

    @patch("jarvis.jarvis_code_agent.utils.get_recent_commits_with_files")
    @patch("jarvis.jarvis_code_agent.utils.get_git_tracked_files_info")
    @patch("jarvis.jarvis_code_agent.utils.get_loc_stats")
    def test_get_project_overview_with_all_info(
        self, mock_loc_stats, mock_git_files, mock_commits
    ):
        """测试获取完整的项目概况"""
        mock_loc_stats.return_value = "Python: 1000 lines"
        mock_git_files.return_value = "Git托管文件列表（共10个文件）:\n  - file1.py"
        mock_commits.return_value = [
            {
                "hash": "abc1234",
                "message": "Test commit",
                "files": ["file1.py", "file2.py"],
            }
        ]

        result = get_project_overview("/tmp/test")

        assert result is not None
        assert "项目概况" in result
        assert "代码统计" in result
        assert "Git托管文件列表" in result
        assert "最近提交" in result

    @patch("jarvis.jarvis_code_agent.utils.get_recent_commits_with_files")
    @patch("jarvis.jarvis_code_agent.utils.get_git_tracked_files_info")
    @patch("jarvis.jarvis_code_agent.utils.get_loc_stats")
    def test_get_project_overview_no_info(
        self, mock_loc_stats, mock_git_files, mock_commits
    ):
        """测试没有任何信息时返回空字符串"""
        mock_loc_stats.return_value = None
        mock_git_files.return_value = None
        mock_commits.return_value = []

        result = get_project_overview("/tmp/test")

        assert result == ""

    @patch("jarvis.jarvis_code_agent.utils.get_recent_commits_with_files")
    @patch("jarvis.jarvis_code_agent.utils.get_git_tracked_files_info")
    @patch("jarvis.jarvis_code_agent.utils.get_loc_stats")
    def test_get_project_overview_partial_info(
        self, mock_loc_stats, mock_git_files, mock_commits
    ):
        """测试只有部分信息的情况"""
        mock_loc_stats.return_value = "Python: 1000 lines"
        mock_git_files.return_value = None
        mock_commits.return_value = []

        result = get_project_overview("/tmp/test")

        assert result is not None
        assert "代码统计" in result
        assert "Git托管文件列表" not in result
        assert "最近提交" not in result

    @patch("jarvis.jarvis_code_agent.utils.get_recent_commits_with_files")
    @patch("jarvis.jarvis_code_agent.utils.get_git_tracked_files_info")
    @patch("jarvis.jarvis_code_agent.utils.get_loc_stats")
    def test_get_project_overview_with_many_commit_files(
        self, mock_loc_stats, mock_git_files, mock_commits
    ):
        """测试提交包含多个文件时的截断"""
        mock_loc_stats.return_value = None
        mock_git_files.return_value = None
        mock_commits.return_value = [
            {
                "hash": "abc1234",
                "message": "Test commit",
                "files": [f"file{i}.py" for i in range(10)],
            }
        ]

        result = get_project_overview("/tmp/test")

        assert result is not None
        assert "最近提交" in result
        # 应该只显示前5个文件
        assert "file0.py" in result
        assert "file4.py" in result
        assert "..." in result  # 应该有省略标记

    @patch("jarvis.jarvis_code_agent.utils.get_recent_commits_with_files")
    @patch("jarvis.jarvis_code_agent.utils.get_git_tracked_files_info")
    @patch("jarvis.jarvis_code_agent.utils.get_loc_stats")
    def test_get_project_overview_exception_handling(
        self, mock_loc_stats, mock_git_files, mock_commits
    ):
        """测试异常处理"""
        mock_loc_stats.side_effect = Exception("Error")
        mock_git_files.side_effect = Exception("Error")
        mock_commits.side_effect = Exception("Error")

        result = get_project_overview("/tmp/test")

        # 应该返回空字符串而不是抛出异常
        assert result == ""

    @patch("jarvis.jarvis_code_agent.utils.get_recent_commits_with_files")
    @patch("jarvis.jarvis_code_agent.utils.get_git_tracked_files_info")
    @patch("jarvis.jarvis_code_agent.utils.get_loc_stats")
    def test_get_project_overview_multiple_commits(
        self, mock_loc_stats, mock_git_files, mock_commits
    ):
        """测试多个提交的情况"""
        mock_loc_stats.return_value = None
        mock_git_files.return_value = None
        mock_commits.return_value = [
            {
                "hash": "abc1234",
                "message": "First commit",
                "files": ["file1.py"],
            },
            {
                "hash": "def5678",
                "message": "Second commit",
                "files": ["file2.py"],
            },
        ]

        result = get_project_overview("/tmp/test")

        assert result is not None
        assert "提交 1" in result
        assert "提交 2" in result
        assert "First commit" in result
        assert "Second commit" in result
