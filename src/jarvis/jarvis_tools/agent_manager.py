# -*- coding: utf-8 -*-
"""Agent 管理工具 - 用于管理 Agent 之间的通信和协作"""

import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

import jarvis.jarvis_utils.globals as jglobals

logger = logging.getLogger(__name__)


class AgentManagerTool:
    """Agent 管理工具，支持多种操作：

    1. **send_to**: 向指定 Agent 发送消息（通过 Web Gateway 代理到目标 Agent 的 /message 接口）
    2. 未来可扩展更多 action（如：list_agents, get_status 等）

    **重要提示**：
    - 每次调用只能执行一种操作
    - 参数根据操作类型而有所不同
    """

    name = "agent_manager"
    description = """Agent 管理工具，用于管理 Agent 之间的通信和协作。

支持的操作：
1. **send_to**: 向指定 Agent 发送消息，消息会通过 Web Gateway 代理到目标 Agent 的 /message 接口，添加到目标 Agent 的输入缓冲区

**重要提示**：
- 每次调用只能执行一种操作（send_to 等）
- 参数根据操作类型而有所不同"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["send_to", "list_agents"],
                "description": "操作类型：send_to（向 Agent 发送消息）、list_agents（获取所有存活 Agent 列表）",
            },
            # send_to 操作的参数
            "agent_id": {
                "type": "string",
                "description": "目标 Agent 的 ID（send_to 操作必填）",
            },
            "message": {
                "type": "string",
                "description": "要发送的消息内容（send_to 操作必填）",
            },
        },
        "required": ["action"],
    }

    def execute(
        self, action: str, agent_id: Optional[str] = None, message: str = "", **kwargs
    ) -> Dict[str, Any]:
        """执行 Agent 管理操作

        参数:
            action: 操作类型 (send_to)
            agent_id: 目标 Agent ID
            message: 消息内容
            **kwargs: 其他参数

        返回:
            Dict[str, Any]: 执行结果
        """
        try:
            if action == "send_to":
                return self._send_to(agent_id, message)
            elif action == "list_agents":
                return self._list_agents()
            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Unknown action: {action}",
                }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
            }

    def _get_master_url(self, action_name: str = "") -> Optional[Dict[str, Any]]:
        """获取 master_url，未设置时返回错误字典。

        参数:
            action_name: 操作名称，用于错误提示

        返回:
            None 表示 master_url 可用，否则返回错误字典
        """
        if not jglobals.master_url:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"master_url is not set, cannot {action_name}. "
                "Please ensure the agent is started with --master-url option.",
            }
        return None

    def _build_auth_headers(self) -> Dict[str, str]:
        """构建带认证信息的请求头。

        返回:
            Dict[str, str]: 请求头字典
        """
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
        error_prefix: str = "Request failed",
    ) -> Dict[str, Any]:
        """向 Gateway 发送 HTTP 请求。

        参数:
            method: HTTP 方法 (GET/POST)
            path: 请求路径 (如 /api/agents)
            json_data: POST 请求的 JSON 数据
            error_prefix: 错误提示前缀

        返回:
            Dict[str, Any]: 请求结果，包含 success/status_code/data 字段
        """
        url = f"{jglobals.master_url}{path}"
        headers = self._build_auth_headers()

        try:
            with httpx.Client(timeout=10.0) as client:
                if method.upper() == "POST":
                    response = client.post(url, json=json_data, headers=headers)
                else:
                    response = client.get(url, headers=headers)

            if response.status_code == 200:
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "data": response.json(),
                }
            else:
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
                "error": f"Cannot connect to gateway at {jglobals.master_url}. Please ensure the gateway is running.",
            }
        except Exception as e:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": f"{error_prefix}: {str(e)}",
            }

    def _send_to(self, agent_id: Optional[str], message: str) -> Dict[str, Any]:
        """向指定 Agent 发送消息。

        通过 Web Gateway 的 /api/agent/{agent_id}/message 接口发送消息，
        Gateway 会将请求代理到目标 Agent 的 /message 接口。

        参数:
            agent_id: 目标 Agent ID
            message: 消息内容

        返回:
            Dict[str, Any]: 发送结果
        """
        if not agent_id:
            return {"success": False, "stdout": "", "stderr": "agent_id is required"}

        if not message:
            return {"success": False, "stdout": "", "stderr": "message is required"}

        err = self._get_master_url("send message to remote agent")
        if err:
            return err

        sender_id = jglobals.agent_id
        result = self._request_gateway(
            method="POST",
            path=f"/api/agent/{agent_id}/message",
            json_data={"sender_id": sender_id, "content": message},
            error_prefix=f"Failed to send message to agent {agent_id}",
        )

        if result["success"]:
            output = {
                "agent_id": agent_id,
                "sender_id": sender_id,
                "message": message,
                "response": result["data"],
            }
            return {
                "success": True,
                "stdout": json.dumps(output, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}

    def _list_agents(self) -> Dict[str, Any]:
        """获取所有存活状态的 Agent 列表。

        通过 Web Gateway 的 /api/agents 接口获取 Agent 列表，
        过滤掉已停止的 Agent，返回存活 Agent 的基本信息。

        返回:
            Dict[str, Any]: 存活 Agent 列表
        """
        err = self._get_master_url("list agents")
        if err:
            return err

        result = self._request_gateway(
            method="GET",
            path="/api/agents",
            error_prefix="Failed to list agents",
        )

        if result["success"]:
            gateway_data = result["data"]
            if not gateway_data.get("success"):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Gateway returned error: {gateway_data.get('error', 'unknown error')}",
                }

            agents = gateway_data.get("data", [])
            alive_agents = [
                agent for agent in agents if agent.get("status") != "stopped"
            ]
            return {
                "success": True,
                "stdout": json.dumps(alive_agents, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}
