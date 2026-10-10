"""
AutoWorker 待办事项（TODO）管理工具（Agent 侧）。

与内置 task_list_manager 的区别：本工具只维护「待办清单」本身（与前端任务面板
同源、跨会话持久化），不拆解任务、不驱动子 Agent 执行；task_list_manager 负责把
复杂任务拆成子任务并调度执行。

用途:
- 让任意 Agent 管理待办事项：查看待办列表/详情、更新待办信息、
  标记状态（pending/running/completed/abandoned）、写备注（notes）。
- Agent 通常以任务子目录为 working_dir 启动，因此默认定位到「当前任务」
  （即 working_dir 下的 .jarvis/autoworker/task.json）；也可显式传入 workdir/task_id
  操作其他任务（如创建子任务）。

参数:
- action (str): 动作，可选 create_task / update_task / set_status / add_note /
  list_tasks / get_task。
- workdir (str, 可选): 后端工作目录（任务子目录的父目录）。默认由当前工作目录推断。
- task_id (str, 可选): 任务 ID（如 T001）。默认取当前任务。
- title / description / tags / due_date / status / content: 各动作对应字段。

返回:
- success (bool)
- stdout (str): JSON 文本，包含操作结果
- stderr (str)

说明:
- 本工具直接复用插件私有功能层 plugin/api.py 的逻辑，保证与前端面板行为一致。
- 任务数据持久化在 <workdir>/<ID>_<标题>/.jarvis/autoworker/task.json。
"""

import importlib.util
import json
import os
import sys
from typing import Any
from typing import Dict
from typing import Optional

_TASK_REL_PATH = os.path.join(".jarvis", "autoworker", "task.json")

# 支持的 action 集合（与 parameters.enum 保持一致）
_KNOWN_ACTIONS = {
    "create_task",
    "update_task",
    "set_status",
    "add_note",
    "list_tasks",
    "get_task",
}


def _load_api():
    """用 importlib 按路径加载插件私有功能层 plugin/api.py。

    plugin/ 不在 sys.path，故按文件路径加载；模块名固定以便复用缓存。
    """
    # tools/task_manager.py -> 插件根目录 -> plugin/api.py
    plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    api_path = os.path.join(plugin_root, "plugin", "api.py")
    if not os.path.isfile(api_path):
        raise FileNotFoundError(f"未找到插件私有功能层: {api_path}")
    mod_name = "autoworker_plugin_api"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, api_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {api_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _read_current_task_id(cwd: str) -> Optional[str]:
    """从当前工作目录下的 task.json 读取当前任务 ID；不存在返回 None。"""
    tf = os.path.join(cwd, _TASK_REL_PATH)
    if not os.path.isfile(tf):
        return None
    try:
        with open(tf, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            tid = str(data.get("id") or "").strip()
            return tid or None
    except Exception:
        return None
    return None


def _infer_workdir(cwd: str) -> Optional[str]:
    """由当前工作目录推断后端工作目录。

    Agent 以任务子目录为 working_dir 启动时，cwd 形如 <workdir>/<ID>_<标题>，
    其父目录即 workdir。若 cwd 下直接存在 .jarvis/autoworker/task.json，则父目录为 workdir。
    """
    if os.path.isfile(os.path.join(cwd, _TASK_REL_PATH)):
        return os.path.dirname(cwd)
    return None


class TaskManagerTool:
    # 文件名必须与工具名一致，便于注册表自动加载
    name = "task_manager"
    description = (
        "待办事项（TODO）管理：维护后端工作目录下持久化的待办清单，与前端「任务」"
        "面板同源。可创建/编辑待办、标记状态（pending/running/completed/abandoned）、"
        "写备注（notes）、按需查看列表或详情。适合记录「要做什么、做到哪了」这类跨会话"
        "留存的事项。默认作用于当前待办（working_dir 所在任务的 task.json），也可通过 "
        "workdir/task_id 操作其他待办。"
        "注意：本工具只管理待办清单本身，不拆解/不执行任务；若要把复杂任务拆成子任务"
        "并驱动子 Agent 执行，请用 task_list_manager。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "create_task",
                    "update_task",
                    "set_status",
                    "add_note",
                    "list_tasks",
                    "get_task",
                ],
                "description": "要执行的动作",
            },
            "workdir": {
                "type": "string",
                "description": "后端工作目录（任务子目录的父目录）。默认由当前工作目录推断。",
            },
            "task_id": {
                "type": "string",
                "description": "任务 ID（如 T001）。默认取当前任务。",
            },
            "title": {"type": "string", "description": "任务标题（create_task/update_task）"},
            "description": {
                "type": "string",
                "description": "任务描述（create_task/update_task）",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "任务标签（create_task/update_task）",
            },
            "due_date": {
                "type": "string",
                "description": "截止时间（create_task/update_task），如 2026-10-20",
            },
            "status": {
                "type": "string",
                "enum": ["pending", "running", "completed", "abandoned"],
                "description": "任务状态（set_status）",
            },
            "content": {
                "type": "string",
                "description": "关键信息内容（add_note）",
            },
        },
        "required": ["action"],
    }

    @staticmethod
    def check() -> bool:
        """工具始终可用（纯文件操作，无外部依赖）。"""
        return True

    def _resolve_context(
        self, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """解析 workdir 与 task_id：优先显式参数，否则由当前工作目录推断。

        返回 {"workdir": str, "task_id": str, "error": str}。
        """
        cwd = os.getcwd()
        workdir = args.get("workdir")
        workdir = str(workdir).strip() if workdir else ""
        if not workdir:
            inferred = _infer_workdir(cwd)
            if not inferred:
                return {
                    "workdir": "",
                    "task_id": "",
                    "error": (
                        "无法推断后端工作目录：当前目录不是任务子目录，"
                        "请显式提供 workdir 参数"
                    ),
                }
            workdir = inferred

        task_id = args.get("task_id")
        task_id = str(task_id).strip() if task_id else ""
        if not task_id:
            task_id = _read_current_task_id(cwd) or ""

        return {"workdir": workdir, "task_id": task_id, "error": ""}

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            action = str(args.get("action") or "").strip()
            if not action:
                return self._err("参数错误：action 不能为空")
            if action not in _KNOWN_ACTIONS:
                return self._err(f"未知 action: {action}")

            api = _load_api()

            if action == "list_tasks":
                workdir = args.get("workdir")
                workdir = str(workdir).strip() if workdir else ""
                if not workdir:
                    ctx = self._resolve_context(args)
                    if ctx["error"]:
                        return self._err(ctx["error"])
                    workdir = ctx["workdir"]
                result = api.list_tasks(workdir=workdir)
                return self._ok(result)

            if action == "create_task":
                ctx = self._resolve_context(args)
                if ctx["error"]:
                    return self._err(ctx["error"])
                result = api.create_task(
                    workdir=ctx["workdir"],
                    title=args.get("title"),
                    description=args.get("description", ""),
                    tags=args.get("tags"),
                    due_date=args.get("due_date"),
                )
                return self._ok(result)

            # 其余动作需要 task_id
            ctx = self._resolve_context(args)
            if ctx["error"]:
                return self._err(ctx["error"])
            if not ctx["task_id"]:
                return self._err(
                    "无法确定任务 ID：当前目录不是任务子目录，请显式提供 task_id"
                )

            if action == "get_task":
                result = api.get_task(
                    workdir=ctx["workdir"], task_id=ctx["task_id"]
                )
            elif action == "update_task":
                result = api.update_task(
                    workdir=ctx["workdir"],
                    task_id=ctx["task_id"],
                    title=args.get("title"),
                    description=args.get("description"),
                    tags=args.get("tags"),
                    due_date=args.get("due_date"),
                )
            elif action == "set_status":
                result = api.set_status(
                    workdir=ctx["workdir"],
                    task_id=ctx["task_id"],
                    status=args.get("status"),
                )
            elif action == "add_note":
                result = api.add_note(
                    workdir=ctx["workdir"],
                    task_id=ctx["task_id"],
                    content=args.get("content"),
                )
            else:
                return self._err(f"未知 action: {action}")

            return self._ok(result)
        except Exception as e:
            return self._err(f"task_manager 执行异常: {e}")

    @staticmethod
    def _ok(result: Dict[str, Any]) -> Dict[str, Any]:
        """把 api 返回统一包装成工具返回格式。"""
        success = bool(result.get("success"))
        return {
            "success": success,
            "stdout": json.dumps(result, ensure_ascii=False, indent=2),
            "stderr": "" if success else str(result.get("error") or "操作失败"),
        }

    @staticmethod
    def _err(message: str) -> Dict[str, Any]:
        return {"success": False, "stdout": "", "stderr": message}
