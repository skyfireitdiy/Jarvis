# -*- coding: utf-8 -*-
"""jarvis_git_utils.git_commiter 模块单元测试"""

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


class TestSquashCheckpointCommits:
    """测试 GitCommitTool._squash_checkpoint_commits 压缩 CheckPoint 临时提交"""

    def _make_tool(self):
        return GitCommitTool()

    def test_squash_when_checkpoint_exists(self):
        """存在 CheckPoint 临时提交时，执行 git reset --soft 压缩到暂存区"""
        tool = self._make_tool()
        with (
            patch(
                "jarvis.jarvis_git_utils.git_commiter.find_recent_non_checkout_commit",
                return_value="abc123",
            ),
            patch(
                "jarvis.jarvis_git_utils.git_commiter.get_latest_commit_hash",
                return_value="def456",
            ),
            patch(
                "jarvis.jarvis_git_utils.git_commiter.subprocess.run"
            ) as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stderr=b"")
            tool._squash_checkpoint_commits()

        # 应执行 git reset --soft <起点>
        mock_run.assert_called_once()
        args = mock_run.call_args.args
        assert args[0] == ["git", "reset", "--soft", "abc123"]

    def test_no_squash_when_head_is_start(self):
        """无 CheckPoint（起点 == HEAD）时，不执行 reset"""
        tool = self._make_tool()
        with (
            patch(
                "jarvis.jarvis_git_utils.git_commiter.find_recent_non_checkout_commit",
                return_value="abc123",
            ),
            patch(
                "jarvis.jarvis_git_utils.git_commiter.get_latest_commit_hash",
                return_value="abc123",
            ),
            patch(
                "jarvis.jarvis_git_utils.git_commiter.subprocess.run"
            ) as mock_run,
        ):
            tool._squash_checkpoint_commits()

        mock_run.assert_not_called()

    def test_no_squash_in_fresh_repo(self):
        """全新仓库（找不到非 CheckPoint 提交）时，跳过压缩"""
        tool = self._make_tool()
        with (
            patch(
                "jarvis.jarvis_git_utils.git_commiter.find_recent_non_checkout_commit",
                return_value="",
            ),
            patch(
                "jarvis.jarvis_git_utils.git_commiter.get_latest_commit_hash",
                return_value="",
            ),
            patch(
                "jarvis.jarvis_git_utils.git_commiter.subprocess.run"
            ) as mock_run,
        ):
            tool._squash_checkpoint_commits()

        mock_run.assert_not_called()

    def test_squash_failure_does_not_raise(self):
        """压缩失败时不抛异常，仅打印警告"""
        tool = self._make_tool()
        with (
            patch(
                "jarvis.jarvis_git_utils.git_commiter.find_recent_non_checkout_commit",
                return_value="abc123",
            ),
            patch(
                "jarvis.jarvis_git_utils.git_commiter.get_latest_commit_hash",
                return_value="def456",
            ),
            patch(
                "jarvis.jarvis_git_utils.git_commiter.subprocess.run"
            ) as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=1, stderr=b"some error")
            tool._squash_checkpoint_commits()  # 不应抛异常
