# -*- coding: utf-8 -*-
"""jarvis_code_agent.code_agent_git 模块单元测试

覆盖 Issue #238：<Commit> 提交时，工作区中未暂存/未提交的变更（含未跟踪文件）
应一并纳入提交，即使没有产生任何 CheckPoint 临时提交（commits 为空）。
"""
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from jarvis.jarvis_code_agent.code_agent_git import GitManager


class TestHandleCommitConfirmation:
    """测试 GitManager.handle_commit_confirmation 的提交条件"""

    def _make_manager(self):
        return GitManager("/tmp")

    def _setup(
        self,
        has_changes,
        diff_files=None,
        commit_result=None,
        start_commit="abc123",
    ):
        """构造 GitManager 并 patch 所有依赖，返回 (manager, mocks)"""
        stack = ExitStack()
        mocks = {}

        mocks["has_changes"] = stack.enter_context(
            patch(
                "jarvis.jarvis_code_agent.code_agent_git.has_uncommitted_changes",
                return_value=has_changes,
            )
        )
        mocks["run"] = stack.enter_context(
            patch("jarvis.jarvis_code_agent.code_agent_git.subprocess.run")
        )
        mocks["diff_list"] = stack.enter_context(
            patch(
                "jarvis.jarvis_utils.git_utils.get_diff_file_list",
                return_value=diff_files or [],
            )
        )
        mocks["latest_hash"] = stack.enter_context(
            patch(
                "jarvis.jarvis_utils.git_utils.get_latest_commit_hash",
                return_value="newhash123",
            )
        )
        mock_commiter = MagicMock()
        mock_commiter.execute.return_value = commit_result or {
            "success": True,
            "stdout": "committed",
            "stderr": "",
        }
        stack.enter_context(
            patch(
                "jarvis.jarvis_code_agent.code_agent_git.GitCommitTool",
                return_value=mock_commiter,
            )
        )
        mocks["commiter"] = mock_commiter

        manager = self._make_manager()
        agent = MagicMock()
        post_process_func = MagicMock()
        return stack, manager, agent, post_process_func, mocks

    def _reset_calls(self, mock_run):
        return [
            c
            for c in mock_run.call_args_list
            if c.args and c.args[0] == ["git", "reset", "--mixed", "abc123"]
        ]

    def test_commits_empty_but_worktree_changes_commits(self):
        """Issue #238：commits 为空但工作区有未提交变更时，应执行提交"""
        stack, manager, agent, post_process_func, mocks = self._setup(
            has_changes=True, diff_files=["file1.py"]
        )
        with stack:
            manager.handle_commit_confirmation(
                commits=[],
                start_commit="abc123",
                prefix="",
                suffix="",
                agent=agent,
                post_process_func=post_process_func,
                skip_confirm=True,
            )

        # 提交条件触发：调用了 has_uncommitted_changes 判断
        mocks["has_changes"].assert_called_once()
        # 执行了 git reset --mixed start_commit
        assert self._reset_calls(mocks["run"]), (
            "commits 为空但有工作区变更时也应执行 git reset --mixed"
        )
        # GitCommitTool 被调用提交
        mocks["commiter"].execute.assert_called_once()
        # 变更文件被后处理
        post_process_func.assert_called_once_with(["file1.py"])
        # start_commit 更新为最新 hash
        assert agent.start_commit == "newhash123"

    def test_commits_empty_and_no_changes_skips(self):
        """commits 为空且工作区无变更时，不执行提交"""
        stack, manager, agent, post_process_func, mocks = self._setup(
            has_changes=False
        )
        with stack:
            manager.handle_commit_confirmation(
                commits=[],
                start_commit="abc123",
                prefix="",
                suffix="",
                agent=agent,
                post_process_func=post_process_func,
                skip_confirm=True,
            )

        mocks["has_changes"].assert_called_once()
        # 不应执行 git reset --mixed
        assert not self._reset_calls(mocks["run"]), (
            "工作区无变更时不应执行 git reset --mixed"
        )
        # GitCommitTool 不应被调用
        mocks["commiter"].execute.assert_not_called()
        post_process_func.assert_not_called()

    def test_commits_non_empty_still_commits(self):
        """commits 非空时行为不变：仍执行提交（回归保护）"""
        stack, manager, agent, post_process_func, mocks = self._setup(
            has_changes=False
        )
        with stack:
            manager.handle_commit_confirmation(
                commits=[("abc123", "CheckPoint #1")],
                start_commit="abc123",
                prefix="",
                suffix="",
                agent=agent,
                post_process_func=post_process_func,
                skip_confirm=True,
            )

        # commits 非空时短路，不应调用 has_uncommitted_changes
        mocks["has_changes"].assert_not_called()
        # 执行了 git reset --mixed
        assert self._reset_calls(mocks["run"])
        mocks["commiter"].execute.assert_called_once()
        assert agent.start_commit == "newhash123"

    def test_start_commit_none_skips_reset(self):
        """start_commit 为空时跳过 git reset --mixed（防御空仓库场景）"""
        stack, manager, agent, post_process_func, mocks = self._setup(
            has_changes=True
        )
        with stack:
            manager.handle_commit_confirmation(
                commits=[],
                start_commit=None,
                prefix="",
                suffix="",
                agent=agent,
                post_process_func=post_process_func,
                skip_confirm=True,
            )

        mocks["has_changes"].assert_called_once()
        # 不应执行 git reset --mixed（start_commit 为 None）
        assert not self._reset_calls(mocks["run"])
        # 仍应执行提交
        mocks["commiter"].execute.assert_called_once()
        assert agent.start_commit == "newhash123"
