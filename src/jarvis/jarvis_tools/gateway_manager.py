# -*- coding: utf-8 -*-
"""Gateway 管理工具 - 用于管理 Agent 之间的通信和协作以及节点信息查询"""

import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

import jarvis.jarvis_utils.globals as jglobals

logger = logging.getLogger(__name__)


class GatewayManagerTool:
    """Gateway 管理工具，支持多种操作：

    1. **send_to_agent**: 向指定 Agent 发送消息（通过 Web Gateway 代理到目标 Agent 的 /message 接口）
    2. **list_agents**: 获取所有 Agent 列表
    3. **list_nodes**: 获取节点列表信息
    4. **list_model_groups**: 获取指定节点的模型组列表

    **重要提示**：
    - 每次调用只能执行一种操作
    - 参数根据操作类型而有所不同
    """

    name = "gateway_manager"
    description = """Agent 管理工具，用于管理 Agent 之间的通信和协作。

支持的操作：
1. **send_to_agent**: 向指定 Agent 发送消息，消息会通过 Web Gateway 代理到目标 Agent 的 /message 接口，添加到目标 Agent 的输入缓冲区
2. **list_agents**: 获取所有 Agent 列表
3. **list_nodes**: 获取节点列表信息，包括本节点配置、运行状态、已注册的子节点等
4. **list_model_groups**: 获取指定节点的模型组列表，包括模型组名称、各档位模型配置等

**重要提示**：
- 每次调用只能执行一种操作（send_to_agent、list_agents、list_nodes、list_model_groups）
- 参数根据操作类型而有所不同"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "send_to_agent",
                    "list_agents",
                    "list_nodes",
                    "list_model_groups",
                ],
                "description": "操作类型：send_to_agent（向 Agent 发送消息）、list_agents（获取所有 Agent 列表）、list_nodes（获取节点列表信息）、list_model_groups（获取指定节点的模型组列表）",
            },
            # send_to_agent 操作的参数
            "agent_id": {
                "type": "string",
                "description": "目标 Agent 的 ID（send_to_agent 操作必填）",
            },
            "message": {
                "type": "string",
                "description": "要发送的消息内容（send_to_agent 操作必填）",
            },
            # list_model_groups 操作的参数
            "node_id": {
                "type": "string",
                "description": "目标节点 ID（list_model_groups 操作可选，默认为 master）",
            },
        },
        "required": ["action"],
    }

    def execute(
        self,
        action: str,
        agent_id: Optional[str] = None,
        message: str = "",
        node_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """执行 Gateway 管理操作

        参数:
            action: 操作类型 (send_to_agent, list_agents, list_nodes, list_model_groups)
            agent_id: 目标 Agent ID
            message: 消息内容
            node_id: 目标节点 ID
            **kwargs: 其他参数

        返回:
            Dict[str, Any]: 执行结果
        """
        try:
            if action == "send_to_agent":
                return self._send_to_agent(agent_id, message)
            elif action == "list_agents":
                return self._list_agents()
            elif action == "list_nodes":
                return self._list_nodes()
            elif action == "list_model_groups":
                return self._list_model_groups(node_id)
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

    def _send_to_agent(self, agent_id: Optional[str], message: str) -> Dict[str, Any]:
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

        err = self._get_master_url("send message to agent")
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
        """获取所有 Agent 列表。

        通过 Web Gateway 的 /api/agents 接口获取 Agent 列表，
        返回所有 Agent 的基本信息。

        返回:
            Dict[str, Any]: Agent 列表
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
            return {
                "success": True,
                "stdout": json.dumps(agents, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}

    def _list_nodes(self) -> Dict[str, Any]:
        """获取节点列表信息。

        通过 Web Gateway 的 /api/node/status 接口获取节点信息，
        包括本节点配置、运行状态、已注册的子节点、Agent 路由等。

        返回:
            Dict[str, Any]: 节点状态信息
        """
        err = self._get_master_url("list nodes")
        if err:
            return err

        result = self._request_gateway(
            method="GET",
            path="/api/node/status",
            error_prefix="Failed to list nodes",
        )

        if result["success"]:
            gateway_data = result["data"]
            if not gateway_data.get("success"):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Gateway returned error: {gateway_data.get('error', 'unknown error')}",
                }

            # 提取节点相关信息
            data = gateway_data.get("data", {})
            node_info = {
                "node": data.get("node", {}),
                "runtime_status": data.get("runtime_status", "unknown"),
                "nodes": data.get("nodes", []),
                "agent_routes": data.get("agent_routes", []),
            }
            return {
                "success": True,
                "stdout": json.dumps(node_info, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}

    def _list_model_groups(self, node_id: Optional[str] = None) -> Dict[str, Any]:
        """获取指定节点的模型组列表。

        通过 Web Gateway 的 /api/node/{node_id}/model-groups 接口获取模型组列表，
        支持跨节点查询，master 节点会代理请求到目标节点。

        参数:
            node_id: 目标节点 ID，默认为 master

        返回:
            Dict[str, Any]: 模型组列表
        """
        target_node = node_id or "master"

        err = self._get_master_url("list model groups")
        if err:
            return err

        result = self._request_gateway(
            method="GET",
            path=f"/api/node/{target_node}/model-groups",
            error_prefix="Failed to list model groups",
        )

        if result["success"]:
            gateway_data = result["data"]
            if not gateway_data.get("success"):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Gateway returned error: {gateway_data.get('error', 'unknown error')}",
                }

            data = gateway_data.get("data", [])
            default_llm_group = gateway_data.get("default_llm_group", "")
            output = {
                "model_groups": data,
                "default_llm_group": default_llm_group,
            }
            return {
                "success": True,
                "stdout": json.dumps(output, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}
