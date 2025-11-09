# -*- coding: utf-8 -*-
"""jarvis_git_utils.git_commiter 模块单元测试"""

import pytest
from unittest.mock import patch, MagicMock

from jarvis.jarvis_git_utils.git_commiter import GitCommitTool
from jarvis.jarvis_utils.tag import ot, ct


class TestGitCommitTool:
    """测试 GitCommitTool 类"""

    def test_init(self):
        """测试初始化"""
        tool = GitCommitTool()
        assert tool.name == "git_commit_agent"
        assert "git" in tool.labels
        assert "version_control" in tool.labels

    def test_extract_commit_message_success(self):
        """测试成功提取提交信息"""
        tool = GitCommitTool()
        message = f"{ot('COMMIT_MESSAGE')}Test commit message{ct('COMMIT_MESSAGE')}"
        
        result = tool._extract_commit_message(message)
        assert result == "Test commit message"

    def test_extract_commit_message_with_whitespace(self):
        """测试提取带空白字符的提交信息"""
        tool = GitCommitTool()
        message = f"{ot('COMMIT_MESSAGE')}\n  Test commit\n  {ct('COMMIT_MESSAGE')}"
        
        result = tool._extract_commit_message(message)
        assert result == "Test commit"

    def test_extract_commit_message_case_insensitive(self):
        """测试大小写不敏感匹配"""
        tool = GitCommitTool()
        # 正则表达式使用 (?i) 标志，应该不区分大小写
        message = f"<commit_message>Test{ct('COMMIT_MESSAGE')}"
        
        result = tool._extract_commit_message(message)
        assert result == "Test"

    def test_extract_commit_message_not_found(self):
        """测试未找到提交信息"""
        tool = GitCommitTool()
        message = "No commit message here"
        
        result = tool._extract_commit_message(message)
        assert result is None

    def test_extract_commit_message_empty(self):
        """测试空提交信息"""
        tool = GitCommitTool()
        message = f"{ot('COMMIT_MESSAGE')}{ct('COMMIT_MESSAGE')}"
        
        result = tool._extract_commit_message(message)
        assert result == ""

    def test_extract_commit_message_special_characters(self):
        """测试包含特殊字符的提交信息"""
        tool = GitCommitTool()
        message = f"{ot('COMMIT_MESSAGE')}Fix: 修复了 #123 和 @user 的问题{ct('COMMIT_MESSAGE')}"
        
        result = tool._extract_commit_message(message)
        assert result == "Fix: 修复了 #123 和 @user 的问题"

    @patch("jarvis.jarvis_git_utils.git_commiter.subprocess.Popen")
    def test_get_last_commit_hash(self, mock_popen):
        """测试获取最后提交哈希"""
        tool = GitCommitTool()
        mock_process = MagicMock()
        mock_process.communicate.return_value = (b"abc123def456\n", b"")
        mock_popen.return_value = mock_process
        
        result = tool._get_last_commit_hash()
        assert result == "abc123def456"

    @patch("jarvis.jarvis_git_utils.git_commiter.subprocess.Popen")
    def test_get_last_commit_hash_empty(self, mock_popen):
        """测试空仓库获取提交哈希"""
        tool = GitCommitTool()
        mock_process = MagicMock()
        mock_process.communicate.return_value = (b"", b"fatal: your current branch")
        mock_popen.return_value = mock_process
        
        result = tool._get_last_commit_hash()
        assert result == ""

