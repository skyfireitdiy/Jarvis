# -*- coding: utf-8 -*-
"""jarvis_tools.commit / review 工具的 working_dir 参数单元测试。

验证：
1. CommitTool/ReviewTool 的 parameters 暴露 working_dir 参数描述；
2. 指定 working_dir 时在目标目录执行，结束后无论成功/失败都恢复原目录；
3. ReviewTool 审查通过联动 commit 时透传 working_dir。
"""

import os
from typing import cast

from jarvis.jarvis_tools.commit import CommitTool
from jarvis.jarvis_tools.review import ReviewTool


class _FakeAgent:
    """最小可用的 agent 替身：非交互、未禁用审查。"""

    non_interactive = True
    disable_review = False
    model = None
    start_commit = None
    quick_mode = False


class TestWorkingDirParameter:
    """验证 parameters 暴露 working_dir 参数描述。"""

    def _props(self) -> dict:
        return cast(dict, CommitTool.parameters["properties"])

    def test_commit_tool_parameters_contains_working_dir(self):
        props = self._props()
        assert "working_dir" in props
        assert props["working_dir"]["type"] == "string"

    def test_review_tool_parameters_contains_working_dir(self):
        props = cast(dict, ReviewTool.parameters["properties"])
        assert "working_dir" in props
        assert props["working_dir"]["type"] == "string"


class TestCommitToolWorkingDir:
    """验证 CommitTool.execute 的目录切换与恢复。"""

    def test_restore_dir_after_success(self, monkeypatch, tmp_path):
        original_dir = os.getcwd()

        # 让 execute 在读取起点前提前返回，避免真实 git/LLM 调用
        monkeypatch.setattr(
            "jarvis.jarvis_tools.commit.find_recent_non_checkout_commit",
            lambda: "",
        )
        monkeypatch.setattr(
            "jarvis.jarvis_tools.commit.get_latest_commit_hash", lambda: ""
        )

        tool = CommitTool()
        result = tool.execute(
            {"working_dir": str(tmp_path), "agent": _FakeAgent(), "skip_review": True}
        )
        assert result["success"] is False  # 无压缩起点，走失败分支
        assert os.getcwd() == original_dir  # 失败后仍恢复原目录

    def test_restore_dir_after_exception(self, monkeypatch, tmp_path):
        original_dir = os.getcwd()

        def boom():
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "jarvis.jarvis_tools.commit.find_recent_non_checkout_commit", boom
        )

        tool = CommitTool()
        result = tool.execute(
            {"working_dir": str(tmp_path), "agent": _FakeAgent(), "skip_review": True}
        )
        assert result["success"] is False
        assert "boom" in result["stderr"]
        assert os.getcwd() == original_dir  # 异常后仍恢复原目录

    def test_no_working_dir_keeps_cwd(self, monkeypatch):
        original_dir = os.getcwd()
        monkeypatch.setattr(
            "jarvis.jarvis_tools.commit.find_recent_non_checkout_commit",
            lambda: "",
        )
        monkeypatch.setattr(
            "jarvis.jarvis_tools.commit.get_latest_commit_hash", lambda: ""
        )

        tool = CommitTool()
        tool.execute({"agent": _FakeAgent(), "skip_review": True})
        assert os.getcwd() == original_dir


class TestReviewToolWorkingDir:
    """验证 ReviewTool.execute 的目录切换、恢复与联动透传。"""

    def test_restore_dir_and_pass_working_dir_to_auto_commit(
        self, monkeypatch, tmp_path
    ):
        original_dir = os.getcwd()
        calls = []

        def fake_run_review(self, agent):
            calls.append(os.getcwd())
            return {"ok": True, "issues": [], "summary": "通过"}

        def fake_auto_commit(self, agent, working_dir=None):
            calls.append(("auto_commit", working_dir, os.getcwd()))

        monkeypatch.setattr(ReviewTool, "run_review", fake_run_review)
        monkeypatch.setattr(ReviewTool, "_auto_commit", fake_auto_commit)

        tool = ReviewTool()
        result = tool.execute({"working_dir": str(tmp_path), "agent": _FakeAgent()})

        assert result["success"] is True
        assert calls[0] == str(tmp_path)  # run_review 在目标目录执行
        assert calls[1] == ("auto_commit", str(tmp_path), str(tmp_path))
        assert os.getcwd() == original_dir  # 结束后恢复原目录

    def test_restore_dir_after_exception(self, monkeypatch, tmp_path):
        original_dir = os.getcwd()

        def fake_run_review(self, agent):
            raise RuntimeError("review boom")

        monkeypatch.setattr(ReviewTool, "run_review", fake_run_review)

        tool = ReviewTool()
        result = tool.execute({"working_dir": str(tmp_path), "agent": _FakeAgent()})

        assert result["success"] is False
        assert "review boom" in result["stderr"]
        assert os.getcwd() == original_dir

    def test_disable_review_skips_chdir(self, tmp_path):
        """disable_review 时直接返回，不应 chdir。"""
        original_dir = os.getcwd()

        class DisabledAgent(_FakeAgent):
            disable_review = True

        tool = ReviewTool()
        result = tool.execute({"working_dir": str(tmp_path), "agent": DisabledAgent()})

        assert result["success"] is False
        assert "已禁用" in result["stderr"]
        assert os.getcwd() == original_dir
