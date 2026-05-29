# -*- coding: utf-8 -*-
"""Agent 管理工具 - 用于管理 Agent 之间的通信和协作"""

import json
import logging
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
                "enum": ["send_to"],
                "description": "操作类型：send_to（向 Agent 发送消息）",
            },
            # send_to 操作的参数
            "agent_id": {
                "type": "string",
                "description": "目标 Agent 的 ID",
            },
            "message": {
                "type": "string",
                "description": "要发送的消息内容",
            },
        },
        "required": ["action", "agent_id", "message"],
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

    def _send_to(self, agent_id: Optional[str], message: str) -> Dict[str, Any]:
        """向指定 Agent 发送消息

        通过 Web Gateway 的 /api/agent/{agent_id}/message 接口发送消息，
        Gateway 会将请求代理到目标 Agent 的 /message 接口。

        参数:
            agent_id: 目标 Agent ID
            message: 消息内容

        返回:
            Dict[str, Any]: 发送结果
        """
        if not agent_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "agent_id is required",
            }

        if not message:
            return {
                "success": False,
                "stdout": "",
                "stderr": "message is required",
            }

        # 获取 master_url（Web Gateway 地址）
        master_url = jglobals.master_url
        if not master_url:
            return {
                "success": False,
                "stdout": "",
                "stderr": "master_url is not set, cannot send message to remote agent. "
                "Please ensure the agent is started with --master-url option.",
            }

        # 构建请求 URL: POST /api/agent/{agent_id}/message
        # Gateway 的 agent_http_proxy 会将请求代理到目标 Agent 的 /message 接口
        url = f"{master_url}/api/agent/{agent_id}/message"

        # 获取当前 Agent 的 ID 作为 sender_id
        sender_id = jglobals.agent_id

        # 发送 HTTP POST 请求
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    url,
                    json={
                        "sender_id": sender_id,
                        "content": message,
                    },
                )

            if response.status_code == 200:
                result = response.json()
                output = {
                    "agent_id": agent_id,
                    "sender_id": sender_id,
                    "message": message,
                    "response": result,
                }
                return {
                    "success": True,
                    "stdout": json.dumps(output, ensure_ascii=False, indent=2),
                    "stderr": "",
                }
            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Failed to send message to agent {agent_id}: HTTP {response.status_code} - {response.text}",
                }
        except httpx.ConnectError:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Cannot connect to gateway at {master_url}. Please ensure the gateway is running.",
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to send message: {str(e)}",
            }
