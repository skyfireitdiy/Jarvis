# -*- coding: utf-8 -*-
"""本机守护进程工具 - 列出指定 jarvis-daemon 会话的能力清单。

与 browser_ext 的区别：browser_ext 驱动的是用户浏览器扩展，本工具驱动的是
用户机器上常驻的 jarvis-daemon 进程（可执行本机文件系统、进程、系统等操作）。

依赖用户在本机安装并启动 jarvis-daemon，且已通过网页把网关地址与 Token 推送给它。

本工具是 daemon 三件套之一（sessions / capabilities / call），采用「动态能力 + call」
模型：能力由守护进程自身动态注册并上报，网关透传。本工具只负责列出指定会话的能力。
"""

import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

import jarvis.jarvis_utils.globals as jglobals

logger = logging.getLogger(__name__)


class DaemonCapabilitiesTool:
    """本机守护进程工具 - 列出指定 jarvis-daemon 会话的能力清单。

    返回该会话注册的能力（含 name/description/parameters/platform）。

    典型流程：先 daemon_sessions 拿到 session_id，再本工具查看该会话
    支持哪些能力及其参数，最后 daemon_call 按能力名调用。
    """

    name = "daemon_capabilities"

    @staticmethod
    def check() -> bool:
        """检查工具是否可用，仅当 Gateway 存在时启用（通过 agent_id 是否设置判断）。"""
        return jglobals.agent_id is not None

    description = """列出指定守护进程（jarvis-daemon）会话上可用的能力清单（含 name/description/parameters/platform）。
需 session_id（先用 daemon_sessions 获取）。
能力清单由守护进程动态注册决定，不同机器/版本可能不同，调用 daemon_call 前务必先本工具确认能力名与参数，不要凭猜测调用。"""

    parameters = {
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "守护进程会话 ID（必填）。应先调用 daemon_sessions 获取",
            },
        },
        "required": ["session_id"],
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
    def _format_result(data: Any) -> str:
        """把网关返回的数据格式化为可读文本。"""
        if data is None:
            return "list_capabilities 执行成功"
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

    def execute(self, session_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """列出指定守护进程会话的能力清单。

        参数:
            session_id: 守护进程会话 ID（必填）

        返回:
            Dict[str, Any]: {"success": bool, "stdout": str, "stderr": str}
        """
        err = self._get_master_url("list_capabilities")
        if err is not None:
            return err

        session_id = str(session_id or "").strip()
        if not session_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "session_id is required. 请先调用 daemon_sessions 获取。",
            }

        try:
            timeout = float(kwargs.get("timeout", 30.0))
        except (TypeError, ValueError):
            timeout = 30.0

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
            "stdout": self._format_result(capabilities),
            "stderr": "",
        }
