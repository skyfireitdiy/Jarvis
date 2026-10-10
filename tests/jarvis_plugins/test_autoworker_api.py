# -*- coding: utf-8 -*-
"""AutoWorker 插件（autoworker）私有功能 api.py 测试。

覆盖任务 CRUD：
1. create_task：创建任务、ID 递增、目录名 `ID_标题`、task.json 结构；
2. update_task：更新详情、标题修改不改目录名（避免引用路径漂移）；
3. set_status：状态变更、无效状态报错；
4. add_note：追加带时间戳的 note；
5. list_tasks：扫描发现任务、按 id 升序；
6. get_task：按 id 查找；
7. 边界：workdir 不存在 / 标题为空 / 标签规范化 / 并发多任务独立目录。

用 importlib 直接加载插件源码文件，不依赖全局配置加载，避免污染真实环境。
"""
import importlib.util
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

PLUGIN_DIR = (
    Path(__file__).resolve().parents[2] / "builtin" / "plugins" / "autoworker"
)
API_FILE = PLUGIN_DIR / "plugin" / "api.py"


@pytest.fixture(scope="module")
def api():
    """加载 autoworker/plugin/api.py 模块。"""
    assert API_FILE.is_file(), f"api.py 不存在: {API_FILE}"
    spec = importlib.util.spec_from_file_location("autoworker_api", str(API_FILE))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["autoworker_api"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def workdir(tmp_path):
    """临时后端工作目录。"""
    wd = tmp_path / "tasks"
    wd.mkdir()
    return str(wd)


def _read_task_json(task_dir):
    """读取任务子目录下的 task.json。"""
    tf = Path(task_dir) / ".jarvis" / "autoworker" / "task.json"
    assert tf.is_file(), f"task.json 不存在: {tf}"
    with open(tf, "r", encoding="utf-8") as f:
        return json.load(f)


def test_create_task_basic(api, workdir):
    """创建任务：返回结构、目录命名、task.json 落盘。"""
    res = api.create_task(
        workdir=workdir,
        title="实现登录功能",
        description="支持账号密码登录",
        tags=["前端", "认证"],
        due_date="2026-10-20",
    )
    assert res["success"] is True
    data = res["data"]
    assert data["id"] == "T001"
    assert data["title"] == "实现登录功能"
    assert data["status"] == "pending"
    assert data["tags"] == ["前端", "认证"]
    assert data["due_date"] == "2026-10-20"
    assert data["notes"] == []
    assert data["created_at"] and data["updated_at"]
    # 目录名 = ID_标题
    task_dir = data["task_dir"]
    assert Path(task_dir).name == "T001_实现登录功能"
    # task.json 落盘且不含内部字段 task_dir
    on_disk = _read_task_json(task_dir)
    assert on_disk["id"] == "T001"
    assert "task_dir" not in on_disk


def test_create_task_id_increment(api, workdir):
    """ID 递增：T001、T002、T003。"""
    ids = []
    for title in ["任务一", "任务二", "任务三"]:
        res = api.create_task(workdir=workdir, title=title)
        assert res["success"] is True
        ids.append(res["data"]["id"])
    assert ids == ["T001", "T002", "T003"]


def test_create_task_dir_name_cleans_illegal_chars(api, workdir):
    """目录名清理非法字符（/ 等），但 title 字段保留原始标题。"""
    res = api.create_task(workdir=workdir, title="任务/含斜杠")
    assert res["success"] is True
    data = res["data"]
    assert data["title"] == "任务/含斜杠"  # title 保留
    assert "任务_含斜杠" in Path(data["task_dir"]).name  # 目录名已清理


def test_create_task_requires_title(api, workdir):
    """标题为空时报错。"""
    res = api.create_task(workdir=workdir, title="   ")
    assert res["success"] is False
    assert "标题" in res["error"]


def test_create_task_requires_workdir(api):
    """workdir 为空或不存在时报错。"""
    res = api.create_task(workdir="", title="任务")
    assert res["success"] is False
    res = api.create_task(workdir="/nonexistent/path/xyz", title="任务")
    assert res["success"] is False


def test_update_task_keeps_dir_name(api, workdir):
    """更新标题只改 task.json，不改目录名（避免引用路径漂移）。"""
    res = api.create_task(workdir=workdir, title="旧标题")
    task_id = res["data"]["id"]
    task_dir = res["data"]["task_dir"]
    assert Path(task_dir).name == "T001_旧标题"

    res = api.update_task(
        workdir=workdir, task_id=task_id, title="新标题", description="新描述"
    )
    assert res["success"] is True
    assert res["data"]["title"] == "新标题"
    assert res["data"]["description"] == "新描述"
    # 目录名不变
    assert Path(task_dir).exists()
    assert Path(task_dir).name == "T001_旧标题"
    # 磁盘上的 task.json 已更新
    on_disk = _read_task_json(task_dir)
    assert on_disk["title"] == "新标题"


def test_update_task_not_found(api, workdir):
    """更新不存在的任务报错。"""
    res = api.update_task(workdir=workdir, task_id="T999", title="x")
    assert res["success"] is False
    assert "不存在" in res["error"]


def test_set_status(api, workdir):
    """状态流转与无效状态报错。"""
    res = api.create_task(workdir=workdir, title="任务")
    task_id = res["data"]["id"]
    for status in ["running", "completed", "abandoned", "pending"]:
        res = api.set_status(workdir=workdir, task_id=task_id, status=status)
        assert res["success"] is True
        assert res["data"]["status"] == status
    # 无效状态
    res = api.set_status(workdir=workdir, task_id=task_id, status="failed")
    assert res["success"] is False
    assert "无效状态" in res["error"]


def test_add_note(api, workdir):
    """追加带时间戳的 note。"""
    res = api.create_task(workdir=workdir, title="任务")
    task_id = res["data"]["id"]
    res = api.add_note(workdir=workdir, task_id=task_id, content="关键信息A")
    assert res["success"] is True
    assert len(res["data"]["notes"]) == 1
    assert res["data"]["notes"][0]["content"] == "关键信息A"
    assert res["data"]["notes"][0]["time"]
    # 追加第二条
    res = api.add_note(workdir=workdir, task_id=task_id, content="关键信息B")
    assert len(res["data"]["notes"]) == 2
    assert [n["content"] for n in res["data"]["notes"]] == ["关键信息A", "关键信息B"]
    # 空内容报错
    res = api.add_note(workdir=workdir, task_id=task_id, content="   ")
    assert res["success"] is False


def test_list_tasks_sorted(api, workdir):
    """list_tasks 扫描发现任务并按 id 升序。"""
    for title in ["任务B", "任务A", "任务C"]:
        api.create_task(workdir=workdir, title=title)
    res = api.list_tasks(workdir=workdir)
    assert res["success"] is True
    assert res["count"] == 3
    assert [t["id"] for t in res["data"]] == ["T001", "T002", "T003"]


def test_list_tasks_empty(api, workdir):
    """无任务时返回空列表。"""
    res = api.list_tasks(workdir=workdir)
    assert res["success"] is True
    assert res["count"] == 0
    assert res["data"] == []


def test_get_task(api, workdir):
    """按 id 查找任务。"""
    api.create_task(workdir=workdir, title="任务A")
    res = api.get_task(workdir=workdir, task_id="T001")
    assert res["success"] is True
    assert res["data"]["id"] == "T001"
    # 不存在
    res = api.get_task(workdir=workdir, task_id="T999")
    assert res["success"] is False


def test_tags_normalization(api, workdir):
    """标签规范化：字符串/列表/去重。"""
    res = api.create_task(workdir=workdir, title="任务", tags="a, b, a")
    assert res["data"]["tags"] == ["a", "b"]
    res = api.update_task(
        workdir=workdir, task_id="T001", tags=["x", "y", "x"]
    )
    assert res["data"]["tags"] == ["x", "y"]


def test_concurrent_tasks_independent(api, workdir):
    """多任务独立目录，互不干扰。"""
    res1 = api.create_task(workdir=workdir, title="任务一")
    res2 = api.create_task(workdir=workdir, title="任务二")
    # 两个任务目录独立
    assert res1["data"]["task_dir"] != res2["data"]["task_dir"]
    # 修改任务一不影响任务二
    api.set_status(workdir=workdir, task_id="T001", status="completed")
    res = api.get_task(workdir=workdir, task_id="T002")
    assert res["data"]["status"] == "pending"


def test_public_functions_whitelist(api):
    """PUBLIC_FUNCTIONS 白名单包含全部对外函数。"""
    whitelist = set(api.PUBLIC_FUNCTIONS)
    assert {
        "create_task",
        "update_task",
        "set_status",
        "add_note",
        "list_tasks",
        "get_task",
    } == whitelist
