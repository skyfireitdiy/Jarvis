# -*- coding: utf-8 -*-
"""每日自动更新流程（check_and_update_git_repo）依赖重装接入测试。

覆盖 NLSpec code-update-deps-reinstall 的每日更新侧行为：
- 代码更新安装成功后调用 reinstall_deps_after_update
- master 节点（master_url 为空）include_frontend=True
- child 节点（master_url 非空）include_frontend=False
- 依赖重装失败不影响更新结果（不抛异常）
"""
from unittest.mock import patch

from jarvis.jarvis_utils import git_utils


class FakeResult:
    """模拟 subprocess.CompletedProcess。"""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout.encode() if isinstance(stdout, str) else stdout
        self.stderr = stderr.encode() if isinstance(stderr, str) else stderr


def _patch_git_flow():
    """patch check_and_update_git_repo 的 git 流程依赖，使其走到安装成功分支。

    返回 (mocks, install_run_mock)：
    - mocks: 供 with 语句使用的 patch 对象列表
    - install_run_mock: subprocess.run 的 mock，用于让安装命令返回成功
    """
    mocks = [
        patch("jarvis.jarvis_utils.git_utils.get_data_dir", return_value="/tmp/data"),
        patch("jarvis.jarvis_utils.git_utils.os.path.exists", return_value=False),
        patch("jarvis.jarvis_utils.git_utils.find_git_root", return_value="/repo"),
        patch(
            "jarvis.jarvis_utils.git_utils.has_uncommitted_changes",
            return_value=False,
        ),
        patch(
            "jarvis.jarvis_utils.git_utils.subprocess.run",
            side_effect=_git_runner,
        ),
        patch(
            "jarvis.jarvis_utils.git_utils.user_confirm",
            return_value=False,
        ),
        patch(
            "jarvis.jarvis_utils.git_utils.PrettyOutput.auto_print",
        ),
        patch(
            "jarvis.jarvis_utils.utils._set_update_reboot_flag",
        ),
    ]
    return mocks


def _git_runner(cmd, *args, **kwargs):
    """模拟 git 流程命令，使流程走到安装成功分支。"""
    cmd0 = cmd[0] if cmd else ""
    if cmd0 == "git":
        if cmd[1] == "fetch":
            return FakeResult()
        if cmd[1] == "describe":
            return FakeResult(stdout="v7.0.0\n")
        if cmd[1] == "ls-remote":
            return FakeResult(stdout="refs/tags/v7.0.1\n")
        if cmd[1] == "checkout":
            return FakeResult()
    # 安装命令（uv/pip install -e .）返回成功
    return FakeResult(stdout="Installed 1 package\n")


class TestDailyUpdateDeps:
    """每日更新流程依赖重装。"""

    def test_master_calls_reinstall_with_frontend(self):
        """master 节点（master_url 为空）include_frontend=True。"""
        mocks = _patch_git_flow()
        with patch(
            "jarvis.jarvis_utils.git_utils.reinstall_deps_after_update",
            return_value={
                "uv": {
                    "attempted": True,
                    "method": "uv_tool_install",
                    "success": True,
                    "detail": "ok",
                },
                "npm": {"attempted": True, "success": True, "detail": "ok"},
            },
        ) as mock_reinstall, patch(
            "jarvis.jarvis_utils.globals.master_url", None
        ):
            for m in mocks:
                m.start()
            try:
                result = git_utils.check_and_update_git_repo("/repo")
            finally:
                for m in mocks:
                    m.stop()

        assert result is False
        mock_reinstall.assert_called_once()
        kwargs = mock_reinstall.call_args
        assert kwargs.args[0] == "/repo"
        assert kwargs.kwargs.get("include_frontend") is True

    def test_child_passes_include_frontend_false(self):
        """child 节点（master_url 非空）include_frontend=False。"""
        mocks = _patch_git_flow()
        with patch(
            "jarvis.jarvis_utils.git_utils.reinstall_deps_after_update",
            return_value={
                "uv": {
                    "attempted": True,
                    "method": "uv_tool_install",
                    "success": True,
                    "detail": "ok",
                },
                "npm": {
                    "attempted": False,
                    "success": False,
                    "detail": "child 节点跳过前端 npm install",
                },
            },
        ) as mock_reinstall, patch(
            "jarvis.jarvis_utils.globals.master_url", "http://master:8000"
        ):
            for m in mocks:
                m.start()
            try:
                result = git_utils.check_and_update_git_repo("/repo")
            finally:
                for m in mocks:
                    m.stop()

        assert result is False
        mock_reinstall.assert_called_once()
        kwargs = mock_reinstall.call_args
        assert kwargs.kwargs.get("include_frontend") is False

    def test_reinstall_failure_does_not_raise(self):
        """依赖重装抛异常不影响更新结果（不抛异常）。"""
        mocks = _patch_git_flow()
        with patch(
            "jarvis.jarvis_utils.git_utils.reinstall_deps_after_update",
            side_effect=RuntimeError("boom"),
        ) as mock_reinstall, patch(
            "jarvis.jarvis_utils.globals.master_url", None
        ):
            for m in mocks:
                m.start()
            try:
                result = git_utils.check_and_update_git_repo("/repo")
            finally:
                for m in mocks:
                    m.stop()

        assert result is False
        mock_reinstall.assert_called_once()


class TestDailyUpdateDepsBackground:
    """后台每日更新流程（check_and_update_git_repo_background）依赖重装。"""

    def _run_background(self):
        """执行后台更新函数（不返回结果，仅验证副作用）。"""
        git_utils.check_and_update_git_repo_background("/repo")

    def test_master_calls_reinstall_with_frontend(self):
        """master 节点（master_url 为空）include_frontend=True。"""
        mocks = _patch_git_flow()
        with patch(
            "jarvis.jarvis_utils.git_utils.reinstall_deps_after_update",
            return_value={
                "uv": {
                    "attempted": True,
                    "method": "uv_tool_install",
                    "success": True,
                    "detail": "ok",
                },
                "npm": {"attempted": True, "success": True, "detail": "ok"},
            },
        ) as mock_reinstall, patch(
            "jarvis.jarvis_utils.globals.master_url", None
        ):
            for m in mocks:
                m.start()
            try:
                self._run_background()
            finally:
                for m in mocks:
                    m.stop()

        mock_reinstall.assert_called_once()
        kwargs = mock_reinstall.call_args
        assert kwargs.args[0] == "/repo"
        assert kwargs.kwargs.get("include_frontend") is True

    def test_child_passes_include_frontend_false(self):
        """child 节点（master_url 非空）include_frontend=False。"""
        mocks = _patch_git_flow()
        with patch(
            "jarvis.jarvis_utils.git_utils.reinstall_deps_after_update",
            return_value={
                "uv": {
                    "attempted": True,
                    "method": "uv_tool_install",
                    "success": True,
                    "detail": "ok",
                },
                "npm": {
                    "attempted": False,
                    "success": False,
                    "detail": "child 节点跳过前端 npm install",
                },
            },
        ) as mock_reinstall, patch(
            "jarvis.jarvis_utils.globals.master_url", "http://master:8000"
        ):
            for m in mocks:
                m.start()
            try:
                self._run_background()
            finally:
                for m in mocks:
                    m.stop()

        mock_reinstall.assert_called_once()
        kwargs = mock_reinstall.call_args
        assert kwargs.kwargs.get("include_frontend") is False

    def test_reinstall_failure_does_not_raise(self):
        """依赖重装抛异常不影响后台更新（不抛异常）。"""
        mocks = _patch_git_flow()
        with patch(
            "jarvis.jarvis_utils.git_utils.reinstall_deps_after_update",
            side_effect=RuntimeError("boom"),
        ) as mock_reinstall, patch(
            "jarvis.jarvis_utils.globals.master_url", None
        ):
            for m in mocks:
                m.start()
            try:
                self._run_background()
            finally:
                for m in mocks:
                    m.stop()

        mock_reinstall.assert_called_once()
