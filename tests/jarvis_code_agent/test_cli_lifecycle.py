# -*- coding: utf-8 -*-
"""code_agent cli 生命周期测试"""

from types import SimpleNamespace


from jarvis.jarvis_code_agent import code_agent


class _DummyServer:
    def __init__(self, events):
        self._events = events

    @property
    def should_exit(self):
        return False

    @should_exit.setter
    def should_exit(self, value):
        self._events.append(("gateway_shutdown", value))


class _DummyThread:
    def __init__(self, target=None, daemon=None):
        self.target = target
        self.daemon = daemon

    def start(self):
        return None


class _DummyCodeAgent:
    def __init__(self, *args, **kwargs):
        pass

    def restore_session(self):
        return False

    def run(self, task, prefix="", suffix=""):
        return "ok"


class _DummyWorktreeManager:
    def __init__(self, repo_root):
        self.repo_root = repo_root

    def get_current_branch(self):
        return "main"

    def create_worktree(self):
        return self.repo_root


def test_cli_keeps_gateway_alive_until_after_worktree_merge(monkeypatch, tmp_path):
    """验证 worktree 合并完成后才关闭 gateway。"""
    events = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        code_agent, "check_and_launch_tmux", lambda config_file=None: None
    )
    monkeypatch.setattr(code_agent, "init_env", lambda *args, **kwargs: None)
    monkeypatch.setattr(code_agent, "find_git_root_and_cd", lambda current_dir: None)
    monkeypatch.setattr(
        code_agent, "_acquire_single_instance_lock", lambda lock_name=None: None
    )
    monkeypatch.setattr(code_agent, "CodeAgent", _DummyCodeAgent)
    monkeypatch.setattr(code_agent, "WorktreeManager", _DummyWorktreeManager)
    monkeypatch.setattr(code_agent.os, "chdir", lambda path: None)
    monkeypatch.setattr(
        code_agent.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(
        code_agent,
        "_handle_worktree_merge",
        lambda *args, **kwargs: events.append(("worktree_merge", None)),
    )

    class _DummyConfig:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    monkeypatch.setitem(
        __import__("sys").modules,
        "uvicorn",
        SimpleNamespace(
            Config=_DummyConfig, Server=lambda config: _DummyServer(events)
        ),
    )
    monkeypatch.setitem(
        __import__("sys").modules, "threading", SimpleNamespace(Thread=_DummyThread)
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "fastapi",
        SimpleNamespace(
            FastAPI=lambda: SimpleNamespace(get=lambda path: lambda func: func)
        ),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "jarvis.jarvis_web_gateway.app",
        SimpleNamespace(
            create_app=lambda custom_app=None: object(),
            get_current_execution_status=lambda: "running",
        ),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "jarvis.jarvis_gateway.manager",
        SimpleNamespace(
            set_current_gateway=lambda gateway: events.append(
                ("set_current_gateway", gateway)
            )
        ),
    )

    code_agent.cli(
        task="demo task",
        task_file=None,
        non_interactive=True,
        restore_session=False,
        worktree=True,
        dispatch=False,
        web_gateway=True,
        web_gateway_port=8765,
    )

    assert events == [
        ("worktree_merge", None),
        ("gateway_shutdown", True),
        ("set_current_gateway", None),
    ]
