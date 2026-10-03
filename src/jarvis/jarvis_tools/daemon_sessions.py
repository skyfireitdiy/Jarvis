# -*- coding: utf-8 -*-
"""本机守护进程工具 - 列出当前在线的 jarvis-daemon 会话。

与 browser_ext 的区别：browser_ext 驱动的是用户浏览器扩展，本工具驱动的是
用户机器上常驻的 jarvis-daemon 进程（可执行本机文件系统、进程、系统等操作）。

依赖用户在本机安装并启动 jarvis-daemon，且已通过网页把网关地址与 Token 推送给它。

本工具是 daemon 三件套之一（sessions / capabilities / call），采用「动态能力 + call」
模型：能力由守护进程自身动态注册并上报，网关透传。本工具只负责列出会话。
"""

import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

import jarvis.jarvis_utils.globals as jglobals

logger = logging.getLogger(__name__)


class DaemonSessionsTool:
    """本机守护进程工具 - 列出当前在线的 jarvis-daemon 会话。

    返回 session_id 列表，每个会话还包含该后台服务所在机器的系统信息
    （system_info：hostname/os_name/os_version/arch/cpu_count/cpu_model/
    mem_total_kb/mem_available_kb/uptime_sec/user/home 等），可据此判断该
    机器的环境与可调用的能力。

    典型流程：先本工具拿到 session_id，再 daemon_capabilities 查看该会话
    支持哪些能力及其参数，最后 daemon_call 按能力名调用。
    """

    name = "daemon_sessions"

    @staticmethod
    def check() -> bool:
        """检查工具是否可用，仅当 Gateway 存在时启用（通过 agent_id 是否设置判断）。"""
        return jglobals.agent_id is not None

    description = """列出当前在线的守护进程（jarvis-daemon）会话。
返回 session_id 列表，每个会话还包含该后台服务所在机器的系统信息
（system_info：hostname/os_name/os_version/arch/cpu_count/cpu_model/
mem_total_kb/mem_available_kb/uptime_sec/user/home 等），可据此判断该机器的环境与可调用的能力。
**应先调用本工具获取 session_id**，再用 daemon_capabilities 看能力、daemon_call 调用。
若用户未安装或未启动守护进程，本工具会返回空列表提示。"""

    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
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
            return "list_sessions 执行成功"
        if isinstance(data, str):
            return data
        try:
            return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception:
            return str(data)

    def execute(self, **kwargs) -> Dict[str, Any]:
        """列出当前在线的守护进程会话。

        返回:
            Dict[str, Any]: {"success": bool, "stdout": str, "stderr": str}
        """
        err = self._get_master_url("list_sessions")
        if err is not None:
            return err

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
            "stdout": self._format_result(sessions),
            "stderr": "",
        }
