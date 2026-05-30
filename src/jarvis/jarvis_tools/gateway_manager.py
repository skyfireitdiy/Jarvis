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
    5. **create_agent**: 创建新的 Agent
    6. **list_directory**: 获取指定路径下的文件/目录列表，支持跨节点查询
    7. **delete_agent**: 删除指定的 Agent
    8. **get_node_secret**: 获取网关的节点连接私钥
    9. **update_nodes_code**: 更新所有节点代码到 main 分支

    **重要提示**：
    - 每次调用只能执行一种操作
    - 参数根据操作类型而有所不同
    """

    name = "gateway_manager"

    @staticmethod
    def check() -> bool:
        """检查工具是否可用，仅当 Gateway 存在时启用（通过 agent_id 是否设置判断）。"""
        return jglobals.agent_id is not None

    description = """Agent 管理工具，用于管理 Agent 之间的通信和协作。

支持的操作：
1. **send_to_agent**: 向指定 Agent 发送消息，消息会通过 Web Gateway 代理到目标 Agent 的 /message 接口，添加到目标 Agent 的输入缓冲区
2. **list_agents**: 获取所有 Agent 列表
3. **list_nodes**: 获取节点列表信息，包括本节点配置、运行状态、已注册的子节点等
4. **list_model_groups**: 获取指定节点的模型组列表，包括模型组名称、各档位模型配置等
5. **create_agent**: 创建新的 Agent，支持指定类型、工作目录、模型组、任务等参数
6. **list_directory**: 获取指定路径下的文件/目录列表，支持跨节点查询（通过 node_id 指定目标节点）
7. **delete_agent**: 删除指定的 Agent，支持跨节点删除（通过 node_id 指定目标节点）
8. **get_node_secret**: 获取网关的节点连接私钥，用于子节点连接主网关时的身份认证
9. **update_nodes_code**: 更新所有节点代码到 main 分支，将所有节点的 Jarvis 代码切换到 main 分支并拉取最新代码

**重要提示**：
- 每次调用只能执行一种操作（send_to_agent、list_agents、list_nodes、list_model_groups、create_agent、list_directory、delete_agent、get_node_secret、update_nodes_code）
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
                    "create_agent",
                    "list_directory",
                    "delete_agent",
                    "get_node_secret",
                    "update_nodes_code",
                ],
                "description": "操作类型：send_to_agent（向 Agent 发送消息）、list_agents（获取所有 Agent 列表）、list_nodes（获取节点列表信息）、list_model_groups（获取指定节点的模型组列表）、create_agent（创建新的 Agent）、list_directory（获取文件/目录列表）、delete_agent（删除指定的 Agent）、get_node_secret（获取网关的节点连接私钥）、update_nodes_code（更新所有节点代码到 main 分支）",
            },
            # send_to_agent 操作的参数
            "agent_id": {
                "type": "string",
                "description": "目标 Agent 的 ID（send_to_agent 操作必填；delete_agent 操作必填）",
            },
            "message": {
                "type": "string",
                "description": "要发送的消息内容（send_to_agent 操作必填）",
            },
            # list_model_groups / create_agent / list_directory 操作的参数
            "node_id": {
                "type": "string",
                "description": "目标节点 ID（list_model_groups 操作可选，默认为 master；create_agent 操作可选，默认为本节点；list_directory 操作可选，默认为本节点；delete_agent 操作可选，默认为本节点）",
            },
            # list_directory 操作的参数
            "path": {
                "type": "string",
                "description": "目录路径（list_directory 操作可选，默认为空表示用户主目录）",
            },
            # create_agent 操作的参数
            "agent_type": {
                "type": "string",
                "description": "Agent 类型（create_agent 操作必填），如 code、chat 等",
            },
            "working_dir": {
                "type": "string",
                "description": "工作目录（create_agent 操作必填）",
            },
            "agent_name": {
                "type": "string",
                "description": "Agent 名称（create_agent 操作可选）",
            },
            "llm_group": {
                "type": "string",
                "description": "模型组名称（create_agent 操作可选，默认为 default）",
            },
            "tool_group": {
                "type": "string",
                "description": "工具组名称（create_agent 操作可选，默认为 default）",
            },
            "config_file": {
                "type": "string",
                "description": "配置文件路径（create_agent 操作可选）",
            },
            "task": {
                "type": "string",
                "description": "Agent 的初始任务描述（create_agent 操作可选，no_interaction_mode 时必填）",
            },
            "additional_args": {
                "type": "string",
                "description": "附加参数（create_agent 操作可选）",
            },
            "worktree": {
                "type": "boolean",
                "description": "是否使用 git worktree（create_agent 操作可选，默认为 false）",
            },
            "quick_mode": {
                "type": "boolean",
                "description": "是否启用快速模式（create_agent 操作可选，默认为 false）",
            },
            "restore_session": {
                "type": "boolean",
                "description": "是否恢复上一次会话（create_agent 操作可选，默认为 false）",
            },
            "no_interaction_mode": {
                "type": "boolean",
                "description": "是否启用无交互模式（create_agent 操作可选，默认为 false，启用时 task 必填）",
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
        path: str = "",
        agent_type: Optional[str] = None,
        working_dir: Optional[str] = None,
        agent_name: Optional[str] = None,
        llm_group: Optional[str] = None,
        tool_group: Optional[str] = None,
        config_file: Optional[str] = None,
        task: Optional[str] = None,
        additional_args: Optional[str] = None,
        worktree: bool = False,
        quick_mode: bool = False,
        restore_session: bool = False,
        no_interaction_mode: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """执行 Gateway 管理操作

        参数:
            action: 操作类型 (send_to_agent, list_agents, list_nodes, list_model_groups, create_agent, list_directory, delete_agent)
            agent_id: 目标 Agent ID
            message: 消息内容
            node_id: 目标节点 ID
            path: 目录路径（list_directory）
            agent_type: Agent 类型（create_agent）
            working_dir: 工作目录（create_agent）
            agent_name: Agent 名称（create_agent）
            llm_group: 模型组（create_agent）
            tool_group: 工具组（create_agent）
            config_file: 配置文件（create_agent）
            task: 任务描述（create_agent）
            additional_args: 附加参数（create_agent）
            worktree: 是否使用 worktree（create_agent）
            quick_mode: 快速模式（create_agent）
            restore_session: 恢复会话（create_agent）
            no_interaction_mode: 无交互模式（create_agent）
            **kwargs: 其他参数

        返回:
            Dict[str, Any]: 执行结果
        """
        # 兼容 v1.0 协议：registry 可能将整个参数字典作为 action 传入
        if isinstance(action, dict):
            args = action
            action = args.get("action", "")
            agent_id = args.get("agent_id")
            message = args.get("message", "")
            node_id = args.get("node_id")
            path = args.get("path", "")
            agent_type = args.get("agent_type")
            working_dir = args.get("working_dir")
            agent_name = args.get("agent_name")
            llm_group = args.get("llm_group")
            tool_group = args.get("tool_group")
            config_file = args.get("config_file")
            task = args.get("task")
            additional_args = args.get("additional_args")
            worktree = args.get("worktree", False)
            quick_mode = args.get("quick_mode", False)
            restore_session = args.get("restore_session", False)
            no_interaction_mode = args.get("no_interaction_mode", False)
        try:
            if action == "send_to_agent":
                return self._send_to_agent(agent_id, message)
            elif action == "list_agents":
                return self._list_agents()
            elif action == "list_nodes":
                return self._list_nodes()
            elif action == "list_model_groups":
                return self._list_model_groups(node_id)
            elif action == "create_agent":
                return self._create_agent(
                    agent_type=agent_type,
                    working_dir=working_dir,
                    name=agent_name,
                    llm_group=llm_group,
                    tool_group=tool_group,
                    config_file=config_file,
                    task=task,
                    additional_args=additional_args,
                    worktree=worktree,
                    quick_mode=quick_mode,
                    restore_session=restore_session,
                    no_interaction_mode=no_interaction_mode,
                    node_id=node_id,
                )
            elif action == "list_directory":
                return self._list_directory(path=path, node_id=node_id)
            elif action == "delete_agent":
                return self._delete_agent(agent_id=agent_id, node_id=node_id)
            elif action == "get_node_secret":
                return self._get_node_secret()
            elif action == "update_nodes_code":
                return self._update_nodes_code()
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
        params: Optional[Dict[str, str]] = None,
        error_prefix: str = "Request failed",
    ) -> Dict[str, Any]:
        """向 Gateway 发送 HTTP 请求。

        参数:
            method: HTTP 方法 (GET/POST/DELETE)
            path: 请求路径 (如 /api/agents)
            json_data: POST 请求的 JSON 数据
            params: GET/DELETE 请求的 query 参数
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

    def _create_agent(
        self,
        agent_type: Optional[str] = None,
        working_dir: Optional[str] = None,
        name: Optional[str] = None,
        llm_group: Optional[str] = None,
        tool_group: Optional[str] = None,
        config_file: Optional[str] = None,
        task: Optional[str] = None,
        additional_args: Optional[str] = None,
        worktree: bool = False,
        quick_mode: bool = False,
        restore_session: bool = False,
        no_interaction_mode: bool = False,
        node_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建新的 Agent。

        通过 Web Gateway 的 POST /api/agents 接口创建 Agent，
        支持跨节点创建（通过 node_id 参数指定目标节点）。

        参数:
            agent_type: Agent 类型（必填），如 code、chat 等
            working_dir: 工作目录（必填）
            name: Agent 名称
            llm_group: 模型组名称
            tool_group: 工具组名称
            config_file: 配置文件路径
            task: 初始任务描述
            additional_args: 附加参数
            worktree: 是否使用 git worktree
            quick_mode: 是否启用快速模式
            restore_session: 是否恢复上一次会话
            no_interaction_mode: 是否启用无交互模式（启用时 task 必填）
            node_id: 目标节点 ID

        返回:
            Dict[str, Any]: 创建结果
        """
        if not agent_type:
            return {"success": False, "stdout": "", "stderr": "agent_type is required"}
        if not working_dir:
            return {"success": False, "stdout": "", "stderr": "working_dir is required"}
        if no_interaction_mode and not task:
            return {
                "success": False,
                "stdout": "",
                "stderr": "task is required when no_interaction_mode is enabled",
            }

        err = self._get_master_url("create agent")
        if err:
            return err

        # 构建请求体，只包含非空参数
        body: Dict[str, Any] = {
            "agent_type": agent_type,
            "working_dir": working_dir,
        }
        if name:
            body["name"] = name
        if llm_group:
            body["llm_group"] = llm_group
        if tool_group:
            body["tool_group"] = tool_group
        if config_file:
            body["config_file"] = config_file
        if task:
            body["task"] = task
        if additional_args:
            body["additional_args"] = additional_args
        if worktree:
            body["worktree"] = True
        if quick_mode:
            body["quick_mode"] = True
        if restore_session:
            body["restore_session"] = True
        if no_interaction_mode:
            body["no_interaction_mode"] = True
        if node_id:
            body["node_id"] = node_id

        result = self._request_gateway(
            method="POST",
            path="/api/agents",
            json_data=body,
            error_prefix="Failed to create agent",
        )

        if result["success"]:
            gateway_data = result["data"]
            if not gateway_data.get("success"):
                error_info = gateway_data.get("error", {})
                error_msg = (
                    error_info.get("message", "unknown error")
                    if isinstance(error_info, dict)
                    else str(error_info)
                )
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Gateway returned error: {error_msg}",
                }

            agent_info = gateway_data.get("data", {})
            return {
                "success": True,
                "stdout": json.dumps(agent_info, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}

    def _list_directory(
        self, path: str = "", node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取指定路径下的文件/目录列表。

        通过 Web Gateway 的 GET /api/directories 接口获取目录列表，
        支持跨节点查询（通过 node_id 参数指定目标节点）。

        参数:
            path: 目录路径，默认为空（表示用户主目录）
            node_id: 目标节点 ID，默认为空（表示本节点）

        返回:
            Dict[str, Any]: 目录列表
        """
        err = self._get_master_url("list directory")
        if err:
            return err

        # 构建 query 参数
        query_params: Dict[str, str] = {}
        if path:
            query_params["path"] = path
        if node_id:
            query_params["node_id"] = node_id

        result = self._request_gateway(
            method="GET",
            path="/api/directories",
            params=query_params if query_params else None,
            error_prefix="Failed to list directory",
        )

        if result["success"]:
            gateway_data = result["data"]
            if not gateway_data.get("success"):
                error_detail = gateway_data.get("error", "unknown error")
                if isinstance(error_detail, dict):
                    error_msg = error_detail.get("message", str(error_detail))
                else:
                    error_msg = str(error_detail)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Gateway returned error: {error_msg}",
                }

            data = gateway_data.get("data", {})
            return {
                "success": True,
                "stdout": json.dumps(data, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}

    def _get_node_secret(self) -> Dict[str, Any]:
        """获取网关的节点连接私钥。

        通过 Web Gateway 的 GET /api/node/secret 接口获取节点连接私钥，
        此私钥用于子节点连接主网关时的身份认证。

        返回:
            Dict[str, Any]: 包含 node_secret 的结果
        """
        err = self._get_master_url("get node secret")
        if err:
            return err

        result = self._request_gateway(
            method="GET",
            path="/api/node/secret",
            error_prefix="Failed to get node secret",
        )

        if result["success"]:
            gateway_data = result["data"]
            if not gateway_data.get("success"):
                error_info = gateway_data.get("error", {})
                error_msg = (
                    error_info.get("message", "unknown error")
                    if isinstance(error_info, dict)
                    else str(error_info)
                )
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Gateway returned error: {error_msg}",
                }

            data = gateway_data.get("data", {})
            node_secret = data.get("node_secret", "")
            return {
                "success": True,
                "stdout": json.dumps(
                    {"node_secret": node_secret}, ensure_ascii=False, indent=2
                ),
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}

    def _update_nodes_code(self) -> Dict[str, Any]:
        """更新所有节点代码到 main 分支。

        通过 Web Gateway 的 POST /api/nodes/{node_id}/code-update 接口，
        将所有在线节点的 Jarvis 代码切换到 main 分支并拉取最新代码。

        返回:
            Dict[str, Any]: 包含各节点更新结果的信息
        """
        err = self._get_master_url("update nodes code")
        if err:
            return err

        # 先获取所有在线节点
        nodes_result = self._request_gateway(
            method="GET",
            path="/api/nodes",
            error_prefix="Failed to get nodes list",
        )

        if not nodes_result["success"]:
            return {"success": False, "stdout": "", "stderr": nodes_result["error"]}

        gateway_data = nodes_result["data"]
        if not gateway_data.get("success"):
            error_info = gateway_data.get("error", {})
            error_msg = (
                error_info.get("message", "unknown error")
                if isinstance(error_info, dict)
                else str(error_info)
            )
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Gateway returned error: {error_msg}",
            }

        nodes_data = gateway_data.get("data", {})
        nodes = nodes_data.get("nodes", [])
        if not nodes:
            return {
                "success": False,
                "stdout": "",
                "stderr": "No online nodes available for code update",
            }

        # 对每个节点执行代码更新
        results = []
        success_count = 0
        for node in nodes:
            node_id = node.get("node_id", "")
            if not node_id:
                continue

            update_result = self._request_gateway(
                method="POST",
                path=f"/api/nodes/{node_id}/code-update",
                error_prefix=f"Failed to update code for node {node_id}",
            )

            if update_result["success"]:
                update_data = update_result["data"]
                if update_data.get("success"):
                    success_count += 1
                    data = update_data.get("data", {})
                    results.append(
                        {
                            "node_id": node_id,
                            "success": True,
                            "message": data.get("message", "更新成功"),
                        }
                    )
                else:
                    error_info = update_data.get("error", {})
                    error_msg = (
                        error_info.get("message", "unknown error")
                        if isinstance(error_info, dict)
                        else str(error_info)
                    )
                    results.append(
                        {
                            "node_id": node_id,
                            "success": False,
                            "message": error_msg,
                        }
                    )
            else:
                results.append(
                    {
                        "node_id": node_id,
                        "success": False,
                        "message": update_result["error"],
                    }
                )

        total_count = len(nodes)
        if success_count == total_count:
            message = f"代码更新成功，已更新 {success_count}/{total_count} 个节点"
        elif success_count > 0:
            message = f"代码更新部分成功，成功 {success_count}/{total_count} 个节点"
        else:
            message = "代码更新失败，没有节点更新成功"

        summary: Dict[str, Any] = {
            "total": total_count,
            "success": success_count,
            "failed": total_count - success_count,
            "results": results,
            "message": message,
        }

        return {
            "success": success_count > 0,
            "stdout": json.dumps(summary, ensure_ascii=False, indent=2),
            "stderr": "" if success_count > 0 else "All nodes failed to update",
        }

    def _delete_agent(
        self, agent_id: Optional[str] = None, node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """删除指定的 Agent。

        通过 Web Gateway 的 DELETE /api/agents/{agent_id} 接口删除 Agent，
        支持跨节点删除（通过 node_id 参数指定目标节点）。

        参数:
            agent_id: 要删除的 Agent ID（必填）
            node_id: 目标节点 ID，默认为空（表示本节点）

        返回:
            Dict[str, Any]: 删除结果
        """
        if not agent_id:
            return {"success": False, "stdout": "", "stderr": "agent_id is required"}

        err = self._get_master_url("delete agent")
        if err:
            return err

        # 构建 query 参数
        query_params: Dict[str, str] = {}
        if node_id:
            query_params["node_id"] = node_id

        result = self._request_gateway(
            method="DELETE",
            path=f"/api/agents/{agent_id}",
            params=query_params if query_params else None,
            error_prefix=f"Failed to delete agent {agent_id}",
        )

        if result["success"]:
            gateway_data = result["data"]
            if not gateway_data.get("success"):
                error_info = gateway_data.get("error", {})
                error_msg = (
                    error_info.get("message", "unknown error")
                    if isinstance(error_info, dict)
                    else str(error_info)
                )
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Gateway returned error: {error_msg}",
                }

            data = gateway_data.get("data", {})
            return {
                "success": True,
                "stdout": json.dumps(data, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}
