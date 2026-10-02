"""
Jarvis 前端工具：让 Agent 向用户前端编辑器下发指令（如打开文件/跳转行/选中区域）。

用途:
- 通过 Web Gateway 广播 editor_* 消息，前端据此在用户的 Monaco 工作区执行对应操作；
- 让 Agent 在分析/修改代码时，把用户的编辑器视图引导到相关位置，实现
  Agent 与用户的可视化协作。

参数:
- action (str, 可选): 要执行的前端操作，目前支持:
    - open_file: 打开文件并跳转到目标行/列（可附带选中一段代码）。默认值。
- path (str): 要打开的文件路径（相对 Agent working_dir 或绝对路径）。仅 open_file 需要。
- line (int, 可选): 跳转到的行号，默认 1
- column (int, 可选): 跳转到的列号，默认 1
- select_start (int, 可选): 选中范围起始列（0-based），需与 select_end 同传
- select_end (int, 可选): 选中范围结束列（0-based），需与 select_start 同传
- reveal (bool, 可选): 是否将目标行滚动到视图中央，默认 true

返回:
- success (bool)
- stdout (str)
- stderr (str)
"""

from typing import Any
from typing import Dict

from jarvis.jarvis_gateway.manager import get_current_gateway
from jarvis.jarvis_utils.globals import agent_id as current_agent_id
from jarvis.jarvis_utils.output import PrettyOutput


class JarvisFrontendTool:
    # 文件名必须与工具名一致，便于注册表自动加载
    name = "jarvis_frontend"
    description = (
        "Jarvis 前端工具：向用户前端编辑器下发指令（打开文件/跳转行/选中代码）。"
        "用于把用户的编辑器视图引导到 Agent 正在分析或修改的位置。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["open_file"],
                "description": "要执行的前端操作，目前支持 open_file（打开文件），默认 open_file",
            },
            "path": {
                "type": "string",
                "description": "要打开的文件路径（相对当前 Agent 工作目录，或绝对路径）",
            },
            "line": {
                "type": "integer",
                "description": "跳转到的行号（从 1 开始），默认 1",
            },
            "column": {
                "type": "integer",
                "description": "跳转到的列号（从 1 开始），默认 1",
            },
            "select_start": {
                "type": "integer",
                "description": "选中范围起始列（0-based），需与 select_end 同时提供",
            },
            "select_end": {
                "type": "integer",
                "description": "选中范围结束列（0-based），需与 select_start 同时提供",
            },
            "reveal": {
                "type": "boolean",
                "description": "是否将目标行滚动到视图中央，默认 true",
            },
        },
        "required": [],
    }

    @staticmethod
    def check() -> bool:
        """仅当存在当前 Agent 且 Gateway 支持编辑器指令时启用。"""
        if not current_agent_id:
            return False
        gateway = get_current_gateway()
        return gateway is not None and hasattr(gateway, "publish_editor_command")

    def _execute_open_file(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """open_file：打开文件并跳转到目标行/列（可附带选中一段代码）。"""
        path = args.get("path")
        if not isinstance(path, str) or not path.strip():
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少或无效的 path 参数",
            }

        if not current_agent_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "当前无 Agent 上下文，无法定位工作目录",
            }

        gateway = get_current_gateway()
        if gateway is None or not hasattr(gateway, "publish_editor_command"):
            return {
                "success": False,
                "stdout": "",
                "stderr": "当前 Gateway 不支持编辑器指令（publish_editor_command）",
            }

        payload: Dict[str, Any] = {"path": path.strip()}

        line = args.get("line")
        if line is not None:
            payload["line"] = int(line)
        column = args.get("column")
        if column is not None:
            payload["column"] = int(column)

        select_start = args.get("select_start")
        select_end = args.get("select_end")
        if select_start is not None and select_end is not None:
            payload["select_start"] = int(select_start)
            payload["select_end"] = int(select_end)
        elif select_start is not None or select_end is not None:
            return {
                "success": False,
                "stdout": "",
                "stderr": "select_start 与 select_end 必须同时提供",
            }

        reveal = args.get("reveal")
        if reveal is not None:
            payload["reveal"] = bool(reveal)

        publish = getattr(gateway, "publish_editor_command")
        publish(current_agent_id, "open_file", payload)
        PrettyOutput.auto_print(
            f"[jarvis_frontend] 已广播打开文件: {payload.get('path')}"
        )
        return {
            "success": True,
            "stdout": f"已通知前端编辑器打开文件: {payload.get('path')}",
            "stderr": "",
        }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            action = args.get("action") or "open_file"
            if action == "open_file":
                return self._execute_open_file(args)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"不支持的前端操作: {action}（目前支持 open_file）",
            }
        except Exception as e:
            PrettyOutput.auto_print(f"❌ {str(e)}")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"广播前端指令失败: {str(e)}",
            }
