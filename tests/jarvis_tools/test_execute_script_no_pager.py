# -*- coding: utf-8 -*-
"""execute_script 非交互模式禁用分页器（pager）测试

对应 NLSpec：.jarvis/.df/specs/disable-pager.md
- 非交互（captured/auto）模式：注入 GIT_PAGER/PAGER/MANPAGER/LESS 并强制覆盖
- interactive 模式：不注入，保持用户原有体验
- Windows 不在范围内
"""
import subprocess
from typing import Any, Dict, List

import pytest

from jarvis.jarvis_tools.execute_script import ScriptTool

PAGER_ENV = {
    "GIT_PAGER": "cat",
    "PAGER": "cat",
    "MANPAGER": "cat",
    "LESS": "FRX",
}


class _PtyRecorder:
    """替换 _execute_on_unix_interactive_pty，记录传入的 env 并返回固定结果。"""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append(kwargs)
        return {"success": True, "stdout": "ok", "stderr": ""}


@pytest.fixture
def pty_recorder(monkeypatch):
    recorder = _PtyRecorder()
    monkeypatch.setattr(
        ScriptTool, "_execute_on_unix_interactive_pty", lambda self, **kw: recorder(**kw)
    )
    monkeypatch.setattr(ScriptTool, "_is_windows", staticmethod(lambda: False))
    return recorder


def _assert_pager_env(env: Dict[str, str]) -> None:
    for key, value in PAGER_ENV.items():
        assert env.get(key) == value, f"{key} 应为 {value!r}，实际 {env.get(key)!r}"


def test_captured_mode_injects_pager_env(pty_recorder):
    tool = ScriptTool()
    result = tool._execute_script_with_interpreter(
        "bash", "echo hi", execution_mode="captured"
    )

    assert result == {"success": True, "stdout": "ok", "stderr": ""}
    assert len(pty_recorder.calls) == 1
    _assert_pager_env(pty_recorder.calls[0]["env"])


def test_captured_mode_overrides_user_pager_env(pty_recorder, monkeypatch):
    """用户已配置 PAGER/GIT_PAGER（如 delta）时也必须强制覆盖。"""
    monkeypatch.setenv("PAGER", "delta")
    monkeypatch.setenv("GIT_PAGER", "delta")
    monkeypatch.setenv("MANPAGER", "delta")
    monkeypatch.setenv("LESS", "-R")

    tool = ScriptTool()
    tool._execute_script_with_interpreter("bash", "echo hi", execution_mode="captured")

    _assert_pager_env(pty_recorder.calls[0]["env"])


def test_auto_mode_non_interactive_injects_pager_env(pty_recorder, monkeypatch):
    """auto 模式在非交互环境（is_non_interactive() 为真）下走非交互分支。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.is_non_interactive", lambda: True
    )

    tool = ScriptTool()
    tool._execute_script_with_interpreter("bash", "echo hi", execution_mode="auto")

    assert len(pty_recorder.calls) == 1
    _assert_pager_env(pty_recorder.calls[0]["env"])


def test_interactive_mode_also_injects_pager_env(pty_recorder, monkeypatch):
    """interactive 模式同样注入分页器变量：任何模式都不允许 pager 挂起。"""
    for key in PAGER_ENV:
        monkeypatch.delenv(key, raising=False)

    tool = ScriptTool()
    tool._execute_script_with_interpreter(
        "bash", "echo hi", execution_mode="interactive"
    )

    assert len(pty_recorder.calls) == 1
    _assert_pager_env(pty_recorder.calls[0]["env"])


def test_interactive_mode_overrides_user_pager_env(pty_recorder, monkeypatch):
    """interactive 模式下用户已设置的 PAGER（如 delta）也必须被强制覆盖。"""
    monkeypatch.setenv("PAGER", "delta")
    monkeypatch.setenv("GIT_PAGER", "delta")

    tool = ScriptTool()
    tool._execute_script_with_interpreter(
        "bash", "echo hi", execution_mode="interactive"
    )

    _assert_pager_env(pty_recorder.calls[0]["env"])


def test_auto_mode_interactive_context_also_injects_pager_env(
    pty_recorder, monkeypatch
):
    """auto 模式在交互式上下文（is_non_interactive() 为假）下也必须注入。

    这是此前的缺陷：交互式会话里 agent 跑 git show 走 VirtualTTY 分支，
    未注入 pager 变量导致挂起。
    """
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.is_non_interactive", lambda: False
    )

    tool = ScriptTool()
    tool._execute_script_with_interpreter("bash", "echo hi", execution_mode="auto")

    assert len(pty_recorder.calls) == 1
    _assert_pager_env(pty_recorder.calls[0]["env"])


def test_non_interactive_keeps_existing_env_and_term(pty_recorder, monkeypatch):
    """注入分页器变量不破坏既有 env 构造（TERM、PYTHONIOENCODING 等）。"""
    monkeypatch.setenv("JARVIS_TEST_KEEP_ME", "1")

    tool = ScriptTool()
    tool._execute_script_with_interpreter("python3", "print(1)", execution_mode="captured")

    env = pty_recorder.calls[0]["env"]
    assert env.get("TERM") == "xterm-256color"
    assert env.get("PYTHONIOENCODING") == "utf-8"
    assert env.get("JARVIS_TEST_KEEP_ME") == "1"
    _assert_pager_env(env)


def test_windows_path_does_not_inject_pager_env(monkeypatch):
    """Windows 不在范围内：不注入分页器变量。"""
    captured: Dict[str, Any] = {}

    def fake_windows(self, **kwargs: Any) -> Dict[str, Any]:
        captured.update(kwargs)
        return {"success": True, "stdout": "", "stderr": ""}

    monkeypatch.setattr(ScriptTool, "_is_windows", staticmethod(lambda: True))
    monkeypatch.setattr(ScriptTool, "_execute_on_windows", fake_windows)

    tool = ScriptTool()
    tool._execute_script_with_interpreter("powershell", "echo hi", execution_mode="captured")

    assert captured.get("is_non_interactive") is True
    for key in PAGER_ENV:
        assert key not in captured, f"Windows 路径不应注入 {key}"


def _git_available() -> bool:
    try:
        subprocess.run(
            ["git", "--version"], capture_output=True, check=True, timeout=10
        )
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _git_available() or ScriptTool._is_windows(), reason="需要 Unix 环境与 git"
)
def test_git_show_does_not_hang_in_captured_mode(tmp_path):
    """端到端：captured 模式下 git show 大输出不挂起、完整返回。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
         "--allow-empty", "-m", "init"],
        cwd=repo,
        check=True,
    )
    big_file = repo / "big.txt"
    big_file.write_text("\n".join(f"line-{i}" for i in range(2000)) + "\n")
    subprocess.run(["git", "add", "big.txt"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "big"],
        cwd=repo,
        check=True,
    )

    tool = ScriptTool()
    result = tool._execute_script_with_interpreter(
        "bash",
        f"cd {repo} && git show HEAD:big.txt",
        execution_mode="captured",
    )

    assert result["success"] is True, result
    assert "line-1999" in result["stdout"]
    assert "line-0" in result["stdout"]


@pytest.mark.skipif(
    not _git_available() or ScriptTool._is_windows(), reason="需要 Unix 环境与 git"
)
def test_git_show_does_not_hang_in_interactive_mode(tmp_path):
    """端到端：interactive（VirtualTTY）模式下 git show 大输出也不挂起。

    真实 PTY 中 git 会因检测到 TTY 拉起 pager 并等待按键；注入 pager 变量后
    必须完整输出并立即返回。此测试直接验证行为，而非仅检查 env 字典。
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    big_file = repo / "big.txt"
    big_file.write_text("\n".join(f"line-{i}" for i in range(2000)) + "\n")
    subprocess.run(["git", "add", "big.txt"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "big"],
        cwd=repo,
        check=True,
    )

    tool = ScriptTool()
    result = tool._execute_script_with_interpreter(
        "bash",
        f"cd {repo} && git -c core.pager=less show HEAD:big.txt",
        execution_mode="interactive",
    )

    assert result["success"] is True, result
    assert "line-1999" in result["stdout"]
    assert "line-0" in result["stdout"]
