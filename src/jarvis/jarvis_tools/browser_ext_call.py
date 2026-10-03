# -*- coding: utf-8 -*-
"""浏览器扩展工具 - 按能力名调用指定浏览器扩展会话的能力。

与 jarvis-browser(jb) 的区别：jb 在服务端用 Playwright 启动独立浏览器，
本工具驱动的是**用户自己浏览器**中已登录的真实标签页。

依赖用户浏览器安装 Jarvis Browser Bridge 扩展并连接到网关。

本工具是 browser_ext 三件套之一（sessions / capabilities / call），
采用「动态能力 + call」模型：扩展侧维护能力清单（command_router.js 的
routes + CAPABILITIES）并动态上报，网关透传。本工具只负责按能力名调用。
"""

import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

import jarvis.jarvis_utils.globals as jglobals

logger = logging.getLogger(__name__)


class BrowserExtCallTool:
    """浏览器扩展工具 - 按能力名调用指定浏览器扩展会话的能力。

    典型流程：先 browser_ext_sessions 拿到 session_id，再 browser_ext_capabilities
    查看该会话支持哪些能力及其参数，最后本工具按能力名调用。

    **注意**：能力清单由扩展动态上报决定，不同版本/站点可能不同，
    因此调用前应先 browser_ext_capabilities 确认能力名与参数，不要凭猜测调用。
    """

    name = "browser_ext_call"

    @staticmethod
    def check() -> bool:
        """检查工具是否可用，仅当 Gateway 存在时启用（通过 agent_id 是否设置判断）。"""
        return jglobals.agent_id is not None

    description = """按能力名调用指定浏览器扩展会话上的能力（通过用户安装的浏览器扩展）。
需 session_id、name；可选 params（能力参数对象）、timeout。
能力名与参数应先通过 browser_ext_capabilities 确认，不要凭猜测调用。
典型流程：browser_ext_sessions 拿 session_id → browser_ext_capabilities 看能力 → 本工具调用。"""

    parameters = {
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "浏览器扩展会话 ID（必填）。应先调用 browser_ext_sessions 获取",
            },
            "name": {
                "type": "string",
                "description": "能力名称（必填），如 tab.list、dom.click。"
                "应先调用 browser_ext_capabilities 获取可用能力名",
            },
            "params": {
                "type": "object",
                "description": "能力参数对象（可选），键值由目标能力的 parameters 描述决定",
            },
            "timeout": {
                "type": "number",
                "description": "等待结果的超时秒数（默认 15）",
            },
        },
        "required": ["session_id", "name"],
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
        session_id: Optional[str] = None,
        name: str = "",
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 15.0,
        **kwargs,
    ) -> Dict[str, Any]:
        """按能力名调用指定浏览器扩展会话的能力。

        参数:
            session_id: 浏览器扩展会话 ID（必填）
            name: 能力名称（必填）
            params: 能力参数对象（可选）
            timeout: 等待结果的超时秒数

        返回:
            Dict[str, Any]: {"success": bool, "stdout": str, "stderr": str}
        """
        err = self._get_master_url("call")
        if err is not None:
            return err

        session_id = str(session_id or "").strip()
        if not session_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "session_id is required. 请先调用 browser_ext_sessions 获取。",
            }

        name = str(name or "").strip()
        if not name:
            return {
                "success": False,
                "stdout": "",
                "stderr": "name is required. 请先调用 browser_ext_capabilities 获取可用能力名。",
            }

        try:
            timeout = float(timeout)
        except (TypeError, ValueError):
            timeout = 15.0

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
            "/api/browser-ext/command",
            json_data={
                "session_id": session_id,
                "action": name,
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
        # 网关信封：{"success": true, "result": {id, type:"result", success, data, error}}
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
