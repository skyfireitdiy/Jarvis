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


class _DummyFastAPI:
    def __init__(self):
        self.routes = {}

    def get(self, path):
        def decorator(func):
            self.routes[path] = func
            return func

        return decorator
