"""
AutoWorker 插件私有功能层（运行在 gateway，供前端代理调用；不暴露给 Agent）。

提供任务 CRUD 纯函数：
- create_task / update_task / set_status / add_note：写操作
- list_tasks / get_task：读操作

任务持久化到后端工作目录下每个任务子目录的 `.jarvis/autoworker/task.json`：
    <workdir>/<ID>_<标题>/.jarvis/autoworker/task.json
- 目录名固定用创建时的 `ID_标题`，标题修改只更新 task.json，不改目录名（避免引用路径漂移）。
- ID 自动递增（T001、T002…）。
- 状态：pending / running / completed / abandoned（无失败/阻塞）。

每个函数返回 dict：{"success": bool, "data": .../ "message": .../ "error": ...}。
本模块不声明在 tool_load_dirs，因此不会被 ToolRegistry 加载，Agent 不可见；
gateway 通过插件功能代理端点动态加载本模块并调用。
"""
import json
import os
import re
from datetime import datetime
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

# 合法任务状态（无失败/阻塞）
VALID_STATUS = {"pending", "running", "completed", "abandoned"}
# 状态展示名
STATUS_LABELS = {
    "pending": "待执行",
    "running": "执行中",
    "completed": "已完成",
    "abandoned": "已放弃",
}
# 任务文件相对任务子目录的路径
_TASK_REL_PATH = os.path.join(".jarvis", "autoworker", "task.json")


def _now() -> str:
    """当前本地时间，ISO 8601 格式（含时区，秒精度）。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _clean_dir_name(title: str) -> str:
    """清理标题中的非法字符，用于目录命名（不用于 task.json 的 title 字段）。"""
    cleaned = re.sub(r'[\\/:*?"<>|\r\n]+', "_", str(title or "").strip())
    return cleaned or "未命名"


def _task_file_path(task_dir: str) -> str:
    """任务子目录 -> task.json 绝对路径。"""
    return os.path.join(task_dir, _TASK_REL_PATH)


def _load_task(task_dir: str) -> Optional[Dict[str, Any]]:
    """读取任务子目录下的 task.json；不存在或解析失败返回 None。
    返回的任务 dict 附带内部字段 task_dir（任务子目录绝对路径）。
    """
    tf = _task_file_path(task_dir)
    if not os.path.isfile(tf):
        return None
    try:
        with open(tf, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        data["task_dir"] = task_dir
        return data
    except Exception:
        return None


def _scan_tasks(workdir: str) -> List[Dict[str, Any]]:
    """扫描 <workdir>/*/.jarvis/autoworker/task.json，返回任务列表（按 id 数值升序）。"""
    tasks: List[Dict[str, Any]] = []
    if not os.path.isdir(workdir):
        return tasks
    try:
        entries = sorted(os.listdir(workdir))
    except Exception:
        return tasks
    for name in entries:
        task_dir = os.path.join(workdir, name)
        if not os.path.isdir(task_dir):
            continue
        task = _load_task(task_dir)
        if task:
            tasks.append(task)

    def _sort_key(t: Dict[str, Any]) -> int:
        m = re.match(r"^T(\d+)$", str(t.get("id", "")))
        return int(m.group(1)) if m else 0

    tasks.sort(key=_sort_key)
    return tasks


def _next_task_id(workdir: str) -> str:
    """生成下一个递增任务 ID（T001、T002…）。"""
    max_num = 0
    for t in _scan_tasks(workdir):
        m = re.match(r"^T(\d+)$", str(t.get("id", "")))
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"T{max_num + 1:03d}"


def _find_task(workdir: str, task_id: str) -> Optional[Dict[str, Any]]:
    """按任务 ID 查找任务；未找到返回 None。"""
    for t in _scan_tasks(workdir):
        if str(t.get("id", "")) == task_id:
            return t
    return None


def _require_workdir(workdir: Any) -> tuple:
    """校验并规范化后端工作目录。返回 (workdir, error)；workdir 为空/不存在时 error 非空。"""
    workdir = (workdir or "").strip()
    if not workdir:
        return "", "未指定后端工作目录"
    workdir = os.path.abspath(os.path.expanduser(workdir))
    if not os.path.isdir(workdir):
        return "", f"后端工作目录不存在: {workdir}"
    return workdir, ""


def _require_task_id(task_id: Any) -> tuple:
    """校验任务 ID。返回 (task_id, error)。"""
    task_id = str(task_id or "").strip()
    if not task_id:
        return "", "未指定任务 ID"
    return task_id, ""


def _write_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """把任务 dict 写回其 task.json（剔除内部字段 task_dir）。"""
    task_dir = task.get("task_dir")
    if not task_dir:
        return {"success": False, "error": "任务目录缺失"}
    tf = _task_file_path(task_dir)
    try:
        os.makedirs(os.path.dirname(tf), exist_ok=True)
        data = {k: v for k, v in task.items() if k != "task_dir"}
        with open(tf, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": f"写入任务文件失败: {e}"}


def _normalize_tags(tags: Any) -> List[str]:
    """规范化标签：接受 list 或逗号分隔字符串，返回去重后的字符串列表。"""
    if tags is None:
        return []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    elif isinstance(tags, (list, tuple)):
        tags = [str(t).strip() for t in tags if str(t).strip()]
    else:
        tags = []
    seen = set()
    result = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def _normalize_due_date(due_date: Any) -> str:
    """规范化截止时间：接受空/None（返回空串）或字符串（裁剪）。"""
    if due_date is None:
        return ""
    return str(due_date).strip()


def create_task(
    workdir: Optional[str] = None,
    title: Optional[str] = None,
    description: str = "",
    tags: Any = None,
    due_date: Any = None,
) -> Dict[str, Any]:
    """创建任务：生成递增 ID，创建 <workdir>/<ID>_<标题> 子目录与 task.json。
    目录名固定用创建时的 ID_标题；返回 data 含 id/task_dir 等。
    """
    workdir, err = _require_workdir(workdir)
    if err:
        return {"success": False, "error": err}
    title = (title or "").strip()
    if not title:
        return {"success": False, "error": "请提供任务标题"}
    task_id = _next_task_id(workdir)
    dir_name = f"{task_id}_{_clean_dir_name(title)}"
    task_dir = os.path.join(workdir, dir_name)
    if os.path.exists(task_dir):
        return {"success": False, "error": f"任务目录已存在: {task_dir}"}
    now = _now()
    task: Dict[str, Any] = {
        "id": task_id,
        "title": title,
        "description": str(description or ""),
        "tags": _normalize_tags(tags),
        "due_date": _normalize_due_date(due_date),
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "notes": [],
        "task_dir": task_dir,
    }
    result = _write_task(task)
    if not result["success"]:
        return result
    # task_dir 是内部字段（不落盘），但对外返回时补上：前端需据此设置 Agent 工作目录
    data = dict(result["data"])
    data["task_dir"] = task_dir
    return {
        "success": True,
        "data": data,
        "message": f"任务 {task_id} 已创建",
    }


def update_task(
    workdir: Optional[str] = None,
    task_id: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    tags: Any = None,
    due_date: Any = None,
) -> Dict[str, Any]:
    """更新任务详情（标题/描述/标签/截止时间）。
    标题修改只更新 task.json，不改目录名（避免引用路径漂移）。
    """
    workdir, err = _require_workdir(workdir)
    if err:
        return {"success": False, "error": err}
    task_id, err = _require_task_id(task_id)
    if err:
        return {"success": False, "error": err}
    task = _find_task(workdir, task_id)
    if not task:
        return {"success": False, "error": f"任务不存在: {task_id}"}
    if title is not None:
        title = str(title).strip()
        if not title:
            return {"success": False, "error": "任务标题不能为空"}
        task["title"] = title
    if description is not None:
        task["description"] = str(description)
    if tags is not None:
        task["tags"] = _normalize_tags(tags)
    if due_date is not None:
        task["due_date"] = _normalize_due_date(due_date)
    task["updated_at"] = _now()
    result = _write_task(task)
    if not result["success"]:
        return result
    data = dict(result["data"])
    data["task_dir"] = task["task_dir"]
    return {
        "success": True,
        "data": data,
        "message": f"任务 {task_id} 已更新",
    }


def set_status(
    workdir: Optional[str] = None,
    task_id: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """标记任务状态（pending/running/completed/abandoned）。"""
    workdir, err = _require_workdir(workdir)
    if err:
        return {"success": False, "error": err}
    task_id, err = _require_task_id(task_id)
    if err:
        return {"success": False, "error": err}
    status = str(status or "").strip()
    if status not in VALID_STATUS:
        return {
            "success": False,
            "error": f"无效状态: {status}（可选: {', '.join(sorted(VALID_STATUS))}）",
        }
    task = _find_task(workdir, task_id)
    if not task:
        return {"success": False, "error": f"任务不存在: {task_id}"}
    task["status"] = status
    task["updated_at"] = _now()
    result = _write_task(task)
    if not result["success"]:
        return result
    data = dict(result["data"])
    data["task_dir"] = task["task_dir"]
    return {
        "success": True,
        "data": data,
        "message": f"任务 {task_id} 状态已更新为 {STATUS_LABELS.get(status, status)}",
    }


def add_note(
    workdir: Optional[str] = None,
    task_id: Optional[str] = None,
    content: Optional[str] = None,
) -> Dict[str, Any]:
    """保存关键信息（notes），带时间戳，供后续生成任务报告。"""
    workdir, err = _require_workdir(workdir)
    if err:
        return {"success": False, "error": err}
    task_id, err = _require_task_id(task_id)
    if err:
        return {"success": False, "error": err}
    content = (content or "").strip()
    if not content:
        return {"success": False, "error": "请提供 note 内容"}
    task = _find_task(workdir, task_id)
    if not task:
        return {"success": False, "error": f"任务不存在: {task_id}"}
    notes = task.get("notes") or []
    if not isinstance(notes, list):
        notes = []
    notes.append({"time": _now(), "content": content})
    task["notes"] = notes
    task["updated_at"] = _now()
    result = _write_task(task)
    if not result["success"]:
        return result
    data = dict(result["data"])
    data["task_dir"] = task["task_dir"]
    return {
        "success": True,
        "data": data,
        "message": f"已为任务 {task_id} 保存关键信息",
    }


def list_tasks(workdir: Optional[str] = None) -> Dict[str, Any]:
    """列出后端工作目录下的全部任务（按 id 升序）。"""
    workdir, err = _require_workdir(workdir)
    if err:
        return {"success": False, "error": err}
    tasks = _scan_tasks(workdir)
    return {
        "success": True,
        "data": tasks,
        "workdir": workdir,
        "count": len(tasks),
    }


def get_task(
    workdir: Optional[str] = None, task_id: Optional[str] = None
) -> Dict[str, Any]:
    """查看单个任务详情。"""
    workdir, err = _require_workdir(workdir)
    if err:
        return {"success": False, "error": err}
    task_id, err = _require_task_id(task_id)
    if err:
        return {"success": False, "error": err}
    task = _find_task(workdir, task_id)
    if not task:
        return {"success": False, "error": f"任务不存在: {task_id}"}
    return {"success": True, "data": task}


# 可被 gateway 代理调用的函数白名单（防止任意函数被调用）
PUBLIC_FUNCTIONS: List[str] = [
    "create_task",
    "update_task",
    "set_status",
    "add_note",
    "list_tasks",
    "get_task",
]
