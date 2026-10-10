# -*- coding: utf-8 -*-
"""会话实时保存守护进程（SessionDaemon）单元测试。

覆盖：
- 正常退出：守护进程收到 quit 后清理内存，不落盘
- 意外退出：管道 EOF（模拟进程被 kill）时按快照落盘，且可被恢复
- build_snapshot_files 的缩进/编码器映射
"""

import json
import os
import subprocess
import sys
import time

import pytest

from jarvis.jarvis_agent.session_daemon import SessionDaemon
from jarvis.jarvis_agent.session_daemon import build_snapshot_files

pytestmark = pytest.mark.skipif(
    not hasattr(os, "fork"), reason="需要 os.fork（POSIX 平台）"
)


def _wait_for(predicate, timeout: float = 5.0, interval: float = 0.02) -> bool:
    """轮询等待条件成立。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class TestBuildSnapshotFiles:
    """build_snapshot_files 的映射逻辑。"""

    def test_indent_and_encoder_mapping(self):
        files = [
            ("/tmp/a_saved_session_x_20260101_000000.json", {"messages": []}, None),
            ("/tmp/a_saved_session_x_20260101_000000_commit.json", {"c": 1}, None),
            ("/tmp/a_saved_session_x_20260101_000000_state.json", {"s": 1}, object()),
            ("/tmp/a_saved_session_x_tasklist.json", {"t": 1}, None),
        ]
        plan = build_snapshot_files("ignored", files)
        assert len(plan) == 4
        by_name = {os.path.basename(p["path"]): p for p in plan}
        # 主会话 / commit 使用 indent=4
        assert by_name["a_saved_session_x_20260101_000000.json"]["indent"] == 4
        assert by_name["a_saved_session_x_20260101_000000_commit.json"]["indent"] == 4
        # state / tasklist 使用 indent=2
        assert by_name["a_saved_session_x_20260101_000000_state.json"]["indent"] == 2
        assert by_name["a_saved_session_x_tasklist.json"]["indent"] == 2
        # 仅 state 使用 SafeEncoder
        assert by_name["a_saved_session_x_20260101_000000_state.json"][
            "use_safe_encoder"
        ]
        assert not by_name["a_saved_session_x_20260101_000000.json"][
            "use_safe_encoder"
        ]


class TestSessionDaemonNormalExit:
    """正常退出：不落盘。"""

    def test_normal_exit_does_not_write(self, tmp_path):
        daemon = SessionDaemon()
        assert daemon.start()
        try:
            session_file = str(tmp_path / "sess_saved_session_agent_20260101_000000.json")
            files = [
                {"path": session_file, "data": {"messages": [{"role": "user"}]},
                 "indent": 4, "use_safe_encoder": False},
            ]
            assert daemon.send_snapshot(files)
            # 正常退出通知
            daemon.send_quit()
            # 给守护进程一点时间；即便落盘也只会写这些文件
            time.sleep(0.3)
            assert not os.path.exists(session_file)
        finally:
            daemon.send_quit()


class TestSessionDaemonCrash:
    """意外退出：EOF 时落盘。"""

    def test_crash_writes_files(self, tmp_path):
        """在独立子进程中运行守护进程，父进程发送快照后直接 _exit 模拟被 kill。"""
        session_file = str(tmp_path / "sess_saved_session_agent_20260101_000000.json")
        commit_file = session_file[:-5] + "_commit.json"
        state_file = str(tmp_path / "sess_saved_session_agent_20260101_000000_state.json")
        tasklist_file = str(tmp_path / "sess_saved_session_agent_tasklist.json")

        script = f"""
import os, time
from jarvis.jarvis_agent.session_daemon import SessionDaemon
d = SessionDaemon()
assert d.start()
files = [
    {{"path": {session_file!r}, "data": {{"messages": [{{"role": "user", "content": "hi"}}]}},
      "indent": 4, "use_safe_encoder": False}},
    {{"path": {commit_file!r}, "data": {{"current_commit": "abc", "agent_name": "agent"}},
      "indent": 4, "use_safe_encoder": False}},
    {{"path": {state_file!r}, "data": {{"metadata": {{"agent_name": "agent"}}}},
      "indent": 2, "use_safe_encoder": True}},
    {{"path": {tasklist_file!r}, "data": {{"task_lists": {{}}}},
      "indent": 2, "use_safe_encoder": False}},
]
assert d.send_snapshot(files)
time.sleep(0.3)
# 模拟被 kill：直接 _exit，不发送 quit，管道写端关闭触发守护进程 EOF
os._exit(0)
"""
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.getcwd(),
        )
        assert proc.returncode == 0, proc.stderr

        # 守护进程应在 EOF 后落盘 4 个文件
        assert _wait_for(lambda: os.path.exists(session_file)), "主会话文件未落盘"
        assert _wait_for(lambda: os.path.exists(commit_file)), "commit 文件未落盘"
        assert _wait_for(lambda: os.path.exists(state_file)), "state 文件未落盘"
        assert _wait_for(lambda: os.path.exists(tasklist_file)), "tasklist 文件未落盘"

        # 内容应可被正常解析（格式与 save_session 一致）
        with open(session_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["messages"][0]["content"] == "hi"
        with open(commit_file, "r", encoding="utf-8") as f:
            assert json.load(f)["current_commit"] == "abc"


class TestSessionDaemonDisabled:
    """未启动时所有操作应为安全空操作。"""

    def test_operations_noop_when_not_started(self):
        daemon = SessionDaemon()
        assert not daemon.enabled
        assert not daemon.send_snapshot([])
        # 不应抛异常
        daemon.send_quit()
