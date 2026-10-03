# -*- coding: utf-8 -*-
"""浏览器扩展工具 - 列出指定浏览器扩展会话的能力清单。

与 jarvis-browser(jb) 的区别：jb 在服务端用 Playwright 启动独立浏览器，
本工具驱动的是**用户自己浏览器**中已登录的真实标签页。

依赖用户浏览器安装 Jarvis Browser Bridge 扩展并连接到网关。

本工具是 browser_ext 三件套之一（sessions / capabilities / call），
采用「动态能力 + call」模型：扩展侧维护能力清单（command_router.js 的
routes + CAPABILITIES）并动态上报，网关透传。本工具只负责列出指定会话的能力。
"""

import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

import jarvis.jarvis_utils.globals as jglobals

logger = logging.getLogger(__name__)


class BrowserExtCapabilitiesTool:
    """浏览器扩展工具 - 列出指定浏览器扩展会话的能力清单。

    返回该会话上报的能力（含 name/description/parameters/platform）。

    典型流程：先 browser_ext_sessions 拿到 session_id，再本工具查看该会话
    支持哪些能力及其参数，最后 browser_ext_call 按能力名调用。
    """

    name = "browser_ext_capabilities"

    @staticmethod
    def check() -> bool:
        """检查工具是否可用，仅当 Gateway 存在时启用（通过 agent_id 是否设置判断）。"""
        return jglobals.agent_id is not None

    description = """列出指定浏览器扩展会话上可用的能力清单（含 name/description/parameters/platform）。
需 session_id（先用 browser_ext_sessions 获取）。
能力清单由扩展动态上报决定，不同版本/站点可能不同，调用 browser_ext_call 前务必先本工具确认能力名与参数，不要凭猜测调用。"""

    parameters = {
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "浏览器扩展会话 ID（必填）。应先调用 browser_ext_sessions 获取",
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

    def execute(self, session_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """列出指定浏览器扩展会话的能力清单。

        参数:
            session_id: 浏览器扩展会话 ID（必填）

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
                "stderr": "session_id is required. 请先调用 browser_ext_sessions 获取。",
            }

        result = self._request_gateway(
            "GET",
            "/api/browser-ext/sessions",
            error_prefix="Failed to list browser sessions",
        )
        if not result.get("success"):
            return {
                "success": False,
                "stdout": "",
                "stderr": result.get("error") or "unknown error",
            }
        data = result.get("data") or {}
        sessions = data.get("sessions") or []
        target = None
        for s in sessions:
            if str(s.get("session_id") or "") == session_id:
                target = s
                break
        if target is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"browser session not found: {session_id}",
            }
        capabilities = target.get("capabilities") or []
        if not capabilities:
            return {
                "success": True,
                "stdout": "该浏览器扩展会话当前未上报任何能力。",
                "stderr": "",
            }
        return {
            "success": True,
            "stdout": self._format_result(capabilities),
            "stderr": "",
        }
