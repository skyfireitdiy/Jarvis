# -*- coding: utf-8 -*-
"""本机守护进程工具 - 通过网关调用用户机器上 jarvis-daemon 的能力。

与 browser_ext 的区别：browser_ext 驱动的是用户浏览器扩展，本工具驱动的是
用户机器上常驻的 jarvis-daemon 进程（可执行本机文件系统、进程、系统等操作）。

依赖用户在本机安装并启动 jarvis-daemon，且已通过网页把网关地址与 Token 推送给它。
"""

import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

import jarvis.jarvis_utils.globals as jglobals

logger = logging.getLogger(__name__)


class DaemonTool:
    """本机守护进程工具，调用用户机器上 jarvis-daemon 注册的能力。

    支持的操作（action）：
    1. **list_sessions**: 列出当前在线的守护进程会话（返回 session_id 列表）
    2. **list_capabilities**: 列出指定会话上可用的能力清单（含名称/说明/参数）
    3. **call**: 按能力名调用指定会话上的能力

    典型流程：先 list_sessions 拿到 session_id，再 list_capabilities 查看该会话
    支持哪些能力及其参数，最后用 call 按能力名调用。

    **重要提示**：
    - 每次调用只能执行一种操作
    - 能力清单是**动态的**：由守护进程自身注册决定，不同机器/不同版本可能不同，
      因此调用前应先 list_capabilities 确认能力名与参数，不要凭猜测调用
    - 操作的是用户真实机器，请谨慎执行可能造成不可逆后果的动作
    - **多用户隔离**：只能访问当前用户自己的守护进程会话（网关按 Token 对应的
      user_id 校验会话归属），跨用户会话会被网关拒绝
    """

    name = "daemon"

    @staticmethod
    def check() -> bool:
        """检查工具是否可用，仅当 Gateway 存在时启用（通过 agent_id 是否设置判断）。"""
        return jglobals.agent_id is not None

    description = """调用用户本机 jarvis-daemon 守护进程注册的能力（在用户自己机器上执行操作）。
与 execute_script 等工具不同：本工具执行的是**用户本机常驻守护进程**上的能力，
不依赖当前 Agent 所在环境，可操作用户自己的机器。
每次调用只能执行一个 action：
- list_sessions: 列出当前在线的守护进程会话（返回 session_id 列表）。**应先调用此操作获取 session_id**
- list_capabilities: 列出指定会话上可用的能力清单（含 name/description/parameters/platform）。需 session_id
- call: 按能力名调用指定会话上的能力。需 session_id、name；可选 params（能力参数对象）、timeout

典型流程：list_sessions 拿 session_id → list_capabilities 看有哪些能力、各自要什么参数
→ call 按 name + params 调用。

**注意**：能力清单由守护进程动态注册决定，不同机器/版本可能不同，调用前务必先
list_capabilities 确认能力名与参数，不要凭猜测调用。
若用户未安装或未启动守护进程，list_sessions 会返回空列表。"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "list_sessions",
                    "list_capabilities",
                    "call",
                ],
                "description": "操作类型",
            },
            "session_id": {
                "type": "string",
                "description": "守护进程会话 ID（除 list_sessions 外必填）。"
                "应先调用 list_sessions 获取",
            },
            "name": {
                "type": "string",
                "description": "能力名称（call 必填），如 fs.read。"
                "应先调用 list_capabilities 获取可用能力名",
            },
            "params": {
                "type": "object",
                "description": "能力参数对象（call 可选），键值由目标能力的 parameters 描述决定",
            },
            "timeout": {
                "type": "number",
                "description": "等待结果的超时秒数（默认 30）",
            },
        },
        "required": ["action"],
    }

    def _get_master_url(self, action_name: str = "") -> Optional[Dict[str, Any]]:
        """获取 master_url，未设置时返回错误字典。"""
        if not jglobals.master_url:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"master_url is not set, cannot {action_name}. "
                "Please ensure the agent is started with --master-url option.",
            }
        return None

    def _build_auth_headers(self) -> Dict[str, str]:
        """构建带认证信息的请求头。"""
        headers: Dict[str, str] = {}
        auth_token = os.environ.get("JARVIS_AUTH_TOKEN")
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        return headers

    def _request_gateway(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
        error_prefix: str = "Request failed",
        timeout: float = 20.0,
    ) -> Dict[str, Any]:
        """向 Gateway 发送 HTTP 请求。"""
        url = f"{jglobals.master_url}{path}"
        headers = self._build_auth_headers()
        try:
            with httpx.Client(timeout=timeout) as client:
                if method.upper() == "POST":
                    response = client.post(url, json=json_data, headers=headers)
                elif method.upper() == "DELETE":
                    response = client.delete(url, headers=headers, params=params)
                else:
                    response = client.get(url, headers=headers, params=params)
            if response.status_code == 200:
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "data": response.json(),
                }
            return {
                "success": False,
                "status_code": response.status_code,
                "data": None,
                "error": f"{error_prefix}: HTTP {response.status_code} - {response.text}",
            }
        except httpx.ConnectError:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": f"Cannot connect to gateway at {jglobals.master_url}. "
                "Please ensure the gateway is running.",
            }
        except Exception as e:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": f"{error_prefix}: {str(e)}",
            }

    @staticmethod
    def _format_result(action: str, data: Any) -> str:
        """把网关返回的数据格式化为可读文本。"""
        if data is None:
            return f"{action} 执行成功"
        if isinstance(data, str):
            return data
        try:
            return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception:
            return str(data)

    @staticmethod
    def _format_error(error: Any) -> str:
        """把网关返回的 error 字段（可能是 dict 或 str）格式化为文本。"""
        if error is None:
            return "unknown error"
        if isinstance(error, str):
            return error
        try:
            return json.dumps(error, ensure_ascii=False)
        except Exception:
            return str(error)

    def execute(
        self,
        action: str,
        session_id: Optional[str] = None,
        name: str = "",
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
        **kwargs,
    ) -> Dict[str, Any]:
        """执行守护进程能力操作。

        参数:
            action: 操作类型（list_sessions/list_capabilities/call）
            session_id: 守护进程会话 ID（除 list_sessions 外必填）
            name: 能力名称（call 必填）
            params: 能力参数对象（call 可选）
            timeout: 等待结果的超时秒数
            **kwargs: 其他参数

        返回:
            Dict[str, Any]: {"success": bool, "stdout": str, "stderr": str}
        """
        # 兼容 v1.0 协议：registry 可能将整个参数字典作为 action 传入
        if isinstance(action, dict):
            args = action
            action = args.get("action", "")
            session_id = args.get("session_id")
            name = args.get("name", "")
            params = args.get("params")
            timeout = args.get("timeout", 30.0)

        action = str(action or "").strip()
        if not action:
            return {
                "success": False,
                "stdout": "",
                "stderr": "action is required",
            }

        known_actions = {"list_sessions", "list_capabilities", "call"}
        if action not in known_actions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"unknown action: {action}",
            }

        err = self._get_master_url(f"execute {action}")
        if err is not None:
            return err

        try:
            timeout = float(timeout)
        except (TypeError, ValueError):
            timeout = 30.0

        # ---------------- list_sessions ----------------
        if action == "list_sessions":
            result = self._request_gateway(
                "GET",
                "/api/daemon/sessions",
                error_prefix="Failed to list daemon sessions",
            )
            if not result.get("success"):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": result.get("error") or "unknown error",
                }
            data = result.get("data") or {}
            sessions = data.get("sessions") or []
            if not sessions:
                return {
                    "success": True,
                    "stdout": "当前没有在线的守护进程会话。"
                    "请确认用户已在本机安装并启动 jarvis-daemon，"
                    "且已通过网页完成认证。",
                    "stderr": "",
                }
            return {
                "success": True,
                "stdout": self._format_result("list_sessions", sessions),
                "stderr": "",
            }

        # ---------------- 其余操作均需 session_id ----------------
        session_id = str(session_id or "").strip()
        if not session_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"session_id is required for action '{action}'. "
                "请先调用 list_sessions 获取。",
            }

        # ---------------- list_capabilities ----------------
        if action == "list_capabilities":
            result = self._request_gateway(
                "POST",
                "/api/daemon/capability/list",
                json_data={"session_id": session_id, "timeout": timeout},
                error_prefix="Failed to list daemon capabilities",
                timeout=timeout + 5.0,
            )
            if not result.get("success"):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": result.get("error") or "unknown error",
                }
            data = result.get("data") or {}
            if not data.get("success"):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": self._format_error(data.get("error")),
                }
            # 网关信封：{"success": true, "result": {"success":..., "capabilities":[...]}}
            payload = data.get("result") or {}
            capabilities = payload.get("capabilities") or []
            if not capabilities:
                return {
                    "success": True,
                    "stdout": "该守护进程当前未注册任何能力。",
                    "stderr": "",
                }
            return {
                "success": True,
                "stdout": self._format_result("list_capabilities", capabilities),
                "stderr": "",
            }

        # ---------------- call ----------------
        name = str(name or "").strip()
        if not name:
            return {
                "success": False,
                "stdout": "",
                "stderr": "name is required for action 'call'. "
                "请先调用 list_capabilities 获取可用能力名。",
            }
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return {
                "success": False,
                "stdout": "",
                "stderr": "params must be an object",
            }
        result = self._request_gateway(
            "POST",
            "/api/daemon/capability/call",
            json_data={
                "session_id": session_id,
                "name": name,
                "params": params,
                "timeout": timeout,
            },
            error_prefix=f"Failed to call {name}",
            timeout=timeout + 5.0,
        )
        if not result.get("success"):
            return {
                "success": False,
                "stdout": "",
                "stderr": result.get("error") or "unknown error",
            }
        data = result.get("data") or {}
        if not data.get("success"):
            return {
                "success": False,
                "stdout": "",
                "stderr": self._format_error(data.get("error")),
            }
        # 网关信封：{"success": true, "result": {"success":..., "data":..., "error":...}}
        payload = data.get("result") or {}
        if not payload.get("success"):
            return {
                "success": False,
                "stdout": "",
                "stderr": self._format_error(payload.get("error"))
                or f"{name} 执行失败",
            }
        return {
            "success": True,
            "stdout": self._format_result(name, payload.get("data")),
            "stderr": "",
        }
