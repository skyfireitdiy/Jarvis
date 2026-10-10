# -*- coding: utf-8 -*-
"""AutoWorker 插件 Agent 侧工具 task_manager.py 测试。

覆盖：
1. 工具元信息（name 与文件名一致、check 可用、parameters 合法）；
2. 默认上下文推断：Agent 以任务子目录为 cwd 时自动定位当前任务；
3. 各动作：get_task / set_status / add_note / update_task / create_task / list_tasks；
4. 显式 workdir/task_id 操作其他任务；
5. 边界：非任务目录且未提供 workdir 时报错；未知 action 报错。

用 importlib 直接加载插件源码，不依赖全局配置加载。
"""
import importlib.util
import json
import os
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

PLUGIN_DIR = (
    Path(__file__).resolve().parents[2] / "builtin" / "plugins" / "autoworker"
)
TOOL_FILE = PLUGIN_DIR / "tools" / "task_manager.py"
API_FILE = PLUGIN_DIR / "plugin" / "api.py"


@pytest.fixture(scope="module")
def tool_cls():
    """加载 task_manager.py，返回 TaskManagerTool 类。"""
    assert TOOL_FILE.is_file(), f"工具文件不存在: {TOOL_FILE}"
    spec = importlib.util.spec_from_file_location("autoworker_task_manager", str(TOOL_FILE))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["autoworker_task_manager"] = mod
    spec.loader.exec_module(mod)
    return mod.TaskManagerTool


@pytest.fixture()
def api():
    """加载 plugin/api.py 用于准备任务数据。"""
    spec = importlib.util.spec_from_file_location("autoworker_api_tm", str(API_FILE))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["autoworker_api_tm"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def workdir(tmp_path):
    wd = tmp_path / "tasks"
    wd.mkdir()
    return str(wd)


def _chdir(path):
    """切换 cwd 的上下文管理器（简单实现）。"""
    class _Ctx:
        def __enter__(self):
            self._old = os.getcwd()
            os.chdir(path)

        def __exit__(self, *a):
            os.chdir(self._old)

    return _Ctx()


def test_tool_metadata(tool_cls):
    """工具元信息：name 与文件名一致、check 可用、parameters 合法。"""
    assert tool_cls.name == "task_manager"
    assert tool_cls.check() is True
    params = tool_cls.parameters
    assert params["type"] == "object"
    assert "action" in params["required"]
    assert set(params["properties"]["action"]["enum"]) == {
        "create_task",
        "update_task",
        "set_status",
        "add_note",
        "list_tasks",
        "get_task",
    }


def test_list_tasks(tool_cls, api, workdir):
    """list_tasks 显式 workdir 列出任务。"""
    api.create_task(workdir=workdir, title="任务一")
    api.create_task(workdir=workdir, title="任务二")
    tool = tool_cls()
    res = tool.execute({"action": "list_tasks", "workdir": workdir})
    assert res["success"] is True
    payload = json.loads(res["stdout"])
    assert payload["count"] == 2
    assert [t["id"] for t in payload["data"]] == ["T001", "T002"]


def test_create_task(tool_cls, workdir):
    """create_task 通过工具创建任务。"""
    tool = tool_cls()
    res = tool.execute(
        {
            "action": "create_task",
            "workdir": workdir,
            "title": "实现登录",
            "description": "账号密码登录",
            "tags": ["认证"],
            "due_date": "2026-10-20",
        }
    )
    assert res["success"] is True
    payload = json.loads(res["stdout"])
    assert payload["data"]["id"] == "T001"
    assert payload["data"]["title"] == "实现登录"
    assert payload["data"]["task_dir"]


def test_default_context_from_cwd(tool_cls, api, workdir):
    """Agent 以任务子目录为 cwd 时，get_task/set_status/add_note 自动定位当前任务。"""
    res = api.create_task(workdir=workdir, title="当前任务")
    task_dir = res["data"]["task_dir"]
    tool = tool_cls()

    with _chdir(task_dir):
        # get_task 默认当前任务
        r = tool.execute({"action": "get_task"})
        assert r["success"] is True
        assert json.loads(r["stdout"])["data"]["id"] == "T001"

        # set_status 默认当前任务
        r = tool.execute({"action": "set_status", "status": "running"})
        assert r["success"] is True
        assert json.loads(r["stdout"])["data"]["status"] == "running"

        # add_note 默认当前任务
        r = tool.execute({"action": "add_note", "content": "关键信息"})
        assert r["success"] is True
        notes = json.loads(r["stdout"])["data"]["notes"]
        assert notes[0]["content"] == "关键信息"

        # list_tasks 由 cwd 推断 workdir
        r = tool.execute({"action": "list_tasks"})
        assert r["success"] is True
        assert json.loads(r["stdout"])["count"] == 1


def test_update_task_via_tool(tool_cls, api, workdir):
    """update_task 更新标题/描述，目录名不变。"""
    res = api.create_task(workdir=workdir, title="旧标题")
    task_dir = res["data"]["task_dir"]
    tool = tool_cls()
    with _chdir(task_dir):
        r = tool.execute(
            {"action": "update_task", "title": "新标题", "description": "新描述"}
        )
        assert r["success"] is True
        data = json.loads(r["stdout"])["data"]
        assert data["title"] == "新标题"
        assert data["description"] == "新描述"
        assert Path(task_dir).name == "T001_旧标题"  # 目录名不变


def test_explicit_task_id_other_task(tool_cls, api, workdir):
    """显式 workdir+task_id 操作其他任务（Agent 在任务一目录下操作任务二）。"""
    r1 = api.create_task(workdir=workdir, title="任务一")
    api.create_task(workdir=workdir, title="任务二")
    tool = tool_cls()
    with _chdir(r1["data"]["task_dir"]):
        r = tool.execute(
            {"action": "set_status", "workdir": workdir, "task_id": "T002", "status": "completed"}
        )
        assert r["success"] is True
        assert json.loads(r["stdout"])["data"]["id"] == "T002"
    # 任务二确实被改，任务一未变
    assert api.get_task(workdir=workdir, task_id="T002")["data"]["status"] == "completed"
    assert api.get_task(workdir=workdir, task_id="T001")["data"]["status"] == "pending"


def test_non_task_dir_without_workdir_errors(tool_cls, tmp_path):
    """非任务目录且未提供 workdir 时报错。"""
    tool = tool_cls()
    plain = tmp_path / "plain"
    plain.mkdir()
    with _chdir(str(plain)):
        r = tool.execute({"action": "get_task"})
        assert r["success"] is False
        assert "workdir" in r["stderr"] or "工作目录" in r["stderr"]


def test_unknown_action_errors(tool_cls, workdir):
    """未知 action 报错。"""
    tool = tool_cls()
    r = tool.execute({"action": "no_such_action", "workdir": workdir})
    assert r["success"] is False
    assert "未知 action" in r["stderr"]


def test_missing_action_errors(tool_cls):
    """缺少 action 报错。"""
    tool = tool_cls()
    r = tool.execute({})
    assert r["success"] is False
    assert "action" in r["stderr"]


def test_set_status_invalid_via_tool(tool_cls, api, workdir):
    """无效状态经工具返回失败。"""
    res = api.create_task(workdir=workdir, title="任务")
    tool = tool_cls()
    with _chdir(res["data"]["task_dir"]):
        r = tool.execute({"action": "set_status", "status": "failed"})
        assert r["success"] is False
        assert "无效状态" in r["stderr"]
