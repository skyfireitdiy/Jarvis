# -*- coding: utf-8 -*-
"""git_utils.reinstall_deps_after_update 模块单元测试。

覆盖 NLSpec code-update-deps-reinstall 的公共依赖重装函数：
- uv tool install 型探测与 --force 重装
- uv pip install 型探测与 -e . 重装
- 非 uv 安装跳过（attempted=false）
- include_frontend=False 跳过 npm
- npm install 执行且不执行 build
- 失败仅记录不抛异常
- 返回结构符合 spec
"""
from unittest.mock import patch

from jarvis.jarvis_utils.git_utils import reinstall_deps_after_update


class FakeResult:
    """模拟 subprocess.CompletedProcess。"""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout.encode() if isinstance(stdout, str) else stdout
        self.stderr = stderr.encode() if isinstance(stderr, str) else stderr


def make_runner(calls):
    """根据 cmd 元组分发返回结果的 subprocess.run 替身。

    calls: dict，key 为 cmd 元组（如 ("uv", "tool", "list")），value 为 FakeResult。
    未匹配的命令默认返回成功。
    """

    def runner(cmd, *args, **kwargs):
        key = tuple(cmd)
        if key in calls:
            return calls[key]
        return FakeResult()

    return runner


def _tool_install_calls(overrides=None):
    """构造 uv tool install 型环境的命令返回表。"""
    calls = {
        ("uv", "tool", "list"): FakeResult(
            stdout="jarvis-ai-assistant v7.0.1\n- jvs\n"
        ),
        ("uv", "pip", "show", "jarvis-ai-assistant"): FakeResult(returncode=1),
        ("uv", "tool", "install", "-e", ".", "--force"): FakeResult(
            stdout="Installed 1 executable: jvs\n"
        ),
        ("npm", "install"): FakeResult(stdout="added 1 package\n"),
    }
    if overrides:
        calls.update(overrides)
    return calls


class TestUvToolInstall:
    """uv tool install 型安装方式。"""

    def test_detects_tool_install_and_runs_force_reinstall(self):
        """探测到 uv tool install 型，执行 uv tool install -e . --force。"""
        calls = _tool_install_calls()
        with patch(
            "jarvis.jarvis_utils.git_utils.subprocess.run",
            side_effect=make_runner(calls),
        ) as mock_run:
            result = reinstall_deps_after_update("/repo")

        uv = result["uv"]
        assert uv["attempted"] is True
        assert uv["method"] == "uv_tool_install"
        assert uv["success"] is True
        assert "uv tool install -e . --force" in uv["detail"]

        # 验证重装命令确实带 --force 且 cwd 为 src_dir
        install_calls = [
            c
            for c in mock_run.call_args_list
            if c.args and c.args[0] == ["uv", "tool", "install", "-e", ".", "--force"]
        ]
        assert install_calls, "应执行 uv tool install -e . --force"
        assert install_calls[0].kwargs.get("cwd") == "/repo"

    def test_npm_install_runs_without_build(self):
        """前端执行 npm install，且不执行 npm run build。"""
        calls = _tool_install_calls()
        with patch(
            "jarvis.jarvis_utils.git_utils.subprocess.run",
            side_effect=make_runner(calls),
        ) as mock_run, patch(
            "jarvis.jarvis_utils.git_utils.os.path.isdir", return_value=True
        ) as mock_isdir:
            result = reinstall_deps_after_update("/repo")

        # 前端目录存在性检查被调用
        assert mock_isdir.called

        npm = result["npm"]
        assert npm["attempted"] is True
        assert npm["success"] is True

        npm_calls = [
            c
            for c in mock_run.call_args_list
            if c.args and c.args[0] and c.args[0][0] == "npm"
        ]
        assert npm_calls, "应执行 npm 命令"
        for c in npm_calls:
            assert "build" not in c.args[0], "不应执行 npm run build"

    def test_tool_install_failure_does_not_raise(self):
        """uv tool install 失败时仅记录，不抛异常，npm 仍执行。"""
        calls = _tool_install_calls(
            {
                ("uv", "tool", "install", "-e", ".", "--force"): FakeResult(
                    returncode=1, stderr="Permission denied\n"
                )
            }
        )
        with patch(
            "jarvis.jarvis_utils.git_utils.subprocess.run",
            side_effect=make_runner(calls),
        ), patch("jarvis.jarvis_utils.git_utils.os.path.isdir", return_value=True):
            result = reinstall_deps_after_update("/repo")

        uv = result["uv"]
        assert uv["attempted"] is True
        assert uv["success"] is False
        assert "Permission denied" in uv["detail"]
        assert result["npm"]["attempted"] is True


class TestUvPipInstall:
    """uv pip install 型安装方式。"""

    def test_detects_pip_install_and_runs_editable_reinstall(self):
        """探测到 uv pip install 型，执行 uv pip install -e .。"""
        calls = {
            ("uv", "tool", "list"): FakeResult(stdout="mypy v1.19.1\n- mypy\n"),
            ("uv", "pip", "show", "jarvis-ai-assistant"): FakeResult(
                stdout="Name: jarvis-ai-assistant\nVersion: 7.0.1\n"
            ),
            ("uv", "pip", "install", "-e", "."): FakeResult(
                stdout="Installed 1 package\n"
            ),
            ("npm", "install"): FakeResult(stdout="added 1 package\n"),
        }
        with patch(
            "jarvis.jarvis_utils.git_utils.subprocess.run",
            side_effect=make_runner(calls),
        ) as mock_run:
            result = reinstall_deps_after_update("/repo")

        uv = result["uv"]
        assert uv["attempted"] is True
        assert uv["method"] == "uv_pip_install"
        assert uv["success"] is True

        pip_calls = [
            c
            for c in mock_run.call_args_list
            if c.args and c.args[0] == ["uv", "pip", "install", "-e", "."]
        ]
        assert pip_calls, "应执行 uv pip install -e ."
        assert pip_calls[0].kwargs.get("cwd") == "/repo"


class TestNonUv:
    """非 uv 安装方式。"""

    def test_non_uv_skips_uv_but_still_npm(self):
        """非 uv 安装时 uv 环节跳过（attempted=false），npm 仍执行。"""
        calls = {
            ("uv", "tool", "list"): FakeResult(stdout="mypy v1.19.1\n- mypy\n"),
            ("uv", "pip", "show", "jarvis-ai-assistant"): FakeResult(returncode=1),
            ("npm", "install"): FakeResult(stdout="added 1 package\n"),
        }
        with patch(
            "jarvis.jarvis_utils.git_utils.subprocess.run",
            side_effect=make_runner(calls),
        ), patch("jarvis.jarvis_utils.git_utils.os.path.isdir", return_value=True):
            result = reinstall_deps_after_update("/repo")

        uv = result["uv"]
        assert uv["attempted"] is False
        assert uv["method"] == "skipped"
        assert result["npm"]["attempted"] is True
        assert result["npm"]["success"] is True


class TestIncludeFrontend:
    """include_frontend 参数（child 节点）。"""

    def test_include_frontend_false_skips_npm(self):
        """include_frontend=False 时跳过 npm。"""
        calls = _tool_install_calls()
        with patch(
            "jarvis.jarvis_utils.git_utils.subprocess.run",
            side_effect=make_runner(calls),
        ) as mock_run:
            result = reinstall_deps_after_update("/repo", include_frontend=False)

        assert result["npm"]["attempted"] is False
        # uv 重装仍执行
        assert result["uv"]["attempted"] is True
        npm_calls = [
            c
            for c in mock_run.call_args_list
            if c.args and c.args[0] and c.args[0][0] == "npm"
        ]
        assert not npm_calls, "include_frontend=False 时不应执行 npm"


class TestReturnStructure:
    """返回结构符合 spec。"""

    def test_return_structure(self):
        """返回 dict 含 uv/npm 键，各含 attempted/method/success/detail。"""
        calls = _tool_install_calls()
        with patch(
            "jarvis.jarvis_utils.git_utils.subprocess.run",
            side_effect=make_runner(calls),
        ), patch("jarvis.jarvis_utils.git_utils.os.path.isdir", return_value=True):
            result = reinstall_deps_after_update("/repo")

        assert set(result.keys()) == {"uv", "npm"}
        for key in ("uv", "npm"):
            assert set(result[key].keys()) >= {
                "attempted",
                "success",
                "detail",
            }
        assert "method" in result["uv"]

    def test_frontend_dir_missing_reports_detail(self):
        """前端目录不存在时 npm 环节 attempted=false 且 detail 说明。"""
        calls = _tool_install_calls()
        with patch(
            "jarvis.jarvis_utils.git_utils.subprocess.run",
            side_effect=make_runner(calls),
        ), patch("jarvis.jarvis_utils.git_utils.os.path.isdir", return_value=False):
            result = reinstall_deps_after_update("/repo")

        assert result["npm"]["attempted"] is False
        assert "frontend" in result["npm"]["detail"].lower() or "不存在" in result["npm"]["detail"]
